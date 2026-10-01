@echo off
chcp 949 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo 가상환경을 만드는 중입니다. 잠시만 기다려 주세요...
  python -m venv .venv
  if errorlevel 1 goto error
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 goto error
)

start "" ".venv\Scripts\pythonw.exe" main.py
exit /b 0

:error
echo.
echo 실행에 실패했습니다. Python이 설치돼 있는지 확인해 주세요.
echo https://www.python.org/downloads/ 에서 설치할 수 있습니다.
pause
exit /b 1
