param([string]$CamPort='COM11',[string]$GatewayAddress='192.168.4.1',[int]$GatewayPort=4089,
      [string]$OutputDirectory=(Join-Path $PSScriptRoot 'captures/wifi-control'))
$ErrorActionPreference='Stop'
if(-not ('CodexBenchTcpPort' -as [type])){Add-Type -Path (Join-Path $PSScriptRoot 'tcp_port.cs')}
[void][IO.Directory]::CreateDirectory($OutputDirectory)
$base=Join-Path $OutputDirectory ('wifi_control_'+[DateTime]::UtcNow.ToString('yyyyMMdd_HHmmss_fff')+'Z')
$clock=[Diagnostics.Stopwatch]::StartNew();$nodes=@{}
$tcp=New-Object CodexBenchTcpPort;$tcp.Host=$GatewayAddress;$tcp.PortNumber=$GatewayPort
$cam=New-Object IO.Ports.SerialPort $CamPort,115200;$cam.DtrEnable=$false;$cam.RtsEnable=$false
foreach($role in @('CAM','S3')){$nodes[$role]=@{Port=$(if($role -eq 'CAM'){$cam}else{$tcp});Buffer='';Info=$null;Link=$null;State=$null;Events=(New-Object 'Collections.Generic.List[object]');Log=(New-Object 'Collections.Generic.List[string]')}}
$report=[ordered]@{schema='wifi-control-only-v1';started_utc=[DateTime]::UtcNow.ToString('o');pass=$false;scope='Wi-Fi/TCP and TEST_ONLY return path; no image/IMU payload';image_tested=$false;imu_data_tested=$false;tool_sha256=(Get-FileHash -LiteralPath $PSCommandPath).Hash;adapter_sha256=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'tcp_port.cs')).Hash}
function Pump {
 foreach($role in @('CAM','S3')){
  $n=$nodes[$role];$n.Buffer+=$n.Port.ReadExisting()
  while(($i=$n.Buffer.IndexOf([char]10)) -ge 0){
   $line=$n.Buffer.Substring(0,$i).Trim();$n.Buffer=$n.Buffer.Substring($i+1)
   if($line -match '(?i)\bMAC\b'){$line='[identifier omitted]'}
   $n.Log.Add($line)
   if($line -match '^(FATAL |FRAME_ERROR |ERR_)'){throw ($role+': '+$line)}
   if($line -notmatch '^([A-Z_]+) '){continue};$kind=$Matches[1];$fields=@{}
   foreach($m in [regex]::Matches($line,'(?:^|\s)([a-z][a-z0-9_]*)=([^\s]+)')){$fields[$m.Groups[1].Value]=$m.Groups[2].Value}
   $n.Events.Add(@{Kind=$kind;Fields=$fields})
   if($kind -eq 'INFO'){$n.Info=$fields};if($kind -eq 'LINK'){$n.Link=$fields};if($kind -eq 'STATE'){$n.State=$fields}
  }
 }
}
function Until([scriptblock]$predicate,[int]$seconds){$end=$clock.Elapsed.TotalSeconds+$seconds;while($clock.Elapsed.TotalSeconds -lt $end){Pump;if(& $predicate){return};Start-Sleep -Milliseconds 10};throw 'Timed out waiting for device response'}
function Control {
 $startS3=$nodes.S3.Events.Count;$startCam=$nodes.CAM.Events.Count;$nonce=Get-Random -Minimum 1 -Maximum 2147483647
 $nodes.S3.Port.Write('CONTROL '+$nonce+[char]10)
 Until { @($nodes.S3.Events|Select-Object -Skip $startS3|Where-Object{$_.Kind -eq 'CONTROL_OK' -and $_.Fields.nonce -eq [string]$nonce}).Count -eq 1 -and @($nodes.CAM.Events|Select-Object -Skip $startCam|Where-Object{$_.Kind -eq 'CONTROL_RX' -and $_.Fields.nonce -eq [string]$nonce}).Count -ge 1 } 4
 $ack=(@($nodes.S3.Events|Select-Object -Skip $startS3|Where-Object{$_.Kind -eq 'CONTROL_OK' -and $_.Fields.nonce -eq [string]$nonce})[0]).Fields
 if($ack.test_only -ne 'YES' -or @($nodes.CAM.Events|Select-Object -Skip $startCam|Where-Object{$_.Kind -eq 'CONTROL_RX' -and $_.Fields.nonce -eq [string]$nonce -and $_.Fields.req -eq $ack.req -and $_.Fields.text -eq 'TEST_ONLY'}).Count -lt 1){throw 'Control identity mismatch'}
 return $ack
}
$failure=$null
try{
 $cam.Open();$tcp.Open()
 $next=0.0;$end=$clock.Elapsed.TotalSeconds+12
 while($clock.Elapsed.TotalSeconds -lt $end){
  if($clock.Elapsed.TotalSeconds -ge $next){$cam.Write("INFO`n");$tcp.Write("INFO`n");$next=$clock.Elapsed.TotalSeconds+1}
  Pump
  if($nodes.CAM.Info.paired -eq '1' -and $nodes.S3.Info.paired -eq '1' -and $nodes.S3.Link.transport -eq 'TCP' -and $nodes.S3.Info.peer_boot -eq $nodes.CAM.Info.boot -and $nodes.CAM.Info.peer_boot -eq $nodes.S3.Info.boot){break}
  Start-Sleep -Milliseconds 10
 }
 if($nodes.S3.Info.fw -ne 'S3_WiFi_Gateway_Check_v1' -or $nodes.CAM.Info.fw -ne 'DualESP_Image_Check_v1' -or $nodes.S3.Link.transport -ne 'TCP' -or $nodes.S3.Info.peer_boot -ne $nodes.CAM.Info.boot -or $nodes.CAM.Info.peer_boot -ne $nodes.S3.Info.boot){throw 'Firmware/paired boot/link mismatch'}
 $report.device_info=@{S3=$nodes.S3.Info;CAM=$nodes.CAM.Info};$report.initial_link=$nodes.S3.Link
 $report.initial_state=@{S3=$nodes.S3.State;CAM=$nodes.CAM.State}
 $controls=New-Object 'Collections.Generic.List[object]'
 for($i=0;$i -lt 5;$i++){$controls.Add((Control))}
 $report.controls=$controls.ToArray()
 $tcp.Close();$nodes.S3.Buffer='';Start-Sleep -Milliseconds 350
 $tcp.Open();$tcp.Write("INFO`n")
 Until {$nodes.S3.Link.sessions -ge 2 -and [int]$nodes.S3.Link.disconnects -ge 1} 4
 if($nodes.S3.Info.boot -ne $report.device_info.S3.boot){throw 'Board restarted'}
 $report.reconnect_control=Control;$report.reconnect_link=$nodes.S3.Link
 $report.tcp_reconnect_pass=$true
 $tcp.Write("INFO`n");$cam.Write("INFO`n");$end=$clock.Elapsed.TotalSeconds+0.2
 while($clock.Elapsed.TotalSeconds -lt $end){Pump;Start-Sleep -Milliseconds 10}
 $report.final_state=@{S3=$nodes.S3.State;CAM=$nodes.CAM.State}
 foreach($role in @('S3','CAM')){foreach($counter in @('queue_drop','tx_queue_drop','tx_errors','radio_fail','bad_packets')){if($nodes[$role].State[$counter] -ne $report.initial_state[$role][$counter]){throw 'Radio counter increased'}}}
 $report.pass=$true
}catch{$failure=$_.Exception.Message;$report.error=$failure;$report.error_location=$_.ScriptStackTrace}
finally{
 foreach($role in @('CAM','S3')){$nodes[$role].Port.Dispose();[IO.File]::WriteAllLines(($base+'_'+$role+'.txt'),$nodes[$role].Log.ToArray(),(New-Object Text.UTF8Encoding $false))}
 $report.finished_utc=[DateTime]::UtcNow.ToString('o');$report.elapsed_s=$clock.Elapsed.TotalSeconds
 $report|ConvertTo-Json -Depth 10|Set-Content -LiteralPath ($base+'.json') -Encoding UTF8
}
if($failure){Write-Output ('FAILED: '+$failure);exit 1}
[ordered]@{pass=$report.pass;imu=$report.device_info.S3.imu;controls=5;tcp_reconnect=$report.tcp_reconnect_pass;report=$base+'.json'}|ConvertTo-Json
