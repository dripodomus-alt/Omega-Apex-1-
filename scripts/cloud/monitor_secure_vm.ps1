<#
.SYNOPSIS
  Provides a simple interface for monitoring the services on the secure VM.
.DESCRIPTION
  This script automates the gcloud SSH commands needed to perform common
  monitoring tasks like viewing logs or checking process status with PM2.
.EXAMPLE
  # Show the PM2 process list (default action)
  .\scripts\cloud\monitor_secure_vm.ps1

  # Tail the logs for the main arbitrage engine
  .\scripts\cloud\monitor_secure_vm.ps1 -Logs

  # Tail the logs for a specific service, like the API
  .\scripts\cloud\monitor_secure_vm.ps1 -Logs -Service omega-api

  # Open the interactive PM2 terminal dashboard
  .\scripts\cloud\monitor_secure_vm.ps1 -Dashboard
#>
param(
    [string]$VmName = "omega-executor-vm-1",
    [string]$Zone = "us-east1-b",
    [ValidateSet("omega-engine", "omega-api", "omega-liquidation-watcher", "omega-telegram-bot")]
    [string]$Service = "omega-engine",
    [switch]$Logs,
    [switch]$Dashboard
)

$ErrorActionPreference = "Stop"

$projectId = gcloud config get-value project
if (!$projectId) {
    throw "No active gcloud project. Run 'gcloud config set project <id>'"
}

if ($Dashboard) {
    Write-Host "Opening PM2 monitoring dashboard in the VM..." -ForegroundColor Cyan
    gcloud compute ssh $VmName --project $projectId --zone $Zone --command "pm2 monit"
}
elseif ($Logs) {
    Write-Host "Tailing logs for '$Service' in the VM..." -ForegroundColor Cyan
    gcloud compute ssh $VmName --project $projectId --zone $Zone --command "pm2 logs $Service --lines 100"
}
else {
    Write-Host "Showing PM2 process list in the VM..." -ForegroundColor Cyan
    gcloud compute ssh $VmName --project $projectId --zone $Zone --command "pm2 list"
}