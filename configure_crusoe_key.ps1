$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$envPath = Join-Path $root ".env"

$secureKey = Read-Host "Paste your rotated Crusoe API key" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)

try {
    $apiKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}

if ([string]::IsNullOrWhiteSpace($apiKey)) {
    throw "CRUSOE_API_KEY cannot be empty."
}

$lines = @(
    "CRUSOE_API_KEY=$apiKey",
    "CRUSOE_MODEL=nvidia/Nemotron-3-Nano-Omni-Reasoning-30B-A3B",
    "MOCK_CRUSOE=false",
    "ASTROOPS_ADVISORY_MODEL=nemotron_omni",
    "ASTROOPS_FAST_MODEL=nemotron_omni"
)

Set-Content -Path $envPath -Value $lines -Encoding UTF8
Write-Host "Crusoe configuration written to .env. This file is ignored by Git."
