@echo off
setlocal
if not exist "%~dp0tmp" mkdir "%~dp0tmp"
cd /d "%~dp0backend"
set "MOCK_CRUSOE=%MOCK_CRUSOE%"
if "%MOCK_CRUSOE%"=="" set "MOCK_CRUSOE=true"
set "CRUSOE_MODEL=%CRUSOE_MODEL%"
if "%CRUSOE_MODEL%"=="" set "CRUSOE_MODEL=nvidia/Nemotron-3-Nano-Omni-Reasoning-30B-A3B"
echo OrbitOps dashboard: http://127.0.0.1:8010
"%~dp0.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8010 > "%~dp0tmp\run_dashboard.log" 2>&1
type "%~dp0tmp\run_dashboard.log"
endlocal
