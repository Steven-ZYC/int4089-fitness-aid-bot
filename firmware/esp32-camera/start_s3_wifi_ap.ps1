param([string]$S3Port='COM9')
$ErrorActionPreference='Stop'
# Run locally after accepting the temporary network switch. Do not log its output.
$rng=[Security.Cryptography.RandomNumberGenerator]::Create()
$random=New-Object byte[] 16
try{$rng.GetBytes($random)}finally{$rng.Dispose()}
$password=[BitConverter]::ToString($random).Replace('-','')
$port=New-Object IO.Ports.SerialPort $S3Port,115200
$port.DtrEnable=$false;$port.RtsEnable=$false
$clock=[Diagnostics.Stopwatch]::StartNew();$buffer='';$info=$false;$ready=$false
try{
    $port.Open();$queryAt=0.0
    while($clock.Elapsed.TotalSeconds -lt 8){
        if($clock.Elapsed.TotalSeconds -ge $queryAt){$port.Write("INFO`n");$queryAt=$clock.Elapsed.TotalSeconds+1}
        $buffer+=$port.ReadExisting()
        if($buffer -match 'FATAL '){throw 'Gateway initialization failed; inspect IMU before enabling Wi-Fi.'}
        if($buffer -match 'INFO fw=S3_WiFi_Gateway_Check_v1 role=S3 '){$info=$true;break}
        Start-Sleep -Milliseconds 30
    }
    if(-not $info){throw 'Expected Wi-Fi gateway firmware not detected; no AP command sent.'}
    $buffer='';$port.Write('AP_START '+$password+[char]10)
    $deadline=$clock.Elapsed.TotalSeconds+8
    while($clock.Elapsed.TotalSeconds -lt $deadline){
        $buffer+=$port.ReadExisting()
        if($buffer -match 'ERR_|FATAL '){throw 'AP startup failed.'}
        if($buffer -match 'AP_READY ssid=INT4089-S3-Yuankun ip=192.168.4.1 port=4089 channel=1'){$ready=$true;break}
        Start-Sleep -Milliseconds 30
    }
    if(-not $ready){throw 'AP startup response timed out.'}
}finally{if($port.IsOpen){$port.Close()};$port.Dispose()}
# Password is generated per run, kept in RAM and shown only to the local operator.
[pscustomobject]@{SSID='INT4089-S3-Yuankun';Password=$password;Address='192.168.4.1';Port=4089}
