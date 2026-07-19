param(
    [switch]$InstallDeps,
    [switch]$Reset
)

$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $repoRoot

if (!(Get-Command pm2 -ErrorAction SilentlyContinue)) {
    throw "PM2 is not available. Install with: npm install -g pm2"
}
if (!(Get-Command python -ErrorAction SilentlyContinue)) {
    throw "python is not available on PATH."
}
if (!(Get-Command anvil -ErrorAction SilentlyContinue)) {
    throw "anvil is not available on PATH. Run Foundry install/init first."
}
if (!(Get-Command redis-server -ErrorAction SilentlyContinue)) {
    throw "redis-server is not available on PATH."
}

if ($InstallDeps) {
    python -m pip install -r requirements.txt
}

powershell -NoProfile -ExecutionPolicy Bypass -File scripts\rust\build_engine.ps1
python -m omega_v5.rust_preflight
python -m omega_v5.wallet_config_verification --mode dry_run

if ($Reset) {
    pm2 delete ecosystem.config.cjs 2>$null
}

New-Item -ItemType Directory -Force -Path logs | Out-Null

pm2 start ecosystem.config.cjs --update-env
pm2 save
pm2 status

Write-Host ""
Write-Host "Omega PM2 boot submitted. Verifying API health..."
$apiUrl = "http://127.0.0.1:8080/health"
$maxAttempts = 10
$attempt = 0
$apiHealthy = $false

while ($attempt -lt $maxAttempts -and !$apiHealthy) {
    $attempt++
    Write-Host "  Attempt $attempt of ${maxAttempts}: Pinging $apiUrl"
    try {
        $response = Invoke-RestMethod -Uri $apiUrl -TimeoutSec 3
        if ($response.ok) {
            Write-Host "  ✅ API is healthy." -ForegroundColor Green
            $apiHealthy = $true
        }
    }
    catch {
        Start-Sleep -Seconds 2
    }
}

if ($apiHealthy) {
    Write-Host "✅ System is online. Dashboard is available at http://127.0.0.1:8080/" -ForegroundColor Green
} else {
    Write-Host "❌ API server failed to start. Please check the logs:" -ForegroundColor Red
    Write-Host "   pm2 logs omega-api"
    throw "API server failed to become healthy after $maxAttempts attempts."
}
