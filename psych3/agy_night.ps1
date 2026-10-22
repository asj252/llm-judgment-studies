param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$env:AGY_CLI_DISABLE_AUTO_UPDATE = 'true'
$stamp = [TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([DateTimeOffset]::Now, 'China Standard Time').ToString('yyyy-MM-dd')
$logDir = Join-Path $PSScriptRoot 'raw'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("psych3_agy_night_$stamp.log")
& $Python -I (Join-Path $PSScriptRoot 'agy_night.py') *>> $log
exit $LASTEXITCODE

# Recommendation only; this script never registers a task:
# 00:00 China Standard Time; repeat every 30 minutes for 7h40m;
# MultipleInstances=IgnoreNew. Do not configure a stop before 08:00:
# the Python supervisor owns the 08:00 process-tree deadline.
