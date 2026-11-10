param(
    [Parameter(Mandatory=$true)][string]$CamPort,
    [Parameter(Mandatory=$true)][string]$S3Port,
    [ValidateSet('Normal','DropAck','CorruptPacket')][string]$Case='Normal',
    [string]$OutputDirectory=(Join-Path $PSScriptRoot 'captures/dual-image')
)
$ErrorActionPreference='Stop'
if ($CamPort -eq $S3Port) { throw 'Two different device ports are required.' }
Add-Type -AssemblyName System.Drawing
if (-not ('CodexImageCrc32' -as [type])) {
    Add-Type -TypeDefinition @'
public static class CodexImageCrc32 {
    public static uint Compute(byte[] bytes) {
        uint crc=0xFFFFFFFFu;
        foreach(byte value in bytes) {
            crc ^= value;
            for(int bit=0;bit<8;bit++) crc=(crc>>1)^((crc&1)!=0?0xEDB88320u:0);
        }
        return ~crc;
    }
}
'@
}
[void][IO.Directory]::CreateDirectory($OutputDirectory)
$started=[DateTime]::UtcNow
$stamp=[TimeZoneInfo]::ConvertTimeFromUtc($started,
    [TimeZoneInfo]::FindSystemTimeZoneById('China Standard Time')).ToString('yyyyMMdd_HHmmss_fff')
$base=Join-Path $OutputDirectory ('dualimage_'+$stamp+'_'+$Case.ToLowerInvariant())
$clock=[Diagnostics.Stopwatch]::StartNew()
$nodes=@{}
foreach($role in @('CAM','S3')) {
    $port=New-Object IO.Ports.SerialPort
    $port.PortName=if($role -eq 'CAM'){$CamPort}else{$S3Port}
    $port.BaudRate=115200; $port.DtrEnable=$false; $port.RtsEnable=$false
    $port.ReadTimeout=500; $port.WriteTimeout=2000; $port.ReadBufferSize=65536
    $nodes[$role]=@{Role=$role; Port=$port; Buffer=''; Info=$null; State=$null
        Events=(New-Object 'Collections.Generic.List[object]')
        Log=(New-Object 'Collections.Generic.List[string]')}
}
$report=[ordered]@{
    schema='dual-esp-image-v1'; started_utc=$started.ToString('o'); case=$Case; pass=$false
    ports=@{CAM=$CamPort;S3=$S3Port}; serial_baud=115200; transport='ESP-NOW'
    packet_bytes=240; payload_bytes=200; channel=1; imu_acquisition=$false
    image_route='CAM capture -> ESP-NOW -> S3 reassembly -> USB UART -> Windows'
    control_scope='TEST_ONLY message and nonce, no AI or Uno command'
    time_scope='CAM frame times share CAM boot clock; gateway duration uses S3 clock; no inter-device subtraction'
    source_sha256=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'DualESP_Image_Check/DualESP_Image_Check.ino')).Hash
    tool_sha256=(Get-FileHash -LiteralPath $PSCommandPath).Hash
}
$runError=$null

function Process-Line($Node,[string]$Line) {
    $line=$Line.Trim()
    if($line -match '(?i)\bMAC\b'){$line='[device identifier omitted]'}
    $Node.Log.Add($line)
    if($line.StartsWith('FATAL ') -or $line.StartsWith('FRAME_ERROR ') -or $line.StartsWith('ERR_')) {
        throw ($Node.Role+': '+$line)
    }
    if($line -notmatch '^([A-Z_]+) '){return}
    $kind=$Matches[1]; $fields=@{}
    foreach($match in [regex]::Matches($line,'(?:^|\s)([a-z][a-z0-9_]*)=([^\s]+)')) {
        $fields[$match.Groups[1].Value]=$match.Groups[2].Value
    }
    $Node.Events.Add(@{Kind=$kind;Fields=$fields;HostMs=$clock.Elapsed.TotalMilliseconds})
    if($kind -eq 'INFO'){$Node.Info=$fields}
    if($kind -eq 'STATE'){$Node.State=$fields}
}
function Pump {
    foreach($role in @('CAM','S3')) {
        $node=$nodes[$role]; $node.Buffer+=$node.Port.ReadExisting()
        while(($i=$node.Buffer.IndexOf([char]10)) -ge 0) {
            $line=$node.Buffer.Substring(0,$i); $node.Buffer=$node.Buffer.Substring($i+1)
            Process-Line $node $line
        }
        if($node.Buffer.Length -gt 4096){throw 'Device text line too long.'}
    }
}
function Wait-For([scriptblock]$Predicate,[int]$Seconds,[string]$Description) {
    $deadline=$clock.Elapsed.TotalSeconds+$Seconds
    while($clock.Elapsed.TotalSeconds -lt $deadline) {
        Pump
        if(& $Predicate){return}
        Start-Sleep -Milliseconds 10
    }
    throw ('Timeout: '+$Description)
}
function Read-S3Line([double]$Deadline) {
    $line=New-Object Text.StringBuilder
    [void]$line.Append($nodes.S3.Buffer); $nodes.S3.Buffer=''
    while($clock.Elapsed.TotalSeconds -lt $Deadline) {
        try{$next=$nodes.S3.Port.ReadByte()}catch [TimeoutException]{continue}
        if($next -eq 10){$text=$line.ToString().Trim(); Process-Line $nodes.S3 $text; return $text}
        if($next -ne 13 -and $next -ge 0){[void]$line.Append([char]$next)}
        if($line.Length -gt 4096){throw 'USB text line too long.'}
    }
    throw 'Timeout reading S3 image header/trailer.'
}
function Fields([string]$Line) {
    $values=@{}
    foreach($m in [regex]::Matches($Line,'(?:^|\s)([a-z][a-z0-9_]*)=([^\s]+)')) {
        $values[$m.Groups[1].Value]=$m.Groups[2].Value
    }
    return $values
}

try {
    foreach($role in @('CAM','S3')){$nodes[$role].Port.Open()}
    $deadline=$clock.Elapsed.TotalSeconds+20; $queryAt=0.0; $ready=$false
    while($clock.Elapsed.TotalSeconds -lt $deadline) {
        if($clock.Elapsed.TotalSeconds -ge $queryAt) {
            foreach($role in @('CAM','S3')){$nodes[$role].Port.Write('INFO'+[char]10)}
            $queryAt=$clock.Elapsed.TotalSeconds+1
        }
        Pump; $ready=$true
        foreach($role in @('CAM','S3')) {
            $info=$nodes[$role].Info
            if($null -eq $info -or $info.fw -ne 'DualESP_Image_Check_v1' -or $info.role -ne $role -or
                $info.channel -ne '1' -or $info.packet_bytes -ne '240' -or $info.payload_bytes -ne '200' -or
                $info.paired -ne '1' -or $null -eq $nodes[$role].State){$ready=$false}
        }
        if($ready -and $nodes.CAM.Info.peer_boot -eq $nodes.S3.Info.boot -and
            $nodes.S3.Info.peer_boot -eq $nodes.CAM.Info.boot){break}
        $ready=$false; Start-Sleep -Milliseconds 10
    }
    if(!$ready){throw 'Expected image firmware/roles did not pair.'}
    $report.device_info=@{CAM=$nodes.CAM.Info;S3=$nodes.S3.Info}
    $report.initial_state=@{CAM=$nodes.CAM.State;S3=$nodes.S3.State}
    $camIndex=$nodes.CAM.Events.Count; $s3Index=$nodes.S3.Events.Count
    if($Case -eq 'DropAck') {
        $nodes.S3.Port.Write('FAULT_DROP_ACK 2'+[char]10)
        Wait-For {@($nodes.S3.Events|Select-Object -Skip $s3Index|Where-Object{$_.Kind -eq 'FAULT_ARMED'}).Count -gt 0} 5 'drop-ACK arm'
    } elseif($Case -eq 'CorruptPacket') {
        $nodes.CAM.Port.Write('FAULT_CORRUPT 2'+[char]10)
        Wait-For {@($nodes.CAM.Events|Select-Object -Skip $camIndex|Where-Object{$_.Kind -eq 'FAULT_ARMED'}).Count -gt 0} 5 'corruption arm'
    }
    $captureHostMs=$clock.Elapsed.TotalMilliseconds
    $nodes.S3.Port.Write('CAPTURE'+[char]10)
    Wait-For {@($nodes.S3.Events|Select-Object -Skip $s3Index|Where-Object{$_.Kind -eq 'CAPTURE_START'}).Count -eq 1} 5 'capture command'
    $request=(@($nodes.S3.Events|Select-Object -Skip $s3Index|Where-Object{$_.Kind -eq 'CAPTURE_START'})[0]).Fields.req
    Wait-For {
        @($nodes.S3.Events|Select-Object -Skip $s3Index|Where-Object{$_.Kind -eq 'IMAGE_READY' -and $_.Fields.req -eq $request}).Count -eq 1 -and
        @($nodes.CAM.Events|Select-Object -Skip $camIndex|Where-Object{$_.Kind -eq 'CAM_COMPLETE' -and $_.Fields.req -eq $request}).Count -eq 1
    } 45 'complete wireless image and END acknowledgement'
    $source=(@($nodes.CAM.Events|Select-Object -Skip $camIndex|Where-Object{$_.Kind -eq 'CAM_SOURCE' -and $_.Fields.req -eq $request})[0]).Fields
    $complete=(@($nodes.CAM.Events|Select-Object -Skip $camIndex|Where-Object{$_.Kind -eq 'CAM_COMPLETE' -and $_.Fields.req -eq $request})[0]).Fields
    $readyEvent=(@($nodes.S3.Events|Select-Object -Skip $s3Index|Where-Object{$_.Kind -eq 'IMAGE_READY' -and $_.Fields.req -eq $request})[0])
    $gateway=$readyEvent.Fields
    foreach($field in @('req','frame','bytes','chunks','crc32','sha256')) {
        if($source[$field] -ne $gateway[$field]){throw ('CAM/S3 source mismatch: '+$field)}
    }
    foreach($field in @('req','frame','bytes','chunks')) {
        if($source[$field] -ne $complete[$field]){throw ('CAM completion mismatch: '+$field)}
    }
    if($source.crc32 -notmatch '^[0-9A-Fa-f]{8}$' -or $source.sha256 -notmatch '^[0-9A-Fa-f]{64}$') {
        throw 'Source CRC32/SHA256 fields missing or invalid.'
    }
    $length=[int]$source.bytes
    if($length -lt 4 -or $length -gt 262144 -or [int]$source.chunks -ne [math]::Ceiling($length/200.0) -or
        [long]$source.frame_us -lt [long]$source.request_us -or [long]$source.acquired_us -lt [long]$source.frame_us){throw 'Source length/freshness/chunks invalid.'}
    $report.cam_source=$source; $report.cam_complete=$complete; $report.gateway_ready=$gateway
    $report.host_command_to_ready_ms=$readyEvent.HostMs-$captureHostMs

    # From DUMP until USB_DONE, read bytes exclusively. Never ReadExisting() on JPEG.
    $nodes.S3.Port.Write('DUMP'+[char]10)
    $deadline=$clock.Elapsed.TotalSeconds+10; $usb=$null
    do {
        $line=Read-S3Line $deadline
        if($line.StartsWith('USB_META ')){$usb=Fields $line}
    } until($line -match '^IMG (\d+)$')
    $declared=[int]$Matches[1]
    if($declared -ne $length -or $null -eq $usb){throw 'USB length/metadata invalid.'}
    foreach($field in @('req','frame','bytes','chunks','crc32','sha256')) {
        if($usb[$field] -ne $source[$field]){throw ('USB metadata mismatch: '+$field)}
    }
    $payload=New-Object byte[] $length; $received=0
    $payloadStart=$clock.Elapsed.TotalMilliseconds; $deadline=$clock.Elapsed.TotalSeconds+90
    while($received -lt $length) {
        if($clock.Elapsed.TotalSeconds -ge $deadline){throw 'USB image transfer timeout.'}
        try{$received+=$nodes.S3.Port.Read($payload,$received,[Math]::Min(4096,$length-$received))}
        catch [TimeoutException]{continue}
    }
    $payloadEnd=$clock.Elapsed.TotalMilliseconds
    $nodes.S3.Log.Add('<binary JPEG payload '+$received+' bytes omitted>')
    $deadline=$clock.Elapsed.TotalSeconds+5
    do{$line=Read-S3Line $deadline}until($line.StartsWith('USB_DONE '))
    $usbDone=Fields $line
    if($usbDone.req -ne $request -or $usbDone.frame -ne $source.frame -or [int]$usbDone.bytes -ne $length){throw 'USB trailer mismatch.'}
    $crc=[CodexImageCrc32]::Compute($payload).ToString('X8')
    $shaProvider=[Security.Cryptography.SHA256]::Create()
    try{$sha=[BitConverter]::ToString($shaProvider.ComputeHash($payload)).Replace('-','')}finally{$shaProvider.Dispose()}
    if($crc -ne $source.crc32 -or $sha -ne $source.sha256){throw 'PC/CAM image CRC32 or SHA256 mismatch.'}
    if($payload[0] -ne 255 -or $payload[1] -ne 216 -or $payload[$length-2] -ne 255 -or $payload[$length-1] -ne 217){throw 'JPEG marker error.'}
    $stream=New-Object IO.MemoryStream(,$payload); $imageObject=$null; $bitmap=$null
    try {
        $imageObject=[Drawing.Image]::FromStream($stream,$true,$true)
        $bitmap=New-Object Drawing.Bitmap $imageObject
        if($bitmap.Width -ne 640 -or $bitmap.Height -ne 480 -or $usb.width -ne '640' -or $usb.height -ne '480'){throw 'Decoded resolution mismatch.'}
        [void]$bitmap.GetPixel(320,240)
    } finally {
        if($null -ne $bitmap){$bitmap.Dispose()}; if($null -ne $imageObject){$imageObject.Dispose()}; $stream.Dispose()
    }
    $report.usb_meta=$usb; $report.usb_done=$usbDone; $report.pc_sha256=$sha; $report.pc_crc32=$crc
    $report.bytes=$length; $report.width=640; $report.height=480; $report.bitmap_decode_pass=$true
    $report.host_usb_payload_read_ms=$payloadEnd-$payloadStart
    if($Case -eq 'DropAck' -and ([int]$gateway.dropped_ack -ne 1 -or [int]$gateway.duplicate_chunks -lt 1 -or [int]$complete.retries -lt 1)){throw 'Dropped chunk ACK recovery not observed.'}
    if($Case -eq 'CorruptPacket' -and ([int]$complete.corruptions -ne 1 -or [int]$gateway.crc_rejects -ne 1 -or [int]$complete.retries -lt 1)){throw 'Packet CRC rejection/recovery not observed.'}
    if($Case -eq 'Normal' -and ([int]$complete.corruptions -ne 0 -or [int]$gateway.dropped_ack -ne 0)){throw 'Unexpected armed fault in normal case.'}
    $nonce=Get-Random -Minimum 1 -Maximum 2147483647
    $controlCam=$nodes.CAM.Events.Count; $controlS3=$nodes.S3.Events.Count
    $nodes.S3.Port.Write('CONTROL '+$nonce+[char]10)
    Wait-For {
        @($nodes.S3.Events|Select-Object -Skip $controlS3|Where-Object{$_.Kind -eq 'CONTROL_OK' -and $_.Fields.nonce -eq [string]$nonce}).Count -eq 1 -and
        @($nodes.CAM.Events|Select-Object -Skip $controlCam|Where-Object{$_.Kind -eq 'CONTROL_RX' -and $_.Fields.nonce -eq [string]$nonce}).Count -ge 1
    } 5 'reverse TEST_ONLY control message'
    $control=(@($nodes.S3.Events|Select-Object -Skip $controlS3|Where-Object{$_.Kind -eq 'CONTROL_OK' -and $_.Fields.nonce -eq [string]$nonce})[0]).Fields
    $matchingControl=@($nodes.CAM.Events|Select-Object -Skip $controlCam|Where-Object{
        $_.Kind -eq 'CONTROL_RX' -and $_.Fields.nonce -eq [string]$nonce -and
        $_.Fields.req -eq $control.req -and $_.Fields.text -eq 'TEST_ONLY'})
    if($matchingControl.Count -lt 1 -or $control.test_only -ne 'YES'){throw 'Reverse control identity mismatch.'}
    $report.reverse_control=$control; $report.reverse_control_pass=$true
    foreach($role in @('CAM','S3')){$nodes[$role].Port.Write('INFO'+[char]10)}
    $settle=$clock.Elapsed.TotalSeconds+0.3
    while($clock.Elapsed.TotalSeconds -lt $settle){Pump;Start-Sleep -Milliseconds 10}
    $report.final_state=@{CAM=$nodes.CAM.State;S3=$nodes.S3.State}
    foreach($role in @('CAM','S3')) {
        if($nodes[$role].Info.boot -ne $report.device_info[$role].boot){throw 'Node restarted during capture.'}
        foreach($counter in @('queue_drop','tx_queue_drop','tx_errors')) {
            if([long]$nodes[$role].State[$counter] -ne [long]$report.initial_state[$role][$counter]){throw ($role+' counter increased: '+$counter)}
        }
        $allowed=if($role -eq 'S3' -and $Case -eq 'CorruptPacket'){1}else{0}
        if([long]$nodes[$role].State.bad_packets-[long]$report.initial_state[$role].bad_packets -ne $allowed){throw 'Unexpected invalid packet count.'}
    }
    [IO.File]::WriteAllBytes(($base+'.jpg'),$payload)
    $report.photo=[IO.Path]::GetFileName($base+'.jpg'); $report.pass=$true
} catch {
    $runError=$_.Exception.Message; $report.error=$runError; $report.error_location=$_.ScriptStackTrace
} finally {
    foreach($role in @('CAM','S3')) {
        if($nodes[$role].Port.IsOpen){$nodes[$role].Port.Close()}; $nodes[$role].Port.Dispose()
        [IO.File]::WriteAllLines(($base+'_'+$role+'.txt'),$nodes[$role].Log.ToArray(),(New-Object Text.UTF8Encoding $false))
    }
    $report.finished_utc=[DateTime]::UtcNow.ToString('o'); $report.elapsed_s=$clock.Elapsed.TotalSeconds
    $report|ConvertTo-Json -Depth 10|Set-Content -LiteralPath ($base+'.json') -Encoding UTF8
}
if($null -ne $runError){Write-Output ('ERROR: '+$runError);Write-Output ('Report: '+$base+'.json');exit 1}
[ordered]@{pass=$report.pass;case=$Case;photo=$base+'.jpg';bytes=$report.bytes;sha256=$report.pc_sha256
    chunks=[int]$report.gateway_ready.chunks;retries=[int]$report.cam_complete.retries
    gateway_elapsed_ms=[long]$report.gateway_ready.gateway_elapsed_us/1000.0
    host_usb_payload_read_ms=$report.host_usb_payload_read_ms;reverse_control_pass=$true
    report=$base+'.json'}|ConvertTo-Json
