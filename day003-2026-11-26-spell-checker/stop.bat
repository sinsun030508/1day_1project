@echo off
chcp 949 >nul
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | Where-Object { $_.CommandLine -match 'live_fix|autofix' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo 맞춤법 교정기를 종료했습니다.
timeout /t 2 >nul
