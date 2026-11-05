param(
    [Parameter(Mandatory = $true)][string]$Port,
    [string]$OutputDirectory = (Join-Path $PSScriptRoot 'captures/cam-check')
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
[void][IO.Directory]::CreateDirectory($OutputDirectory)
$startUtc = [DateTime]::UtcNow
$stamp = [TimeZoneInfo]::ConvertTimeFromUtc($startUtc,
    [TimeZoneInfo]::FindSystemTimeZoneById('China Standard Time')).ToString('yyyyMMdd_HHmmss_fff')
$outputBase = Join-Path $OutputDirectory ('camcheck_' + $stamp)
$log = New-Object 'Collections.Generic.List[string]'
$clock = [Diagnostics.Stopwatch]::StartNew()
$connection = New-Object IO.Ports.SerialPort $Port,115200,'None',8,'One'
$connection.DtrEnable = $false
$connection.RtsEnable = $false
$connection.Handshake = [IO.Ports.Handshake]::None
$connection.ReadTimeout = 500
$connection.WriteTimeout = 2000
$connection.ReadBufferSize = 65536
$report = [ordered]@{
    schema = 'esp32cam-usb-check-v1'
    started_utc = $startUtc.ToString('o')
    port = $Port
    baud = 115200
    pass = $false
    clock_scope = 'Camera timestamps are local since boot, first DMA not exposure; not synchronized to PC or S3'
    integrity_scope = 'Length, JPEG markers, bitmap decode and DONE checked; no payload CRC in this USB protocol'
    receiver_sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash
}
$runError = $null

function Read-CameraLine([double]$Deadline) {
    $line = New-Object Text.StringBuilder
    while ($clock.Elapsed.TotalSeconds -lt $Deadline) {
        try { $next = $connection.ReadByte() }
        catch [TimeoutException] { continue }
        if ($next -eq 10) {
            $text = $line.ToString().Trim()
            if ($text -match '(?i)\bMAC\b') { $text = '[device identifier omitted]' }
            $log.Add($text)
            if ($text.StartsWith('ERR_')) { throw ('Camera: ' + $text) }
            return $text
        }
        if ($next -ne 13 -and $next -ge 0) { [void]$line.Append([char]$next) }
        if ($line.Length -gt 2048) { throw 'Device text line exceeds 2048 bytes.' }
    }
    throw 'Timed out waiting for a camera response.'
}

function Parse-Fields([string]$Line) {
    $fields = @{}
    foreach ($part in ($Line -split ' ' | Select-Object -Skip 1)) {
        if ($part -notmatch '^([a-z_]+)=([^ ]+)$') { throw ('Invalid metadata: ' + $part) }
        if ($fields.ContainsKey($Matches[1])) { throw 'Duplicate metadata field.' }
        $fields[$Matches[1]] = $Matches[2]
    }
    return $fields
}

function Require-Integer($Fields, [string]$Name) {
    if (!$Fields.ContainsKey($Name) -or $Fields[$Name] -notmatch '^\d+$') {
        throw ('Missing or invalid integer: ' + $Name)
    }
    return [long]$Fields[$Name]
}

try {
    $connection.Open()
    $deadline = $clock.Elapsed.TotalSeconds + 15
    do { $line = Read-CameraLine $deadline } until ($line -eq 'READY')
    $connection.Write('INFO' + [char]10)
    $deadline = $clock.Elapsed.TotalSeconds + 5
    do { $line = Read-CameraLine $deadline } until ($line.StartsWith('INFO '))
    $info = Parse-Fields $line
    if ($info['fw'] -ne 'ESP32CAM_USB_Check_v1' -or $info['format'] -ne 'JPEG') {
        throw 'Expected ESP32CAM_USB_Check_v1 JPEG firmware.'
    }
    $report.device_info = $info

    $requestHostMs = $clock.Elapsed.TotalMilliseconds
    $connection.Write('CAPTURE' + [char]10)
    $deadline = $clock.Elapsed.TotalSeconds + 20
    $meta = $null
    do {
        $line = Read-CameraLine $deadline
        if ($line.StartsWith('META ')) {
            if ($null -ne $meta) { throw 'Duplicate META.' }
            $meta = Parse-Fields $line
        }
    } until ($line -match '^IMG (\d+)$')
    $expectedBytes = [long]$Matches[1]
    if ($expectedBytes -lt 4 -or $expectedBytes -gt 2097152 -or $null -eq $meta) {
        throw 'Invalid image length or missing META.'
    }
    $requestUs = Require-Integer $meta 'request_us'
    $frameUs = Require-Integer $meta 'frame_us'
    $acquiredUs = Require-Integer $meta 'acquired_us'
    $seq = Require-Integer $meta 'seq'
    $discarded = Require-Integer $meta 'discarded'
    $width = Require-Integer $meta 'width'
    $height = Require-Integer $meta 'height'
    if ($frameUs -lt $requestUs -or $acquiredUs -lt $frameUs -or $seq -lt 1 -or
        (Require-Integer $meta 'len') -ne $expectedBytes -or
        $width -ne 640 -or $height -ne 480 -or
        (Require-Integer $info 'width') -ne $width -or
        (Require-Integer $info 'height') -ne $height) {
        throw 'Freshness, sequence, size or resolution metadata failed.'
    }
    $report.frame_meta = $meta
    $payloadStartMs = $clock.Elapsed.TotalMilliseconds
    $payload = New-Object byte[] ([int]$expectedBytes)
    $received = 0
    $deadline = $clock.Elapsed.TotalSeconds + 120
    while ($received -lt $expectedBytes) {
        if ($clock.Elapsed.TotalSeconds -ge $deadline) { throw 'JPEG transfer timed out.' }
        try {
            $received += $connection.Read($payload,$received,
                [Math]::Min(4096,[int]$expectedBytes - $received))
        } catch [TimeoutException] { continue }
    }
    $payloadEndMs = $clock.Elapsed.TotalMilliseconds
    if ($payload[0] -ne 255 -or $payload[1] -ne 216 -or
        $payload[$received - 2] -ne 255 -or $payload[$received - 1] -ne 217) {
        throw 'JPEG markers failed.'
    }
    $deadline = $clock.Elapsed.TotalSeconds + 5
    do { $line = Read-CameraLine $deadline } until ($line.StartsWith('DONE '))
    $done = Parse-Fields $line
    if ((Require-Integer $done 'seq') -ne $seq -or
        (Require-Integer $done 'written') -ne $received) { throw 'DONE mismatch.' }
    $report.done = $done

    $stream = New-Object IO.MemoryStream(,$payload)
    $image = $null
    $bitmap = $null
    try {
        $image = [Drawing.Image]::FromStream($stream,$true,$true)
        $bitmap = New-Object Drawing.Bitmap $image
        if ($bitmap.Width -ne $width -or $bitmap.Height -ne $height) {
            throw 'Decoded image dimensions differ from metadata.'
        }
        [void]$bitmap.GetPixel([int]($width / 2),[int]($height / 2))
    } finally {
        if ($null -ne $bitmap) { $bitmap.Dispose() }
        if ($null -ne $image) { $image.Dispose() }
        $stream.Dispose()
    }
    $photo = $outputBase + '.jpg'
    [IO.File]::WriteAllBytes($photo,$payload)
    $report.photo = [IO.Path]::GetFileName($photo)
    $report.bytes = $received
    $report.width = $width
    $report.height = $height
    $report.photo_sha256 = (Get-FileHash -LiteralPath $photo -Algorithm SHA256).Hash
    $report.frame_dma_after_request = $true
    $report.jpeg_markers_pass = $true
    $report.bitmap_decode_pass = $true
    $report.device_request_to_acquired_ms = ($acquiredUs - $requestUs) / 1000.0
    $report.device_dma_to_acquired_ms = ($acquiredUs - $frameUs) / 1000.0
    $report.device_jpeg_uart_send_ms = (Require-Integer $done 'send_us') / 1000.0
    $report.host_payload_read_ms = $payloadEndMs - $payloadStartMs
    $report.host_request_to_payload_end_ms = $payloadEndMs - $requestHostMs
    $report.pass = $true
} catch {
    $runError = $_.Exception.Message
    $report.error = $runError
} finally {
    if ($connection.IsOpen) { $connection.Close() }
    $connection.Dispose()
    $report.finished_utc = [DateTime]::UtcNow.ToString('o')
    $report.host_run_elapsed_ms = $clock.Elapsed.TotalMilliseconds
    $log | Set-Content -LiteralPath ($outputBase + '.log') -Encoding UTF8
    $report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath ($outputBase + '.json') -Encoding UTF8
}

if ($null -ne $runError) { Write-Output ('ERROR: ' + $runError); exit 1 }
[ordered]@{
    pass = $report.pass
    photo = $photo
    bytes = $report.bytes
    width = $width
    height = $height
    discarded_old_frames = $discarded
    device_request_to_acquired_ms = $report.device_request_to_acquired_ms
    device_jpeg_uart_send_ms = $report.device_jpeg_uart_send_ms
    host_payload_read_ms = $report.host_payload_read_ms
    device = $info
    report = $outputBase + '.json'
} | ConvertTo-Json -Depth 4
