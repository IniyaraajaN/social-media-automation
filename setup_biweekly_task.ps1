$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$taskName = "Social Media Biweekly Demo Report"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Project Python environment not found. Run the setup commands in README.md first."
}

$action = New-ScheduledTaskAction `
    -Execute $pythonPath `
    -Argument "-m src.report" `
    -WorkingDirectory $projectRoot

$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -WeeksInterval 2 `
    -DaysOfWeek Monday `
    -At "9:00AM"

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Generates the clearly labeled simulated Instagram bi-weekly report." `
    -Force | Out-Null

Write-Host "Scheduled '$taskName' every other Monday at 9:00 AM."
Write-Host "The computer must be awake for the task to run."
