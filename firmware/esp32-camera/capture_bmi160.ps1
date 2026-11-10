param(
    [string]$Port = 'COM4',
    [ValidateRange(10, 120)][int]$Seconds = 15,
    [ValidatePattern('^[a-zA-Z0-9_-]+$')][string]$Label = 'observation',
    [string]$OutputDirectory = (Join-Path $PSScriptRoot 'captures\bmi160')
)

$ErrorActionPreference = 'Stop'
$culture = [Globalization.CultureInfo]::InvariantCulture
$header = 'sample_seq,t_read_us,sensor_ticks,ax_raw,ay_raw,az_raw,gx_raw,gy_raw,gz_raw,ax_g,ay_g,az_g,gx_dps,gy_dps,gz_dps'
$stamp = [TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([datetime]::UtcNow, 'Singapore Standard Time').ToString('yyyyMMdd_HHmmss_fff')
[void](New-Item -ItemType Directory -Path $OutputDirectory -Force)
$basePath = Join-Path $OutputDirectory ($Label + '_' + $stamp)
$csvLines = New-Object 'System.Collections.Generic.List[string]'
$serialLines = New-Object 'System.Collections.Generic.List[string]'
$samples = New-Object 'System.Collections.Generic.List[object]'
[void]$csvLines.Add($header)
$badRows = 0
$startupFragments = 0
$configReports = 0
$detectedAddress = $null
$diagnosticErrors = 0
$connection = New-Object IO.Ports.SerialPort($Port, 115200)
$connection.ReadTimeout = 1000
$connection.DtrEnable = $false
$connection.RtsEnable = $false
$portOpenUtc = [datetime]::UtcNow.ToString('o')
$captureStartUtc = $null
$recordingClock = $null

try {
    $connection.Open()
    $stopwatch = [Diagnostics.Stopwatch]::StartNew()
    # A serial-open/reset can spend about two seconds starting the firmware.
    # Bound startup wait separately; count the requested duration from real data.
    while ($stopwatch.Elapsed.TotalSeconds -lt ($Seconds + 8)) {
        if ($null -eq $recordingClock) {
            if ($stopwatch.Elapsed.TotalSeconds -ge 8) { break }
        } elseif ($recordingClock.Elapsed.TotalSeconds -ge $Seconds) { break }
        try { $line = $connection.ReadLine().Trim() }
        catch [TimeoutException] { continue }
        if (-not $line) { continue }
        # Only retain this firmware's diagnostic/schema/numeric output.
        if ($line.StartsWith('# ')) {
            [void]$serialLines.Add($line)
            if ($line.StartsWith('# CONFIG ')) {
                $validConfig = $true
                $fields = $line -split ' '
                $addresses = @($fields | Where-Object { $_ -match '^address=0x(?:68|69)$' })
                if ($addresses.Count -ne 1) { $validConfig = $false }
                elseif ($null -eq $detectedAddress) { $detectedAddress = $addresses[0] }
                elseif ($detectedAddress -ne $addresses[0]) { $validConfig = $false }
                foreach ($field in @('firmware=BMI160_SixAxis_v3_autoaddr', 'chip_id=0xD1',
                        'acc_conf=0x27', 'acc_range=0x05', 'gyr_conf=0x27', 'gyr_range=0x02',
                        'pmu=0x14', 'err=0x00', 'odr_hz=50', 'calibrated=NO')) {
                    if (($line -split ' ') -notcontains $field) { $validConfig = $false }
                }
                if ($validConfig) { $configReports += 1 } else { $diagnosticErrors += 1 }
            }
            if ($line.StartsWith('# FATAL ') -or
                    ($line.StartsWith('# STATS ') -and $line -notmatch '\bread_errors=0(?:\s|$)')) {
                $diagnosticErrors += 1
            }
            continue
        }
        if ($line -eq $header) { continue }
        if ($line -notmatch '^\d+,') { continue }
        [void]$serialLines.Add($line)
        $parts = $line.Split(',')
        if ($parts.Count -ne 15) {
            if ($null -eq $recordingClock) { $startupFragments += 1 }
            else { $badRows += 1 }
            continue
        }
        try {
            $values = @($parts | ForEach-Object { [double]::Parse($_, $culture) })
            if (@($values | Where-Object { [double]::IsNaN($_) -or [double]::IsInfinity($_) }).Count) {
                throw 'Non-finite value'
            }
            if ($values[0] -lt 1 -or $values[1] -lt 0 -or
                    $values[2] -lt 0 -or $values[2] -gt 16777215) { throw 'Invalid sequence or clock' }
            for ($axisIndex = 3; $axisIndex -le 8; $axisIndex++) {
                if ($values[$axisIndex] -lt -32768 -or $values[$axisIndex] -gt 32767) { throw 'Invalid int16 sample' }
            }
            $norm = [math]::Sqrt($values[9]*$values[9] + $values[10]*$values[10] + $values[11]*$values[11])
            if ($null -eq $recordingClock) {
                $captureStartUtc = [datetime]::UtcNow.ToString('o')
                $recordingClock = [Diagnostics.Stopwatch]::StartNew()
            }
            [void]$samples.Add([pscustomobject]@{ Values = $values; AccelNorm = $norm })
            [void]$csvLines.Add($line)
        } catch {
            if ($null -eq $recordingClock) { $startupFragments += 1 }
            else { $badRows += 1 }
        }
    }
} finally {
    if ($connection.IsOpen) { $connection.Close() }
    $connection.Dispose()
    $utf8 = New-Object Text.UTF8Encoding($false)
    [IO.File]::WriteAllText(($basePath + '.csv'), (($csvLines -join "`n") + "`n"), $utf8)
    [IO.File]::WriteAllText(($basePath + '.log'), (($serialLines -join "`n") + "`n"), $utf8)
}

if ($samples.Count -lt 2) { throw "Not enough samples; inspect $basePath.log" }

function Get-Statistics([double[]]$Numbers) {
    $mean = ($Numbers | Measure-Object -Average).Average
    $squared = 0.0
    foreach ($number in $Numbers) { $squared += ($number - $mean) * ($number - $mean) }
    $bounds = $Numbers | Measure-Object -Minimum -Maximum
    return [ordered]@{ mean = $mean; stddev = [math]::Sqrt($squared / ($Numbers.Count - 1)); min = $bounds.Minimum; max = $bounds.Maximum }
}

$intervals = New-Object 'System.Collections.Generic.List[double]'
$sequenceGaps = 0
$nonmonotonic = 0
for ($i = 1; $i -lt $samples.Count; $i++) {
    $delta = $samples[$i].Values[1] - $samples[$i-1].Values[1]
    [void]$intervals.Add($delta)
    if ($delta -le 0) { $nonmonotonic += 1 }
    $sequenceDelta = $samples[$i].Values[0] - $samples[$i-1].Values[0]
    if ($sequenceDelta -ne 1) { $sequenceGaps += 1 }
}
$spanUs = $samples[$samples.Count-1].Values[1] - $samples[0].Values[1]
$rate = if ($spanUs -gt 0) { ($samples.Count - 1) * 1000000.0 / $spanUs } else { 0.0 }
$axisStatistics = [ordered]@{}
$axisNames = @('ax_g','ay_g','az_g','gx_dps','gy_dps','gz_dps')
for ($axisIndex = 0; $axisIndex -lt 6; $axisIndex++) {
    $columnIndex = 9 + $axisIndex
    $axisStatistics[$axisNames[$axisIndex]] = Get-Statistics @($samples | ForEach-Object { $_.Values[$columnIndex] })
}
$normStatistics = Get-Statistics @($samples | ForEach-Object { $_.AccelNorm })
$largeReadGaps = @($intervals | Where-Object { $_ -gt 30000 }).Count
$clippingRows = @($samples | Where-Object {
    @($_.Values[3..8] | Where-Object { [math]::Abs($_) -ge 32760 }).Count -gt 0
}).Count
$transportPass = $samples.Count -ge ($Seconds * 40) -and $configReports -gt 0 -and
    $badRows -eq 0 -and $diagnosticErrors -eq 0 -and $sequenceGaps -eq 0 -and
    $nonmonotonic -eq 0 -and $rate -ge 45 -and $rate -le 55 -and $largeReadGaps -eq 0

$summary = [ordered]@{
    label = $Label
    port_open_utc = $portOpenUtc
    capture_start_utc = $captureStartUtc
    port = $Port
    address = $detectedAddress
    requested_seconds = $Seconds
    valid_rows = $samples.Count
    config_reports = $configReports
    malformed_rows = $badRows
    startup_fragments = $startupFragments
    diagnostic_errors = $diagnosticErrors
    sequence_discontinuities = $sequenceGaps
    nonmonotonic_read_times = $nonmonotonic
    read_span_seconds = $spanUs / 1000000.0
    measured_read_rate_hz = $rate
    read_interval_us = (Get-Statistics $intervals.ToArray())
    read_intervals_over_30ms = $largeReadGaps
    clipping_rows = $clippingRows
    accel_norm_g = $normStatistics
    axes = $axisStatistics
    transport_check_passed = $transportPass
    calibrated = $false
    note = 'Uncorrected data. S3 read-start timestamps and BMI160 read-time clock are separate time domains. Read gaps flag delivery timing, not an exact count of internally lost sensor samples. Stationary/motion labels describe the requested physical test, not automatic proof of stillness or calibration.'
}
$summaryJson = $summary | ConvertTo-Json -Depth 6
[IO.File]::WriteAllText(($basePath + '.json'), $summaryJson, (New-Object Text.UTF8Encoding($false)))
$summaryJson
Write-Output ("CSV: " + $basePath + '.csv')
Write-Output ("Summary: " + $basePath + '.json')
if (-not $transportPass) { throw 'Capture recorded, but rate/configuration/continuity checks did not all pass; inspect the saved files.' }
