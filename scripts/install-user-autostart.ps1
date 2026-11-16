param([string]$InstallRoot = 'C:\MeetingTranscriber')
$python = Join-Path $InstallRoot '.venv311\Scripts\pythonw.exe'
$server = Join-Path $InstallRoot 'run_server.py'
$value = '"' + $python + '" "' + $server + '"'
$key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
New-Item -Path $key -Force | Out-Null
Set-ItemProperty -Path $key -Name 'MeetingTranscriber' -Value $value
Start-Process -FilePath $python -ArgumentList $server -WorkingDirectory $InstallRoot -WindowStyle Hidden
