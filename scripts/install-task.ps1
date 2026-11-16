param([string]$InstallRoot = 'C:\MeetingTranscriber')
$python = Join-Path $InstallRoot '.venv311\Scripts\pythonw.exe'
$argument = "-m uvicorn app.main:app --host 127.0.0.1 --port 8765"
$action = New-ScheduledTaskAction -Execute $python -Argument $argument -WorkingDirectory $InstallRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable
Register-ScheduledTask -TaskName 'MeetingTranscriber' -Action $action -Trigger $trigger -Settings $settings -Description 'Local Meeting Transcriber backend' -Force
Start-ScheduledTask -TaskName 'MeetingTranscriber'

