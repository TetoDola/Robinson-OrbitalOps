@echo off
cd /d "%~dp0"
echo OrbitOps is starting...
echo App:  http://127.0.0.1:8000
echo API:  http://127.0.0.1:8000/docs
echo.
echo Keep this terminal window running.
call "%~dp0start-backend.cmd"
