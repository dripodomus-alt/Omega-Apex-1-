<#
.SYNOPSIS
  Automates the full deployment and configuration of Solidity source adapters.
.DESCRIPTION
  This script provides a single, safe entrypoint for the multi-step process of
  deploying and configuring the capital source adapters. It orchestrates the
  deployment, syncs the new contract addresses to the .env file, and configures
  the on-chain pool-kind allowlist.

  This reduces manual steps and the risk of misconfiguration.
.EXAMPLE
  # Perform a full dry-run of the adapter setup process.
  .\scripts\cloud\finalize_adapter_setup.ps1

  # Run the full process and broadcast the transactions to mainnet.
  .\scripts\cloud\finalize_adapter_setup.ps1 -Broadcast -LiveAck "I_UNDERSTAND_POLYGON_MAINNET_RISK"
#>
param(
    [switch]$Broadcast,
    [string]$LiveAck = "",
    [switch]$DeployCurveAdapter,
    [string]$RpcUrl = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = (Get-Item -Path $PSScriptRoot).Parent.Parent.FullName
Set-Location $repoRoot

function Write-Step { param([string]$Message) Write-Host "`n✅ $($Message)" -ForegroundColor Green }

if ($Broadcast -and $LiveAck -ne "I_UNDERSTAND_POLYGON_MAINNET_RISK") {
    throw "Broadcasting to mainnet requires the acknowledgment: -LiveAck 'I_UNDERSTAND_POLYGON_MAINNET_RISK'"
}

$commonArgs = @()
if ($RpcUrl) { $commonArgs += "--rpc-url", $RpcUrl }
if ($Broadcast) { $commonArgs += "--send" }

# --- 1. Deploy Adapters ---
Write-Step "Step 1: Deploying and Configuring Source Adapter Contracts"
$deployArgs = $commonArgs + @("--configure", "--write-env")
Write-Host "Running python -m omega_v5.deploy_adapters to deploy standard adapters (Balancer, Aave)..."
python -m omega_v5.deploy_adapters @deployArgs # Deploys the standard, audited set
Assert-Ok ($LASTEXITCODE -eq 0) "Adapter deployment script failed."

if ($DeployCurveAdapter) {
    Write-Step "Step 1.5: Deploying and Configuring Curve Capital Source Adapter (Prototype)"
    Write-Host "Running python -m omega_v5.deploy_adapters for Curve..." -ForegroundColor Yellow
    $curveDeployArgs = $commonArgs + @("--adapter", "curve", "--configure", "--write-env")
    python -m omega_v5.deploy_adapters @curveDeployArgs
    Assert-Ok ($LASTEXITCODE -eq 0) "Curve adapter deployment failed. NOTE: This requires a new 'OmegaCurveCapitalSourceAdapter.sol' and updates to the python deployment script."
}
Write-Host ".env file has been updated with the new contract addresses."

# --- 2. Sync Environment (REMOVED) ---
# This step is now handled by the --write-env and --configure flags in the
# deploy_adapters.py script itself. This ensures that the newly deployed
# adapter addresses are immediately configured on-chain and written to the
# .env file, making the process more atomic and removing the need for a
# separate sync script that might read stale on-chain state.

# --- 3. Configure On-Chain Allowlist ---
Write-Step "Step 3: Configuring On-Chain Route Pool Kind Allowlist"
Write-Host "Running python -m omega_v5.configure_route_pool_kinds..."
$configArgs = $commonArgs + @("--adapter", "all", "--live-registry")
python -m omega_v5.configure_route_pool_kinds @configArgs
Assert-Ok ($LASTEXITCODE -eq 0) "Route pool kind configuration script failed."

Write-Step "Adapter setup complete."
Write-Host "The new adapters have been deployed and configured for use by the execution engine."