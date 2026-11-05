param(
    [Parameter(Mandatory = $true)][string]$CamPort,
    [Parameter(Mandatory = $true)][string]$S3Port,
    [ValidateRange(1,50)][int]$Count = 20,
    [string]$OutputDirectory = (Join-Path $PSScriptRoot 'captures/dual-text')
)

$ErrorActionPreference = 'Stop'
if ($CamPort -eq $S3Port) { throw 'CAM and S3 must have different ports.' }
[void][IO.Directory]::CreateDirectory($OutputDirectory)
$started = [DateTime]::UtcNow
$stamp = [TimeZoneInfo]::ConvertTimeFromUtc($started,
    [TimeZoneInfo]::FindSystemTimeZoneById('China Standard Time')).ToString('yyyyMMdd_HHmmss_fff')
$outputBase = Join-Path $OutputDirectory ('dualtext_' + $stamp)
$clock = [Diagnostics.Stopwatch]::StartNew()
$nodes = @{}
foreach ($role in @('CAM','S3')) {
    $connection = New-Object IO.Ports.SerialPort
    $connection.PortName = if ($role -eq 'CAM') { $CamPort } else { $S3Port }
    $connection.BaudRate = 115200
    $connection.DtrEnable = $false
    $connection.RtsEnable = $false
    $connection.ReadTimeout = 500
    $connection.WriteTimeout = 2000
    $connection.ReadBufferSize = 65536
    $nodes[$role] = @{
        Role=$role; Connection=$connection; Buffer=''; Info=$null; State=$null
        Events=(New-Object 'Collections.Generic.List[object]')
        Log=(New-Object 'Collections.Generic.List[string]')
    }
}
$report = [ordered]@{
    schema='dual-esp-text-v1'; started_utc=$started.ToString('o'); pass=$false
    transport='ESP-NOW'; channel=1; packet_bytes=48
    ports=@{CAM=$CamPort; S3=$S3Port}; serial_baud=115200
    acquisition_running=$false
    latency_scope='Initiator local clock from first radio send to matching application ACK; includes retries, no inter-device clock synchronization'
    pairing_scope='Bench discovery by project magic/version/opposite role; no authentication or encrypted payload in this diagnostic'
    host_role='Only sends serial test commands and records both boards; does not relay radio messages'
    tool_sha256=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash
    sketch_sha256=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'DualESP_Text_Check/DualESP_Text_Check.ino') -Algorithm SHA256).Hash
    cases=(New-Object 'Collections.Generic.List[object]')
}
$runError = $null

function Pump {
    foreach ($role in @('CAM','S3')) {
        $node = $nodes[$role]
        $node.Buffer += $node.Connection.ReadExisting()
        while (($position = $node.Buffer.IndexOf([char]10)) -ge 0) {
            $line = $node.Buffer.Substring(0,$position).Trim()
            $node.Buffer = $node.Buffer.Substring($position + 1)
            if ($line -match '(?i)\bMAC\b') { $line = '[device identifier omitted]' }
            $node.Log.Add($line)
            if ($line.StartsWith('FATAL ') -or $line.StartsWith('ERR_')) {
                throw ($role + ': ' + $line)
            }
            if ($line -notmatch '^([A-Z_]+) ') { continue }
            $kind = $Matches[1]
            $fields = @{}
            foreach ($match in [regex]::Matches($line,'(?:^|\s)([a-z_]+)=([^\s]+)')) {
                $fields[$match.Groups[1].Value] = $match.Groups[2].Value
            }
            $node.Events.Add(@{Kind=$kind; Fields=$fields; HostMs=$clock.Elapsed.TotalMilliseconds})
            if ($kind -eq 'INFO') { $node.Info = $fields }
            if ($kind -eq 'STATE') { $node.State = $fields }
        }
        if ($node.Buffer.Length -gt 4096) { throw ($role + ' text line too long.') }
    }
}

function Wait-For([scriptblock]$Predicate,[int]$Seconds,[string]$Description) {
    $deadline = $clock.Elapsed.TotalSeconds + $Seconds
    while ($clock.Elapsed.TotalSeconds -lt $deadline) {
        Pump
        if (& $Predicate) { return }
        Start-Sleep -Milliseconds 10
    }
    throw ('Timeout: ' + $Description)
}

function Request-Info {
    foreach ($role in @('CAM','S3')) { $nodes[$role].Connection.Write('INFO' + [char]10) }
}

function Run-Case([string]$Initiator,[int]$Amount,[bool]$DropAck) {
    $remote = if ($Initiator -eq 'S3') { 'CAM' } else { 'S3' }
    $localNode = $nodes[$Initiator]
    $remoteNode = $nodes[$remote]
    $localIndex = $localNode.Events.Count
    $remoteIndex = $remoteNode.Events.Count
    if ($DropAck) {
        $remoteNode.Connection.Write('DROP_NEXT_ACK' + [char]10)
        Wait-For { @($remoteNode.Events | Select-Object -Skip $remoteIndex |
            Where-Object { $_.Kind -eq 'FAULT_ARMED' }).Count -gt 0 } 5 'fault arm'
    }
    Write-Output ('Testing ' + $Initiator + ' -> ' + $remote + ', count=' + $Amount + ', drop_one_ack=' + $DropAck)
    $localNode.Connection.Write('RUN ' + $Amount + [char]10)
    Wait-For { @($localNode.Events | Select-Object -Skip $localIndex |
        Where-Object { $_.Kind -eq 'RUN_DONE' }).Count -gt 0 } 75 'application ACK run'
    $settle = $clock.Elapsed.TotalSeconds + 0.15
    while ($clock.Elapsed.TotalSeconds -lt $settle) { Pump; Start-Sleep -Milliseconds 10 }
    $done = @($localNode.Events | Select-Object -Skip $localIndex |
        Where-Object { $_.Kind -eq 'RUN_DONE' })[-1].Fields
    $acks = @($localNode.Events | Select-Object -Skip $localIndex |
        Where-Object { $_.Kind -eq 'APP_ACK' -and $_.Fields.run -eq $done.run })
    $received = @($remoteNode.Events | Select-Object -Skip $remoteIndex |
        Where-Object { $_.Kind -eq 'APP_RX' -and $_.Fields.from -eq $Initiator -and
            [long]$_.Fields.seq -ge [long]$done.first_seq -and
            [long]$_.Fields.seq -le [long]$done.last_seq })
    if ([int]$done.count -ne $Amount -or [int]$done.acked -ne $Amount -or
        [int]$done.failed -ne 0 -or $acks.Count -ne $Amount) {
        throw ($Initiator + ' run did not receive all application ACKs.')
    }
    $transactions = New-Object 'Collections.Generic.List[object]'
    $sequences = New-Object 'Collections.Generic.HashSet[long]'
    foreach ($ack in $acks) {
        $a = $ack.Fields
        if (!$sequences.Add([long]$a.seq) -or $a.from -ne $remote -or
            $a.text -ne ('RECEIVED_BY_' + $remote) -or
            $a.from_boot -ne $remoteNode.Info.boot -or $a.target_boot -ne $localNode.Info.boot) {
            throw 'Application ACK role/text/session/uniqueness mismatch.'
        }
        $rxMatches = @($received | Where-Object { $_.Fields.seq -eq $a.seq -and
            $_.Fields.text -eq ('HELLO_FROM_' + $Initiator) -and
            $_.Fields.from_boot -eq $localNode.Info.boot -and
            $_.Fields.target_boot -eq $remoteNode.Info.boot })
        if ($rxMatches.Count -lt 1) { throw 'No corresponding remote APP_RX record.' }
        $transactions.Add([ordered]@{
            seq=[long]$a.seq; attempts=[int]$a.attempts; rtt_ms=[long]$a.rtt_us / 1000.0
            matching_remote_rx=$rxMatches.Count; reply=$a.text
        })
    }
    if ($sequences.Count -ne $Amount -or
        [long]$done.last_seq - [long]$done.first_seq + 1 -ne $Amount) { throw 'Sequence range mismatch.' }
    $duplicateCount = @($received | Where-Object { $_.Fields.duplicate -eq '1' }).Count
    $dropped = @($remoteNode.Events | Select-Object -Skip $remoteIndex |
        Where-Object { $_.Kind -eq 'FAULT_DROP_ACK' }).Count
    if ($DropAck -and ($dropped -ne 1 -or [int]$done.retries -lt 1 -or $duplicateCount -lt 1)) {
        throw 'Deliberate dropped ACK did not produce retry and duplicate recognition.'
    }
    # Measure numeric values explicitly; Windows PowerShell does not reliably
    # expose OrderedDictionary keys as Measure-Object properties.
    $rttStats = @($transactions.ToArray() | ForEach-Object {
        [double]$_['rtt_ms']
    }) | Measure-Object -Minimum -Maximum -Average
    $report.cases.Add([ordered]@{
        initiator=$Initiator; responder=$remote; deliberate_drop_ack=$DropAck; pass=$true
        requested=$Amount; acked=[int]$done.acked; failed=[int]$done.failed
        retries=[int]$done.retries; remote_duplicate_rx=$duplicateCount; deliberate_drops=$dropped
        first_seq=[long]$done.first_seq; last_seq=[long]$done.last_seq
        rtt_min_ms=$rttStats.Minimum; rtt_mean_ms=$rttStats.Average; rtt_max_ms=$rttStats.Maximum
        transactions=@($transactions.ToArray())
    })
    Write-Output ('PASS ' + $Initiator + ' -> ' + $remote + ': ' + $Amount + '/' + $Amount + ', retries=' + $done.retries)
}

try {
    foreach ($role in @('CAM','S3')) { $nodes[$role].Connection.Open() }
    $readyDeadline = $clock.Elapsed.TotalSeconds + 20
    $nextQuery = 0.0
    $ready = $false
    while ($clock.Elapsed.TotalSeconds -lt $readyDeadline) {
        if ($clock.Elapsed.TotalSeconds -ge $nextQuery) { Request-Info; $nextQuery=$clock.Elapsed.TotalSeconds+1 }
        Pump
        $ready = $true
        foreach ($role in @('CAM','S3')) {
            $info = $nodes[$role].Info
            if ($null -eq $info -or $info.fw -ne 'DualESP_Text_Check_v1' -or
                $info.role -ne $role -or $info.channel -ne '1' -or
                $info.packet_bytes -ne '48' -or $info.paired -ne '1' -or
                $null -eq $nodes[$role].State) { $ready=$false }
        }
        if ($ready -and $nodes.CAM.Info.peer_boot -eq $nodes.S3.Info.boot -and
            $nodes.S3.Info.peer_boot -eq $nodes.CAM.Info.boot) { break }
        $ready = $false
        Start-Sleep -Milliseconds 10
    }
    if (!$ready) { throw 'Both expected boards did not pair on channel 1.' }
    $report.device_info = @{ CAM=$nodes.CAM.Info; S3=$nodes.S3.Info }
    $report.initial_state = @{ CAM=$nodes.CAM.State; S3=$nodes.S3.State }
    Run-Case 'S3' $Count $false
    Run-Case 'CAM' $Count $false
    Run-Case 'S3' 1 $true
    Run-Case 'CAM' 1 $true
    Request-Info
    $finishWait = $clock.Elapsed.TotalSeconds + 0.3
    while ($clock.Elapsed.TotalSeconds -lt $finishWait) { Pump; Start-Sleep -Milliseconds 10 }
    $report.final_state = @{ CAM=$nodes.CAM.State; S3=$nodes.S3.State }
    foreach ($role in @('CAM','S3')) {
        if ($nodes[$role].State.boot -ne $report.device_info[$role].boot) { throw 'Node rebooted during test.' }
        foreach ($counter in @('rx_queue_drop','tx_queue_drop','bad_crc','invalid','tx_api_errors')) {
            if ([long]$nodes[$role].State[$counter] -ne [long]$report.initial_state[$role][$counter]) {
                throw ($role + ' error counter increased: ' + $counter)
            }
        }
    }
    $report.pass = $true
} catch {
    $runError = $_.Exception.Message
    $report.error = $runError
    $report.error_location = $_.ScriptStackTrace
} finally {
    foreach ($role in @('CAM','S3')) {
        if ($nodes[$role].Connection.IsOpen) { $nodes[$role].Connection.Close() }
        $nodes[$role].Connection.Dispose()
        [IO.File]::WriteAllLines(($outputBase + '_' + $role + '.txt'),
            $nodes[$role].Log.ToArray(),(New-Object Text.UTF8Encoding $false))
    }
    $report.finished_utc = [DateTime]::UtcNow.ToString('o')
    $report.elapsed_s = $clock.Elapsed.TotalSeconds
    $report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath ($outputBase + '.json') -Encoding UTF8
}
Write-Output ('Report: ' + $outputBase + '.json')
if ($null -ne $runError) { Write-Output ('ERROR: ' + $runError); exit 1 }
Write-Output 'PASS: bidirectional application replies, session/sequence matching and dropped-ACK recovery.'
