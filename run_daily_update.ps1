# run_daily_update.ps1 — runs scripts/daily_live_update.py once, logging
# output to a timestamped file. This is what the Windows Scheduled Task
# (set up by scripts/setup_daily_task.ps1) actually invokes each day.

$env:MODEL_DIR = "C:\bethero_models"
$env:API_SPORTS_KEY = "4425c6faf96faad31706bdf167ded8c6"
$env:ODDS_API_KEY = "5f1a890725a8b04ca19a3f14ab549eac"

Set-Location $PSScriptRoot

$logDir = Join-Path $PSScriptRoot "logs\daily_update"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir ("{0}.log" -f (Get-Date -Format "yyyy-MM-dd_HHmmss"))

$env:PYTHONPATH = $PSScriptRoot
# *>&1 merges all native-process streams into the success stream first, then
# Out-File writes UTF-8 (PowerShell 5.1's own `*>` redirect defaults to
# UTF-16LE with BOM, which is unreadable to plain text tools).
python3 scripts\daily_live_update.py *>&1 | Out-File -FilePath $logFile -Encoding utf8

# Keep only the last 30 days of logs so this directory doesn't grow forever.
Get-ChildItem $logDir -Filter "*.log" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } |
    Remove-Item -Force
