<#
.SYNOPSIS
  Securely connects to the production VM and launches the PM2 monitoring dashboard.
.DESCRIPTION
  This script provides a one-step command to securely monitor the live, deployed
  Omega V5 system. It uses the `gcloud compute ssh` command with IAP (Identity-Aware
  Proxy) tunneling to establish a secure connection to the production VM without
  requiring a public IP address.

  Once connected, it automatically starts the `pm2 monit` command, which provides
  a real-time, terminal-based dashboard showing the status, CPU/memory usage,
  and logs of all running services.

  This is the primary tool for live operational monitoring.
.EXAMPLE
  # Connect to the default production VM and start monitoring.
  .\scripts\ops\monitor_secure_vm.ps1

  # Connect to a specific VM instance in a specific zone.
  .\scripts\ops\monitor_secure_vm.ps1 -InstanceName "omega-v5-prod-us-central1-a" -Zone "us-central1-a"
#>
[CmdletBinding()]
param(
    [string]$InstanceName = "omega-v5-prod",
    [string]$Zone = "us-central1-a",
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
function Assert-Command {
    param([string]$Name, [string]$InstallHint)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name is not available on PATH. $InstallHint"
    }
}
function Assert-Ok {
    param([bool]$Condition, [string]$Message) if (-not $Condition) { throw "[FAILURE] $Message" }
}

# --- 1. Pre-flight Checks ---
Write-Phase "Step 1: Verifying Prerequisites"
Assert-Command -Name "gcloud" -InstallHint "Install Google Cloud SDK and authenticate with `gcloud auth login`."

# Resolve environment variables if parameters are not provided
if ([string]::IsNullOrEmpty($Project)) { $Project = $env:GCP_PROJECT_ID }
if ([string]::IsNullOrEmpty($InstanceName)) { $InstanceName = $env:GCP_VM_INSTANCE_NAME }
if ([string]::IsNullOrEmpty($Zone)) { $Zone = $env:GCP_VM_ZONE }

# Final fallback to gcloud config for project ID
$effectiveProject = $Project
if ([string]::IsNullOrEmpty($effectiveProject)) {
    try {
        $effectiveProject = (gcloud config get-value project 2>$null).Trim()
    } catch {
        # gcloud might not be configured; we'll catch this in the Assert-Ok below.
    }
}
Assert-Ok -Condition (-not [string]::IsNullOrEmpty($effectiveProject)) -Message "GCP Project ID not found. Please set it via the -Project parameter, the GCP_PROJECT_ID environment variable, or `gcloud config set project <YOUR_PROJECT_ID>`."

Write-Host "Target Project  : $effectiveProject" -ForegroundColor Green
Write-Host "Target Instance : $InstanceName" -ForegroundColor Green
Write-Host "Target Zone     : $Zone" -ForegroundColor Green

# --- 2. Initiate Secure Connection ---
Write-Phase "Step 2: Initiating Secure SSH Connection via IAP"
Write-Host "This will open a new SSH session to the secure VM."
Write-Host "Once connected, 'pm2 monit' will start automatically."
Write-Host "To exit, press Ctrl+C in the SSH window."

# The `--command` parameter executes 'pm2 monit' immediately upon successful login.
# The `--` is used to separate gcloud arguments from the command arguments.
gcloud compute ssh --project $effectiveProject --zone $Zone $InstanceName --command "pm2 monit"