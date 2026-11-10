param(
    [Parameter(Mandatory = $true)][string]$ReferenceJson,
    [Parameter(Mandatory = $true)][string]$ValidationJson,
    [Parameter(Mandatory = $true)][string]$OutputBase
)

$ErrorActionPreference = 'Stop'
$culture = [Globalization.CultureInfo]::InvariantCulture
$reference = Get-Content -LiteralPath $ReferenceJson -Raw | ConvertFrom-Json
$validation = Get-Content -LiteralPath $ValidationJson -Raw | ConvertFrom-Json
$referenceCsv = [IO.Path]::ChangeExtension($ReferenceJson, '.csv')
$validationCsv = [IO.Path]::ChangeExtension($ValidationJson, '.csv')
foreach ($outputPath in @(($OutputBase + '.csv'), ($OutputBase + '.json'))) {
    foreach ($inputPath in @($referenceCsv, $validationCsv, $ReferenceJson, $ValidationJson)) {
        if ([IO.Path]::GetFullPath($outputPath) -eq [IO.Path]::GetFullPath($inputPath)) {
            throw 'Output paths must differ from both raw input recordings.'
        }
    }
}
$referenceHash = (Get-FileHash -LiteralPath $referenceCsv -Algorithm SHA256).Hash
$validationHash = (Get-FileHash -LiteralPath $validationCsv -Algorithm SHA256).Hash
if ($referenceHash -eq $validationHash) { throw 'Use a separate physical recording for validation.' }

foreach ($recording in @($reference, $validation)) {
    if (-not $recording.transport_check_passed -or $recording.clipping_rows -ne 0) {
        throw 'Both source recordings must pass capture checks without clipping.'
    }
    if ($recording.accel_norm_g.mean -lt 0.85 -or $recording.accel_norm_g.mean -gt 1.15) {
        throw 'Acceleration norm does not support the requested stationary test.'
    }
    foreach ($axis in @('ax_g','ay_g','az_g')) {
        if ($recording.axes.$axis.stddev -gt 0.02) { throw 'Acceleration is too variable for this stationary check.' }
    }
    foreach ($axis in @('gx_dps','gy_dps','gz_dps')) {
        if ($recording.axes.$axis.stddev -gt 0.2 -or [math]::Abs($recording.axes.$axis.mean) -gt 5) {
            throw 'Gyroscope is too variable or too far from zero for this stationary check.'
        }
    }
}

$referenceRows = @(Import-Csv -LiteralPath $referenceCsv)
$validationRows = @(Import-Csv -LiteralPath $validationCsv)
if ($referenceRows.Count -ne $reference.valid_rows -or $validationRows.Count -ne $validation.valid_rows) {
    throw 'CSV row count differs from the accompanying capture summary.'
}
$axes = @('gx_dps','gy_dps','gz_dps')
$bias = [ordered]@{}
foreach ($axis in $axes) {
    $sum = 0.0
    foreach ($row in $referenceRows) { $sum += [double]::Parse($row.$axis, $culture) }
    $bias[$axis] = $sum / $referenceRows.Count
}

$rawSumSquares = 0.0
$correctedSumSquares = 0.0
$rawSums = [ordered]@{ gx_dps=0.0; gy_dps=0.0; gz_dps=0.0 }
$correctedSums = [ordered]@{ gx_dps=0.0; gy_dps=0.0; gz_dps=0.0 }
$correctedRows = foreach ($row in $validationRows) {
    foreach ($axis in $axes) {
        $raw = [double]::Parse($row.$axis, $culture)
        $corrected = $raw - $bias[$axis]
        $rawSums[$axis] += $raw
        $correctedSums[$axis] += $corrected
        $rawSumSquares += $raw * $raw
        $correctedSumSquares += $corrected * $corrected
        $row | Add-Member -NotePropertyName ($axis + '_corrected') -NotePropertyValue ($corrected.ToString('F6', $culture))
    }
    $row
}
$rawRms = [math]::Sqrt($rawSumSquares / $validationRows.Count)
$correctedRms = [math]::Sqrt($correctedSumSquares / $validationRows.Count)
$axisResults = [ordered]@{}
$passed = $correctedRms -lt $rawRms
foreach ($axis in $axes) {
    $residual = $correctedSums[$axis] / $validationRows.Count
    if ([math]::Abs($residual) -gt 0.1) { $passed = $false }
    $axisResults[$axis] = [ordered]@{
        reference_bias = $bias[$axis]
        validation_raw_mean = $rawSums[$axis] / $validationRows.Count
        validation_corrected_mean = $residual
    }
}

$outputParent = Split-Path -Parent ([IO.Path]::GetFullPath($OutputBase))
[void](New-Item -ItemType Directory -Path $outputParent -Force)
$correctedRows | Export-Csv -LiteralPath ($OutputBase + '.csv') -NoTypeInformation -Encoding UTF8
$report = [ordered]@{
    method = 'Host-side per-axis subtraction of the mean from a separate stationary reference'
    unit = 'deg/s'
    reference_label = $reference.label
    validation_label = $validation.label
    reference_sha256 = $referenceHash
    validation_sha256 = $validationHash
    reference_rows = $referenceRows.Count
    validation_rows = $validationRows.Count
    axes = $axisResults
    validation_vector_rms_before_dps = $rawRms
    validation_vector_rms_after_dps = $correctedRms
    prototype_check_passed = $passed
    corrected_mean_limit_dps = 0.1
    applied_to_s3_or_sensor_registers = $false
    note = 'Requires user-confirmed stillness. Statistical gates are prototype checks, not proof of no motion or a factory accuracy test. Only gyroscope zero-rate bias is checked; accelerometer calibration, scale factors, axis alignment and temperature stability remain separate tasks. Raw inputs remain unchanged.'
}
$reportJson = $report | ConvertTo-Json -Depth 5
[IO.File]::WriteAllText(($OutputBase + '.json'), $reportJson, (New-Object Text.UTF8Encoding($false)))
$reportJson
if (-not $passed) { throw 'Independent stationary bias check did not meet the documented prototype criteria.' }
