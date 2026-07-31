<#
.SYNOPSIS
  Securely stops all running services on the production VM and then shuts down the VM itself.
.DESCRIPTION
  This script provides a safe and orderly shutdown procedure for the live, deployed
  Omega V5 system. It performs a two-stage shutdown:

  1.  **Graceful Service Stop:** It first connects to the VM via secure SSH and runs
      `pm2 delete all` to gracefully stop all running engine and watcher processes.
      It then runs `pm2 save` to persist the empty process list, preventing an
      automatic restart on the next boot.

  2.  **VM Shutdown:** After services are confirmed to be stopped, it uses the
      `gcloud compute instances stop` command to shut down the entire VM instance.

  This procedure prevents data corruption and ensures a clean state for the next
  time the system is started. It includes multiple confirmation steps to prevent
  accidental shutdown.
.EXAMPLE
  # Securely shut down the default production VM.
  .\scripts\ops\shutdown_secure_vm.ps1 -Confirm

  # Shut down a specific VM instance.
  .\scripts\ops\shutdown_secure_vm.ps1 -InstanceName "apex-node-1" -Confirm
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [switch]$Confirm,

    [string]$InstanceName = "omega-executor-vm-1",
    [string]$Zone = "us-east1-b",
    [string]$Project
)

$ErrorActionPreference = "Stop"

# --- Helper Functions ---
function Write-Phase {
    param([string]$Title)
    $timestamp = Get-Date -Format "HH:mm:ss"
    Write-Host "`n" + ("-" * 80)
    Write-Host "[$timestamp] $Title" -ForegroundColor Cyan
    Write-Host ("-" * 80)
}
function Assert-Ok { param([bool]$Condition, [string]$Message) if (-not $Condition) { throw "[FAILURE] $Message" } }
function Assert-Command { param([string]$Name, [string]$InstallHint) if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) { throw "$Name is not available on PATH. $InstallHint" } }

# --- 1. Pre-flight Checks ---
Write-Phase "Step 1: Verifying Prerequisites"
Assert-Command -Name "gcloud" -InstallHint "Install Google Cloud SDK and authenticate with `gcloud auth login`."

if (-not $Confirm) {
    throw "This is a destructive script. You must explicitly acknowledge the risk by adding the '-Confirm' parameter."
}

$effectiveProject = $Project
if ([string]::IsNullOrEmpty($effectiveProject)) { $effectiveProject = $env:GCP_PROJECT_ID }
if ([string]::IsNullOrEmpty($effectiveProject)) { $effectiveProject = (gcloud config get-value project 2>$null).Trim() }
Assert-Ok -Condition (-not [string]::IsNullOrEmpty($effectiveProject)) -Message "GCP Project ID not found. Please set it via the -Project parameter, the GCP_PROJECT_ID environment variable, or `gcloud config set project <YOUR_PROJECT_ID>`."

Write-Host "You are about to shut down all services on the following VM and then stop the VM itself:" -ForegroundColor Yellow
Write-Host "  Project  : $effectiveProject"
Write-Host "  Instance : $InstanceName"
Write-Host "  Zone     : $Zone"

$confirmation = Read-Host "`nAre you absolutely sure you want to proceed? [y/N]"
if ($confirmation.ToLower() -ne 'y') {
    throw "Shutdown cancelled by user."
}

# --- 2. Graceful Service Stop ---
Write-Phase "Step 2: Gracefully Stopping All PM2 Services on VM"
# Use 'bash -c "set -e; ..."' to ensure that if any command (like pm2) fails,
# the entire remote script exits with a non-zero status code, which is then caught by Assert-Ok.
gcloud compute ssh --project $effectiveProject --zone $Zone $InstanceName --command "bash -c ""set -e; echo 'Stopping all services...'; pm2 delete all; pm2 save --force; echo 'Services stopped.'"""
Assert-Ok -Condition ($LASTEXITCODE -eq 0) -Message "Failed to stop PM2 services on the remote VM."
Write-Host "All PM2 services have been stopped and the process list has been saved." -ForegroundColor Green

# --- 3. VM Shutdown ---
Write-Phase "Step 3: Shutting Down the VM Instance"
gcloud compute instances stop $InstanceName --project $effectiveProject --zone $Zone
Write-Host "✅ Shutdown command sent to VM '$InstanceName'. It will stop shortly." -ForegroundColor Green
