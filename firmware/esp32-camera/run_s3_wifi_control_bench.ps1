param([string]$S3Port='COM9',[string]$CamPort='COM11',
      [ValidateSet('Control','ImageImu')][string]$TestKind='Control',
      [Parameter(Mandatory=$true)][string]$OutputDirectory,
      [switch]$SwitchWifi)
$ErrorActionPreference='Stop'
if(-not $SwitchWifi){throw 'Choose the temporary Wi-Fi switch before running this bench.'}
[void][IO.Directory]::CreateDirectory($OutputDirectory)
$snapshot=@(& netsh wlan show interfaces)
$restoreProfile=($snapshot|Where-Object{$_ -match '^\s*Profile\s*:'}|Select-Object -First 1) -replace '^\s*Profile\s*:\s*',''
$iface=($snapshot|Where-Object{$_ -match '^\s*Name\s*:'}|Select-Object -First 1) -replace '^\s*Name\s*:\s*',''
$restoreProfile=$restoreProfile.Trim();$iface=$iface.Trim()
if(-not $restoreProfile -or -not $iface){throw 'Could not identify the original WLAN profile safely; network unchanged.'}
$profile='INT4089-Bench-'+[Guid]::NewGuid().ToString('N')
$xmlPath=Join-Path ([IO.Path]::GetTempPath()) ($profile+'.xml')
$result=[ordered]@{schema='wifi-switch-bench-v1';started_utc=[DateTime]::UtcNow.ToString('o');pass=$false;test_kind=$TestKind;orchestrator_sha256=(Get-FileHash -LiteralPath $PSCommandPath).Hash;wifi_switched=$false;original_network_restored=$false;temporary_profile_removed=$false;ap_stopped=$false}
$proc=$null;$ap=$null;$childCode=-1;$failure=$null
try{
 $ap=& (Join-Path $PSScriptRoot 'start_s3_wifi_ap.ps1') -S3Port $S3Port
 $xml=@"
<?xml version="1.0"?><WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1"><name>$profile</name><SSIDConfig><SSID><name>INT4089-S3-Yuankun</name></SSID></SSIDConfig><connectionType>ESS</connectionType><connectionMode>manual</connectionMode><MSM><security><authEncryption><authentication>WPA2PSK</authentication><encryption>AES</encryption><useOneX>false</useOneX></authEncryption><sharedKey><keyType>passPhrase</keyType><protected>false</protected><keyMaterial>$($ap.Password)</keyMaterial></sharedKey></security></MSM></WLANProfile>
"@
 [IO.File]::WriteAllText($xmlPath,$xml,(New-Object Text.UTF8Encoding $false));$xml=$null
 & netsh wlan add profile "filename=$xmlPath" user=current | Out-Null
 if($LASTEXITCODE -ne 0){throw 'Temporary WLAN profile could not be added'}
 & netsh wlan connect "name=$profile" "interface=$iface" | Out-Null
 if($LASTEXITCODE -ne 0){throw 'Could not request S3 WLAN connection'}
 $end=[DateTime]::UtcNow.AddSeconds(12);$connected=$false
 do{
  Start-Sleep -Milliseconds 500
  $state=@(& netsh wlan show interfaces)
  if(@($state|Where-Object{$_ -match '^\s*SSID\s*:\s*INT4089-S3-Yuankun\s*$'}).Count){$connected=$true;break}
 }while([DateTime]::UtcNow -lt $end)
 if(-not $connected){throw 'S3 WLAN association timed out'}
 $result.wifi_switched=$true;Start-Sleep -Milliseconds 1200
 $testName=if($TestKind -eq 'ImageImu'){'test_s3_wifi_gateway.ps1'}else{'test_s3_wifi_control.ps1'}
 $test=(Join-Path $PSScriptRoot $testName).Replace("'","''")
 $dest=$OutputDirectory.Replace("'","''");$port=$CamPort.Replace("'","''")
 $command="& '$test' -CamPort '$port' -OutputDirectory '$dest'; exit `$LASTEXITCODE"
 $encoded=[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
 $proc=Start-Process -FilePath powershell.exe -WindowStyle Hidden -PassThru -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-EncodedCommand',$encoded) -RedirectStandardOutput (Join-Path $OutputDirectory 'control_console.txt') -RedirectStandardError (Join-Path $OutputDirectory 'control_errors.txt')
 $null=$proc.Handle
 if(-not $proc.WaitForExit(25000)){Stop-Process -Id $proc.Id -Force;throw 'Network test exceeded 25 seconds'}
 $childCode=$proc.ExitCode
 $reportPattern=if($TestKind -eq 'ImageImu'){'wifigateway_*.json'}else{'wifi_control_*.json'}
 $childReport=Get-ChildItem -LiteralPath $OutputDirectory -Filter $reportPattern|Sort-Object LastWriteTimeUtc -Descending|Select-Object -First 1
 if(-not $childReport){throw 'Missing child test report'}
 $verified=Get-Content -LiteralPath $childReport.FullName -Raw -Encoding UTF8|ConvertFrom-Json
 if(-not $verified.pass -or [DateTime]$verified.started_utc -lt [DateTime]$result.started_utc){throw 'Child report failed or belongs to another run'}
 $result.control_report=$childReport.Name
 if($null -ne $childCode -and $childCode -ne 0){throw 'Network control process failed'}
 $result.pass=$true
}catch{$failure=$_.Exception.Message;$result.error=$failure}
finally{
 if($proc -and -not $proc.HasExited){Stop-Process -Id $proc.Id -Force}
 & netsh wlan connect "name=$restoreProfile" "interface=$iface" | Out-Null
 & netsh wlan delete profile "name=$profile" | Out-Null
 $result.temporary_profile_removed=$LASTEXITCODE -eq 0
 if(Test-Path -LiteralPath $xmlPath){Remove-Item -LiteralPath $xmlPath -Force}
 $ap=$null
 try{
  Start-Sleep -Milliseconds 400
  $serial=New-Object IO.Ports.SerialPort $S3Port,115200;$serial.DtrEnable=$false;$serial.RtsEnable=$false
  try{$serial.Open();$serial.Write("AP_STOP`n");Start-Sleep -Milliseconds 500;$result.ap_stopped=$serial.ReadExisting() -match 'AP_OFF'}finally{$serial.Dispose()}
 }catch{$result.ap_stop_error=$_.Exception.Message}
 try {
  $end=[DateTime]::UtcNow.AddSeconds(20)
  & netsh wlan connect "name=$restoreProfile" "interface=$iface" | Out-Null
  do {
   Start-Sleep -Milliseconds 500
   $returned=@(& netsh wlan show interfaces)
   $active=(($returned|Where-Object{$_ -match '^\s*Profile\s*:'}|Select-Object -First 1) -replace '^\s*Profile\s*:\s*','').Trim()
   if($active -eq $restoreProfile){$result.original_network_restored=$true;break}
  }while([DateTime]::UtcNow -lt $end)
 }catch{$result.restore_check_error=$_.Exception.Message}
 if(-not $result.original_network_restored -or -not $result.ap_stopped){$result.pass=$false}
 $result.finished_utc=[DateTime]::UtcNow.ToString('o')
 $result|ConvertTo-Json -Depth 5|Set-Content -LiteralPath (Join-Path $OutputDirectory 'switch_summary.json') -Encoding UTF8
}
$result|ConvertTo-Json -Depth 5
if(-not $result.pass){exit 1}
