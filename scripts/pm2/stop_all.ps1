$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $repoRoot
 
# Set PM2_HOME to a local directory to avoid Windows C:\ permissions issues
# and ensure we are targeting the correct daemon.
$env:PM2_HOME = Join-Path $repoRoot ".pm2"
Write-Host "INFO: Using local PM2_HOME: $env:PM2_HOME"
 
Write-Host "Stopping and deleting all services defined in ecosystem.config.js..."
# Use try/catch as this will error if no processes are found
try {
    pm2 delete ecosystem.config.js
} catch {
    Write-Host "No running processes found for ecosystem.config.js."
}
 
Write-Host "PM2 services stopped."
