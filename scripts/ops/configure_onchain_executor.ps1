<#
.SYNOPSIS
  Configures the main executor contract by registering the deployed adapters.
.DESCRIPTION
  This script reads the adapter addresses from 'out/adapter_deployments.json'
  and calls the 'configureAdapter(uint8, address)' function on the main executor
  contract for each one. This is an owner-only function that links a protocol ID
  (e.g., 1 for V2_CPMM) to its corresponding adapter contract address.

  This is the final step to fully activate the on-chain execution muscle.

  WARNING: This script sends live transactions to the mainnet and will spend
  real POL from the executor wallet for gas fees. The EXECUTOR_WALLET must be
  the owner of the EXECUTOR_CONTRACT_ADDR.
.EXAMPLE
  # Run the configuration script after deploying the adapters.
  .\scripts\ops\configure_onchain_executor.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = (Get-Item -Path $PSScriptRoot).Parent.Parent.FullName
Set-Location $repoRoot
$envHelperPath = Join-Path $PSScriptRoot "env_contract.ps1"
. $envHelperPath
$resolvedEnvPath = Resolve-EnvContractPath -RepoRoot $repoRoot
$env:OMEGA_ENV_PATH = $resolvedEnvPath

# --- Helper Functions ---
function Write-Phase {
    param([string]$Title, [string]$Subtitle)
    $timestamp = Get-Date -Format "HH:mm:ss"
    Write-Host "`n" + ("-" * 80)
    Write-Host "[$timestamp] $Title" -ForegroundColor Cyan
    if (-not [string]::IsNullOrEmpty($Subtitle)) { Write-Host "  $Subtitle" -ForegroundColor Gray }
    Write-Host ("-" * 80)
}
function Assert-Ok { param([bool]$Condition, [string]$Message) if (-not $Condition) { throw "[FAILURE] $Message" } }
function Assert-Command { param([string]$Name, [string]$InstallHint) if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) { throw "$Name is not available on PATH. $InstallHint" } }
function Parse-EnvFile {
    param([string]$FilePath)
    $config = @{}
    if (Test-Path $FilePath) {
        Get-Content $FilePath | ForEach-Object {
            $line = $_.Trim()
            if ($line -and $line -notmatch '^\s*#') {
                $parts = $line -split '=', 2
                if ($parts.Length -eq 2) {
                    $key = $parts[0].Trim()
                    $value = $parts[1].Trim().Trim('"').Trim("'")
                    $config[$key] = $value
                }
            }
        }
    }
    return $config
}

Write-Phase -Title "Step 1: Pre-flight Checks for Executor Configuration"
Assert-Command -Name "cast" -InstallHint "Install Foundry (which includes 'cast') and ensure it is on PATH."
$deploymentsPath = "out/adapter_deployments.json"
Assert-Ok -Condition (Test-Path $deploymentsPath) -Message "Deployment artifact '$deploymentsPath' not found. Run 'deploy_onchain_adapters.ps1' first."

$envConfig = Parse-EnvFile -FilePath $resolvedEnvPath
$privateKey = $envConfig.EXECUTOR_PRIVATE_KEY
$rpcUrl = $envConfig.BROADCAST_RPC_URL
$executorAddress = $envConfig.EXECUTOR_CONTRACT_ADDR
Assert-Ok -Condition (-not ([string]::IsNullOrEmpty($privateKey))) -Message "EXECUTOR_PRIVATE_KEY is not set in '$resolvedEnvPath'."
Assert-Ok -Condition (-not ([string]::IsNullOrEmpty($rpcUrl))) -Message "BROADCAST_RPC_URL is not set in '$resolvedEnvPath'."
Assert-Ok -Condition (-not ([string]::IsNullOrEmpty($executorAddress))) -Message "EXECUTOR_CONTRACT_ADDR is not set in '$resolvedEnvPath'."

$deployedAdapters = Get-Content $deploymentsPath -Raw | ConvertFrom-Json

Write-Phase -Title "Step 2: Registering Adapters with Main Executor"

# This mapping connects the contract name to its on-chain Protocol ID from config.py
$adapterToProtocolIdMap = @{
    "OmegaV2CpmmAdapter"           = 1
    "OmegaV3ClmmAdapter"           = 2
    "OmegaAlgebraClmmAdapter"      = 3
    "OmegaCurveStableAdapter"      = 4
    "OmegaBalancerWeightedAdapter" = 5
    "OmegaKyberElasticAdapter"     = 6
    "OmegaDodoPmmAdapter"          = 7
}

foreach ($adapterName in $adapterToProtocolIdMap.Keys) {
    if (-not $deployedAdapters.Contains($adapterName)) {
        Write-Host "⚠️ Adapter '$adapterName' not found in deployment file. Skipping." -ForegroundColor Yellow
        continue
    }

    $adapterAddress = $deployedAdapters.$adapterName
    $protocolId = $adapterToProtocolIdMap.$adapterName

    Write-Host "Registering $adapterName ($adapterAddress) with Protocol ID $protocolId..."

    try {
        $txHash = cast send $executorAddress "configureAdapter(uint8,address)" $protocolId $adapterAddress --private-key $privateKey --rpc-url $rpcUrl --json | ConvertFrom-Json | Select-Object -ExpandProperty transactionHash -ErrorAction Stop
        Assert-Ok -Condition (-not ([string]::IsNullOrEmpty($txHash))) -Message "Transaction failed to broadcast for $adapterName."
        Write-Host "✅ Transaction sent: $txHash. Waiting for receipt..."
        $receipt = cast receipt $txHash --rpc-url $rpcUrl --json | ConvertFrom-Json
        Assert-Ok -Condition ($receipt.status -eq "0x1") -Message "Transaction for $adapterName reverted. Check transaction on Polygonscan."
        Write-Host "✅ Successfully configured adapter for Protocol ID $protocolId." -ForegroundColor Green
    } catch {
        throw "Failed to configure adapter for $adapterName. Error: $($_.Exception.Message)"
    }
}

Write-Phase -Title "Step 3: Configuration Complete"
Write-Host "✅ All available adapters have been registered with the main executor contract." -ForegroundColor Green
Write-Host "The system's on-chain muscle is now fully activated."