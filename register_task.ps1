# Invest Thermometer: run Tue-Sat 07:00 KST (after US market close).
# If the PC was off at 07:00, it runs as soon as the PC is on.
# To remove: Unregister-ScheduledTask -TaskName "InvestThermometer" -Confirm:$false
$py = (Get-Command python).Source -replace 'python\.exe$', 'pythonw.exe'
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$action = New-ScheduledTaskAction -Execute $py -Argument "`"$dir\thermometer.py`"" -WorkingDirectory $dir
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Tuesday,Wednesday,Thursday,Friday,Saturday -At 7:00am
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName "InvestThermometer" -Action $action -Trigger $trigger -Settings $settings `
    -Description "Invest Thermometer daily update" -Force | Out-Null
Write-Host "Registered. Next run:" (Get-ScheduledTaskInfo -TaskName "InvestThermometer").NextRunTime
