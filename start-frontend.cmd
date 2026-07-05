@echo off
cd /d "%~dp0frontend"
set "PATH=C:\Users\sivap\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin;%PATH%"
".\node_modules\.bin\vite.cmd" --host 127.0.0.1 --port 5173

