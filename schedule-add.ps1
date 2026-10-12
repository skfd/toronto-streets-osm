$taskName   = "kk-TorontoStreetsOSM"
$oldName    = "TorontoStreetsOSM"   # before the kk- prefix
$projectDir = $PSScriptRoot
$logFile    = "$projectDir\logs\scheduler.log"

if (-not (Test-Path "$projectDir\logs")) {
    New-Item -ItemType Directory -Path "$projectDir\logs" | Out-Null
}

if (Get-ScheduledTask -TaskName $oldName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $oldName -Confirm:$false
    Write-Host "Removed old task '$oldName'."
}

$action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c cd /d `"$projectDir`" && python run.py update >> `"$logFile`" 2>&1"

# Monthly is enough: street names change slowly on both sides, and each run
# adds one point to docs/history.jsonl. Day 1 at 13:45 stays clear of
# kk-ontario-update (12:00) and kk-SCOpenQuests (13:15).
#
# New-ScheduledTaskTrigger has no -Monthly, and Register-ScheduledTask rejects
# a hand-built MSFT_TaskMonthlyTrigger ("The parameter is incorrect"), so
# schtasks lays down the monthly trigger and Set-ScheduledTask fills in the
# real action and the settings schtasks cannot express.
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 2) -StartWhenAvailable

schtasks /Create /TN $taskName /SC MONTHLY /D 1 /ST 13:45 /TR "cmd.exe" /F | Out-Null
if ($LASTEXITCODE -ne 0) { throw "schtasks /Create failed ($LASTEXITCODE)" }
Set-ScheduledTask -TaskName $taskName -Action $action -Settings $settings | Out-Null

$next = (Get-ScheduledTaskInfo -TaskName $taskName).NextRunTime
Write-Host "Scheduled '$taskName' monthly, day 1 at 13:45. Next run: $next"
Write-Host "Log: $logFile"
