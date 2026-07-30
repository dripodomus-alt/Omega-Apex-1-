<#
.SYNOPSIS
  Starts a secure SSH tunnel to the Omega V5 dashboard running on a GCP VM.
.DESCRIPTION
  This script uses `gcloud compute ssh` to forward a local port to the remote dashboard
  port (default 8080), allowing you to view the UI securely in your local browser
  at http://localhost:8080. It automatically detects your GCP project from the
  -Project parameter, the GCP_PROJECT_ID environment variable, or your active gcloud
  configuration.
  The script will occupy the terminal until you press CTRL+C to close the tunnel.
.EXAMPLE
  # Start a tunnel with default settings
  .\scripts\cloud\start_dashboard_tunnel.ps1

  # Start a tunnel using a different local port
  .\scripts\cloud\start_dashboard_tunnel.ps1 -LocalPort 9090

  # Start a tunnel to a different VM
  .\scripts\cloud\start_dashboard_tunnel.ps1 -VmName "my-other-vm" -Zone "us-central1-a"
#>
param(
    [string]$VmName = "apex-node-1",
    [string]$Zone = "us-central1-a",
    [string]$Project = "", # Will be automatically detected from gcloud config if not provided
    [int]$LocalPort = 8080,
    [int]$RemotePort = 8080
)

$ErrorActionPreference = "Stop"

if (!(Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw "gcloud command not found. Please install the Google Cloud SDK and authenticate via `gcloud auth login`."
}

$effectiveProject = $Project
if ([string]::IsNullOrEmpty($effectiveProject)) {
    $effectiveProject = $env:GCP_PROJECT_ID # Fallback to environment variable
}
if ([string]::IsNullOrEmpty($effectiveProject)) {
    try {
        $effectiveProject = gcloud config get-value project 2>$null
    } catch {}
}
if ([string]::IsNullOrEmpty($effectiveProject)) {
    throw "GCP Project ID not found. Please set it via the -Project parameter, the GCP_PROJECT_ID environment variable, or `gcloud config set project <YOUR_PROJECT_ID>`."
}

Write-Host "🚀 Starting secure SSH tunnel to $VmName..." -ForegroundColor Cyan
Write-Host "   Forwarding local port $LocalPort to remote port $RemotePort."
Write-Host "   When the tunnel is active, open this URL in your browser: http://localhost:$LocalPort/" -ForegroundColor Green
Write-Host "   Press CTRL+C in this window to close the tunnel." -ForegroundColor Yellow

000000000# Use the modern --ssh-flag syntax, which is more robust than the deprecated '--' separator.
gcloud compute ssh "$VmName" --project "$effectiveProject" --zone "$Zone" --ssh-flag="-N" --ssh-flag="-L $($LocalPort):127.0.0.1:$($RemotePort)"