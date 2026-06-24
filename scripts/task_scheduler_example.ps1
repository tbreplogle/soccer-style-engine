# Example only. Review and edit before registering a Windows scheduled task.

$TaskName = "SoccerStyleEngineDailyPipeline"
$Repo = "C:\Users\tbrep\OneDrive\Documents\GitHub\soccer-style-engine"
$Script = Join-Path $Repo "scripts\run_daily_pipeline.ps1"

Write-Host "Review these values before running Register-ScheduledTask:"
Write-Host "Task name: $TaskName"
Write-Host "Repository: $Repo"
Write-Host "Script: $Script"

# Uncomment only after reviewing paths and account permissions.
# $Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Script`""
# $Trigger = New-ScheduledTaskTrigger -Daily -At 8:00AM
# Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Description "Run soccer-style-engine daily pipeline"
