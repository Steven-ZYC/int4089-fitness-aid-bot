param(
    [string]$Port = 'COM9',
    [string]$OutputDirectory = (Join-Path $PSScriptRoot 'captures'),
    [switch]$OpenImage
)

$ErrorActionPreference = 'Stop'
$connection = New-Object System.IO.Ports.SerialPort
$connection.PortName = $Port
$connection.BaudRate = 115200
$connection.DataBits = 8
$connection.Parity = [System.IO.Ports.Parity]::None
$connection.StopBits = [System.IO.Ports.StopBits]::One
$connection.Handshake = [System.IO.Ports.Handshake]::None
$connection.DtrEnable = $false
$connection.RtsEnable = $false
$connection.ReadTimeout = 1000
$connection.WriteTimeout = 2000
$connection.ReadBufferSize = 65536

# Read text one byte at a time so no JPEG bytes are decoded as text.
function Read-DeviceLine {
    param($Connection, [datetime]$Deadline)

    $line = New-Object System.Text.StringBuilder
    while ([datetime]::UtcNow -lt $Deadline) {
        try {
            $nextByte = $Connection.ReadByte()
        } catch [System.TimeoutException] {
            continue
        }

        if ($nextByte -eq 10) {
            return $line.ToString().Trim()
        }
        if ($nextByte -ge 0 -and $nextByte -ne 13) {
            [void]$line.Append([char]$nextByte)
            if ($line.Length -gt 2048) {
                [void]$line.Clear()
            }
        }
    }
    throw 'Timed out waiting for ESP32-CAM. Check the port and press the board RESET button once.'
}

$savedImage = $null
try {
    $connection.Open()
    Write-Host "Waiting for READY on $Port ..."
    $deadline = [datetime]::UtcNow.AddSeconds(30)

    do {
        $line = Read-DeviceLine $connection $deadline
        if ($line.StartsWith('ERR_')) {
            throw "ESP32-CAM reported: $line"
        }
    } until ($line -eq 'READY')

    $connection.Write("CAPTURE`n")
    Write-Host 'Capture requested. Receiving JPEG ...'
    $deadline = [datetime]::UtcNow.AddSeconds(30)
    $expectedBytes = 0

    while ($expectedBytes -eq 0) {
        $line = Read-DeviceLine $connection $deadline
        if ($line.StartsWith('ERR_')) {
            throw "ESP32-CAM reported: $line"
        }
        if ($line -match '^IMG ([0-9]+)$') {
            $length = [long]$Matches[1]
            if ($length -lt 4 -or $length -gt 2097152) {
                throw "Invalid JPEG length: $length"
            }
            $expectedBytes = [int]$length
        }
    }

    $imageBytes = New-Object byte[] $expectedBytes
    $receivedBytes = 0
    $deadline = [datetime]::UtcNow.AddSeconds(120)

    while ($receivedBytes -lt $expectedBytes) {
        if ([datetime]::UtcNow -ge $deadline) {
            throw "Incomplete transfer: $receivedBytes / $expectedBytes bytes. No JPG was saved."
        }
        try {
            $count = $connection.Read(
                $imageBytes, $receivedBytes,
                [Math]::Min(4096, $expectedBytes - $receivedBytes)
            )
            $receivedBytes += $count
        } catch [System.TimeoutException] {
            continue
        }
    }

    if ($imageBytes[0] -ne 255 -or $imageBytes[1] -ne 216 -or
        $imageBytes[$expectedBytes - 2] -ne 255 -or
        $imageBytes[$expectedBytes - 1] -ne 217) {
        throw 'JPEG start/end markers are missing. No JPG was saved. Check USB power/cable and retry.'
    }

    [void][System.IO.Directory]::CreateDirectory($OutputDirectory)
    $filename = 'photo_' + (Get-Date -Format 'yyyyMMdd_HHmmss_fff') + '.jpg'
    $savedImage = Join-Path $OutputDirectory $filename
    [System.IO.File]::WriteAllBytes($savedImage, $imageBytes)
    Write-Host "Saved $expectedBytes bytes to:"
    Write-Host $savedImage
} catch {
    Write-Host ("ERROR: " + $_.Exception.Message) -ForegroundColor Red
    Write-Host 'If access is denied, close Arduino Serial Monitor / Serial Plotter and retry.'
    exit 1
} finally {
    if ($connection.IsOpen) {
        $connection.Close()
    }
    $connection.Dispose()
}

if ($OpenImage -and $savedImage) {
    Invoke-Item -LiteralPath $savedImage
}
