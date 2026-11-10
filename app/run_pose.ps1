<#
.SYNOPSIS
Starts the unified vision and IMU application using this project's existing venv.
.EXAMPLE
powershell.exe -File app/run_pose.ps1 -CamPort COM3 -Action squat
#>
param(
    [string]$CamPort = 'COM3',
    [AllowEmptyString()][string]$ImuPort = 'COM4',
    [ValidateSet('squat')][string]$Action = 'squat',
    [ValidateRange(1024, 65535)][int]$WebPort = 8010
)
$ErrorActionPreference = 'Stop'
$pythonPath = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $pythonPath)) {
    throw 'Project venv not found. Follow app/README.md to set up the environment first.'
}
Write-Host "CAM=$CamPort IMU=$ImuPort action=$Action URL=http://127.0.0.1:$WebPort (Ctrl+C to stop)"
Push-Location -LiteralPath $PSScriptRoot
try {
    & $pythonPath -X utf8 main.py --source "serial://$CamPort" "--imu-port=$ImuPort" --action $Action --port $WebPort --no-browser
    $appExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}
exit $appExitCode
