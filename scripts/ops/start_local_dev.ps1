<#
.SYNOPSIS
  Starts the complete OMEGA-FINALLY-RICH local development environment.
.DESCRIPTION
  This script ensures all dependencies are installed and then starts the
  backend API, background workers, and the web frontend in parallel as
  background jobs, reflecting the 'Run locally' instructions for the
  new monorepo architecture.
.EXAMPLE
  # Install dependencies and start all services.
  .\scripts\ops\start_local_dev.ps1

  # Force re-installation of dependencies before starting.
  .\scripts\ops\start_local_dev.ps1 -ForceInstall

  # Stop all running development jobs started by this script.
  .\scripts\ops\start_local_dev.ps1 -Stop

.NOTES
  The services are started as PowerShell background jobs. You can manage them
  using standard cmdlets like Get-Job, Receive-Job, and Stop-Job.
  The job names are 'omega-api', 'omega-worker', and 'omega-web'.
#>
[CmdletBinding()]
param(
    [switch]$Stop,
    [switch]$ForceInstall,
    [int]$ApiHealthcheckTimeoutSec = 30
)

$ErrorActionPreference = "Stop"
$repoRoot = (Get-Item -Path $PSScriptRoot).Parent.Parent.FullName
Set-Location $repoRoot

$Jobs = @("omega-api", "omega-worker", "omega-web")

function Write-Step { param([string]$Message) Write-Host "`n==> $Message" -ForegroundColor Cyan }

if ($Stop) {
    Write-Step "Stopping local development services..."
    $runningJobs = Get-Job | Where-Object { $Jobs -contains $_.Name }
    if ($runningJobs) {
        $runningJobs | Stop-Job -PassThru | Remove-Job
        Write-Host "Stopped and removed running OMEGA jobs." -ForegroundColor Green
    } else {
        Write-Host "No running OMEGA development jobs found."
    }
    exit 0
}

if (-not (Get-Command pnpm -ErrorAction SilentlyContinue)) {
    throw "pnpm is not available on your PATH. Please install it first: npm install -g pnpm"
}

if (-not (Test-Path ".env")) {
    Write-Host "`n[WARNING] No .env file found. The application may not start correctly." -ForegroundColor Yellow
    Write-Host "[INFO] Please copy .env.example to .env and configure your environment variables." -ForegroundColor Blue
}

Write-Step "Step 1: Installing Monorepo Dependencies"
if ($ForceInstall -or -not (Test-Path "node_modules")) {
    Write-Host "Running 'pnpm install'..."
    pnpm install
    if ($LASTEXITCODE -ne 0) { throw "pnpm install failed." }
    Write-Host "Dependencies installed successfully." -ForegroundColor Green
} else {
    Write-Host "node_modules already exists. Skipping install. Use -ForceInstall to override."
}

Write-Step "Step 2: Starting Services as Background Jobs"

$services = @{
    "omega-api"    = "api"
    "omega-worker" = "worker"
    "omega-web"    = "web"
}

foreach ($jobName in $services.Keys) {
    $filter = $services[$jobName]
    Write-Host "Starting $jobName (pnpm --filter $filter dev)..."
    Start-Job -Name $jobName -ScriptBlock { pnpm --filter $using:filter dev }
}

Write-Step "Step 3: Verifying API Health"
$apiUrl = (Get-Content ".env" | Select-String -Pattern "NEXT_PUBLIC_API_URL" | ForEach-Object { ($_ -split '=')[1].Trim() }) + "/health"
$healthCheckStart = Get-Date
$apiHealthy = $false

Write-Host "Waiting for API to become healthy at $apiUrl (Timeout: ${ApiHealthcheckTimeoutSec}s)..."

while (((Get-Date) - $healthCheckStart).TotalSeconds -lt $ApiHealthcheckTimeoutSec) {
    try {
        $response = Invoke-RestMethod -Uri $apiUrl -Method Get -TimeoutSec 2
        if ($response) { # Assuming any successful response is a sign of health
            Write-Host "✅ API is healthy and responsive." -ForegroundColor Green
            $apiHealthy = $true
            break
        }
    }
    catch {
        Write-Host "." -NoNewline
        Start-Sleep -Seconds 2
    }
}

if (-not $apiHealthy) {
    Write-Host "`n[WARNING] API server did not become healthy within the timeout period." -ForegroundColor Yellow
}

Write-Step "Step 4: System is Booting"
Write-Host "All services have been started in the background." -ForegroundColor Green
Write-Host "Use 'Get-Job' to see their status."
Write-Host "Use 'Receive-Job -Name <job-name> -Keep' to view logs."
Write-Host "Use '.\scripts\ops\start_local_dev.ps1 -Stop' to terminate all services."