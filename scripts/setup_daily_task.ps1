# setup_daily_task.ps1 — one-time setup: registers a Windows Scheduled Task
# that runs run_daily_update.ps1 every day at 06:00, keeping live fixtures,
# predictions, odds and accumulators fresh without any manual step.
#
# Run once, from an elevated (Administrator) PowerShell prompt:
#   powershell -ExecutionPolicy Bypass -File scripts\setup_daily_task.ps1
#
# To check it later:      Get-ScheduledTask -TaskName "BetHeroDailyUpdate"
# To run it immediately:  Start-ScheduledTask -TaskName "BetHeroDailyUpdate"
# To remove it:           Unregister-ScheduledTask -TaskName "BetHeroDailyUpdate"

$taskName = "BetHeroDailyUpdate"
$repoRoot = Split-Path -Parent $PSScriptRoot
$scriptPath = Join-Path $repoRoot "run_daily_update.ps1"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""

$trigger = New-ScheduledTaskTrigger -Daily -At 6:00AM

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 10)

Register-ScheduledTask -TaskName $taskName `
    -Action $action -Trigger $trigger -Settings $settings `
    -Description "Bet Hero: daily fixture/prediction/odds/accumulator refresh from API-Football" `
    -Force

Write-Host "Scheduled task '$taskName' registered - runs daily at 06:00."
Write-Host ("Logs land in: {0}\logs\daily_update" -f $repoRoot)
