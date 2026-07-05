@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Missing .venv. Run this first:
  echo   uv venv .venv
  echo   uv pip install -r backend\requirements.txt --python .venv\Scripts\python.exe
  pause
  exit /b 1
)

set "MOCK_CRUSOE=%MOCK_CRUSOE%"
if "%MOCK_CRUSOE%"=="" set "MOCK_CRUSOE=true"

set "CRUSOE_MODEL=%CRUSOE_MODEL%"
if "%CRUSOE_MODEL%"=="" set "CRUSOE_MODEL=nvidia/Nemotron-3-Nano-Omni-Reasoning-30B-A3B"

echo.
echo OrbitOps NEW multimodal dashboard
echo URL: http://127.0.0.1:8010
echo API: /api/simulation/* and /api/agents/*
echo.
echo Keep this window open while testing.
echo.

"%~dp0.venv\Scripts\python.exe" "%~dp0launch_new_dashboard.py"

pause
endlocal
