<#
.SYNOPSIS
  Starts the Omega V5 core components directly (no PM2 required).
  Recommended for local development on Windows.
.DESCRIPTION
  Launches:
    - uvicorn API server
    - Main arbitrage engine
    - Liquidation watcher (optional)

  Use this when PM2 gives EPERM / pipe errors.
.EXAMPLE
  .\scripts\ops\start_direct.ps1
  .\scripts\ops\start_direct.ps1 -NoWatcher
#>
[CmdletBinding()]
param(
    [switch]$NoWatcher,
    [switch]$NoApi
)

$ErrorActionPreference = "Continue"
$repoRoot = (Get-Item -Path $PSScriptRoot).Parent.Parent.FullName
Set-Location $repoRoot
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"

Write-Host "=== Omega V5 Direct Start (PM2-free) ===" -ForegroundColor Cyan
Write-Host "Working directory: $repoRoot`n"

# Require project virtual environment for deterministic runtime behavior.
if (!(Test-Path -LiteralPath $venvPython)) {
  throw "Project venv interpreter not found at $venvPython. Run .\scripts\ops\bootstrap_hybrid_env.ps1 first."
}

Write-Host "Using venv interpreter: $venvPython" -ForegroundColor Yellow

# Start API
if (-not $NoApi) {
    Write-Host "Starting API (uvicorn) on port 8080..." -ForegroundColor Green
  Start-Process -FilePath $venvPython -ArgumentList "-m uvicorn omega_v5.api:app --host 127.0.0.1 --port 8080" -WindowStyle Normal
    Start-Sleep -Seconds 2
}

# Start main engine
Write-Host "Starting main engine (omega_v5.main)..." -ForegroundColor Green
Start-Process -FilePath $venvPython -ArgumentList "-m omega_v5.main" -WindowStyle Normal

# Start liquidation watcher
if (-not $NoWatcher) {
    Write-Host "Starting liquidation watcher..." -ForegroundColor Green
  Start-Process -FilePath $venvPython -ArgumentList "-m omega_v5.liquidation_watcher" -WindowStyle Normal
}

Write-Host "`n✅ Core services launched in separate windows." -ForegroundColor Green
Write-Host "Close the individual windows to stop services."
Write-Host "For full stack (including anvil/redis), use Docker or install them natively."
