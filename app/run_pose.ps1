<#
.SYNOPSIS
Starts the current USB camera pose application using this project's existing venv.
.EXAMPLE
powershell.exe -File app/run_pose.ps1 -CamPort COM3 -Action squat
#>
param(
    [string]$CamPort = 'COM3',
    [ValidateSet('squat', 'pushup')][string]$Action = 'squat',
    [ValidateRange(1024, 65535)][int]$WebPort = 8010
)
$ErrorActionPreference = 'Stop'
$pythonPath = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $pythonPath)) {
    throw 'Project venv not found. Follow app/README.md to set up the environment first.'
}
Write-Host "CAM=$CamPort action=$Action URL=http://127.0.0.1:$WebPort (Ctrl+C to stop)"
Push-Location -LiteralPath $PSScriptRoot
try {
    & $pythonPath -X utf8 pose_app.py --source "serial://$CamPort" --action $Action --port $WebPort --no-browser
    $appExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}
exit $appExitCode
