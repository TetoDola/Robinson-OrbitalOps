$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Host "Virtual environment not found. Creating it..."
    $env:UV_CACHE_DIR = Join-Path $root ".uv-cache"
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $root ".uv-python"
    uv venv (Join-Path $root ".venv")
    uv pip install -r (Join-Path $backend "requirements.txt") --python $python
}

$env:MOCK_CRUSOE = if ($env:MOCK_CRUSOE) { $env:MOCK_CRUSOE } else { "true" }
$env:CRUSOE_MODEL = if ($env:CRUSOE_MODEL) { $env:CRUSOE_MODEL } else { "nvidia/Nemotron-3-Nano-Omni-Reasoning-30B-A3B" }

Set-Location $backend
Write-Host "OrbitOps dashboard: http://127.0.0.1:8010"
& $python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
