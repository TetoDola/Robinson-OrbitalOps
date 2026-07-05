$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$python = Join-Path $root ".venv\Scripts\python.exe"
$logs = Join-Path $root "tmp"

New-Item -ItemType Directory -Force -Path $logs | Out-Null

$psi = [System.Diagnostics.ProcessStartInfo]::new()
$psi.FileName = $python
$psi.Arguments = "-m uvicorn app.main:app --host 127.0.0.1 --port 8010"
$psi.WorkingDirectory = $backend
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$process = [System.Diagnostics.Process]::Start($psi)
Start-Sleep -Milliseconds 800

if ($process.HasExited) {
    throw "OrbitOps server exited immediately."
}

Write-Host "OrbitOps dashboard started on http://127.0.0.1:8010 (PID $($process.Id))"
