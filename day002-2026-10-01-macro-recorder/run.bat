@echo off
rem 매크로 녹화기 실행 (.venv가 없으면 먼저 만들고 pynput을 설치한다)
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv || goto :error
  .venv\Scripts\python.exe -m pip install -r requirements.txt || goto :error
)
start "" ".venv\Scripts\pythonw.exe" main.py
exit /b 0

:error
echo.
echo 실행에 실패했습니다. Python이 설치돼 있는지 확인해 주세요.
pause
