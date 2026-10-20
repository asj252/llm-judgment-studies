param(
    [string]$Deadline = '08:00',
    [double]$QuotaSkipHours = 2,
    # Minimum wait; auto_clear also applies per-model 30/60/120 minute backoff.
    [ValidateRange(0, 1440)][double]$RetryWaitMinutes = 30,
    [ValidateRange(1, 100)][int]$MaxRounds = 12,
    [string]$Agy = 'agy'
)
$ErrorActionPreference = 'Stop'
# Freeze the agy version for the experiment (value must be 'true'; '1' is ignored). Child processes inherit it.
$env:AGY_CLI_DISABLE_AUTO_UPDATE = 'true'
Set-Location -LiteralPath $PSScriptRoot
$logDir = Join-Path $PSScriptRoot 'raw'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$started = Get-Date
$logPath = Join-Path $logDir ('night_queue_{0}.log' -f $started.ToString('yyyy-MM-dd'))
$utf8 = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::AppendAllText($logPath, ('{0} START exit_code=pending{1}' -f $started.ToString('o'), [Environment]::NewLine), $utf8)
# cmd redirects native stderr as bytes; PowerShell 5.1 must not wrap it as ErrorRecord.
$queueScript = Join-Path $PSScriptRoot 'night_queue.py'
$quota = $QuotaSkipHours.ToString([System.Globalization.CultureInfo]::InvariantCulture)
$clearScript = Join-Path $PSScriptRoot 'auto_clear.py'
$deadlineAt = $started.Date.Add([TimeSpan]::Parse($Deadline))
function Invoke-LoggedPython([string]$Arguments) {
    $commandLine = '""python.exe" -u -X utf8 -B {0} >> "{1}" 2>&1"' -f $Arguments, $logPath
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo.FileName = $env:ComSpec
    $process.StartInfo.Arguments = '/d /s /c ' + $commandLine
    $process.StartInfo.UseShellExecute = $false
    $process.StartInfo.CreateNoWindow = $true
    [void]$process.Start()
    $process.WaitForExit()
    $code = $process.ExitCode
    $process.Dispose()
    return $code
}
$exitCode = 0
for ($round = 1; $round -le $MaxRounds; $round++) {
    [System.IO.File]::AppendAllText($logPath, ('{0} ROUND {1}{2}' -f (Get-Date).ToString('o'), $round, [Environment]::NewLine), $utf8)
    $queueArgs = '"{0}" --deadline "{1}" --quota-skip-hours "{2}" --agy "{3}"' -f $queueScript, $Deadline, $quota, $Agy
    $exitCode = Invoke-LoggedPython $queueArgs
    if ((Get-Date) -ge $deadlineAt -or $round -ge $MaxRounds) { break }
    $waitMinutes = $RetryWaitMinutes.ToString([System.Globalization.CultureInfo]::InvariantCulture)
    $clearArgs = '"{0}" --log-date "{1}" --retry-wait-minutes "{2}"' -f $clearScript, $started.ToString('yyyy-MM-dd'), $waitMinutes
    $clearCode = Invoke-LoggedPython $clearArgs
    if ($clearCode -notin @(0, 10)) { $exitCode = $clearCode; break }
    $wakeAt = (Get-Date).AddMinutes($RetryWaitMinutes)
    $retryAt = @()
    $statePath = Join-Path $logDir 'queue_state.json'
    if (Test-Path -LiteralPath $statePath) {
        $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
        $retryAt = @($state.models.PSObject.Properties.Value | Where-Object {
            -not $_.needs_review -and $_.stage -ne 'done' -and $_.skipped_until
        } | ForEach-Object { [DateTimeOffset]::Parse($_.skipped_until).LocalDateTime } | Sort-Object)
        if ($retryAt.Count -gt 0 -and $retryAt[0] -gt $wakeAt) { $wakeAt = $retryAt[0] }
    }
    if ($retryAt.Count -gt 0 -and $retryAt[0] -ge $deadlineAt) { break }
    if ($clearCode -eq 0 -and $retryAt.Count -eq 0) { break }
    while ((Get-Date) -lt $wakeAt -and (Get-Date) -lt $deadlineAt) {
        $seconds = [Math]::Min(60, [Math]::Min(($wakeAt - (Get-Date)).TotalSeconds, ($deadlineAt - (Get-Date)).TotalSeconds))
        if ($seconds -gt 0) { Start-Sleep -Milliseconds ([int][Math]::Ceiling($seconds * 1000)) }
    }
    if ((Get-Date) -ge $deadlineAt) { break }
}
[System.IO.File]::AppendAllText($logPath, ('{0} END exit_code={1}{2}' -f (Get-Date).ToString('o'), $exitCode, [Environment]::NewLine), $utf8)
exit $exitCode
