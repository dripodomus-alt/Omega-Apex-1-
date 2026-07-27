<#
.SYNOPSIS
  Starts, and optionally resets, all services defined in the ecosystem.config.js file.
.DESCRIPTION
  This script is the primary entrypoint for booting the entire Omega V5 service stack using PM2.
  It uses the `ecosystem.config.js` file as the source of truth for all services.
.EXAMPLE
  # Start all services if they are not already running.
  .\scripts\pm2\boot_all.ps1

  # Stop, delete, and restart all services for a clean boot.
  .\scripts\pm2\boot_all.ps1 -Reset
#>
[CmdletBinding()]
param(
    # If specified, stops and deletes all existing PM2 processes before starting.
    [switch]$Reset
)

$ErrorActionPreference = "Stop"
$repoRoot = (Get-Item -Path $PSScriptRoot).Parent.Parent.FullName
Set-Location $repoRoot

# --- PM2 Environment Configuration ---
# Set PM2_HOME to a local directory to avoid Windows C:\ permissions issues.
$env:PM2_HOME = Join-Path $repoRoot ".pm2"
Write-Host "INFO: Using local PM2_HOME: $env:PM2_HOME"

# --- Pre-flight Check ---
if (-not (Get-Command pm2 -ErrorAction SilentlyContinue)) {
    throw "pm2 is not available on your PATH. Please install it globally with 'npm install -g pm2'."
}
if (-not (Test-Path "ecosystem.config.js")) { # Explicitly check for the .js file
    throw "ecosystem.config.js not found in the project root. This file is required to boot the services."
}

# --- Reset (Optional) ---
if ($Reset) {
    Write-Host "Resetting PM2 environment..."
    # Use try/catch because 'pm2 delete all' can fail if no processes exist, which is not an error.
    try {
        pm2 delete all
    } catch {
        Write-Host "No existing PM2 processes to delete."
    }
}

# --- Start & Save Services ---
Write-Host "Starting all services from ecosystem.config.js..."
pm2 start ecosystem.config.js # Explicitly start the .js file
if ($LASTEXITCODE -ne 0) {
    throw "Failed to start services with PM2. Check the logs above for errors."
}

Write-Host "Saving PM2 process list to resurrect on reboot..."
pm2 save
if ($LASTEXITCODE -ne 0) {
    # This is not a fatal error, but the user should be aware.
    Write-Host "Warning: Failed to save PM2 process list. Processes will not be restored after a system reboot." -ForegroundColor Yellow
}

Write-Host "`n✅ All services booted successfully." -ForegroundColor Green
pm2 status
