<#
.SYNOPSIS
  Deploys the individual on-chain adapter contracts to Polygon mainnet.
.DESCRIPTION
  This script uses Foundry to compile and deploy the adapter contracts required
  by the main Omega executor. It iterates through a list of necessary adapters,
  deploys each one using the EXECUTOR_PRIVATE_KEY from your .env file, and
  outputs a JSON file containing the new contract addresses.

  This is the first step in activating full on-chain execution capabilities.
  The output of this script is the input for 'configure_onchain_executor.ps1'.

  WARNING: This script deploys new contracts to the mainnet and will spend
  real POL from the executor wallet for gas fees.
.EXAMPLE
  # Run the deployment script. It will prompt for confirmation.
  .\scripts\ops\deploy_onchain_adapters.ps1

  # Run non-interactively (e.g., in a CI/CD pipeline).
  .\scripts\ops\deploy_onchain_adapters.ps1 -Force
#>
[CmdletBinding()]
param(
    [switch]$Force
)

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

Write-Phase -Title "Step 1: Pre-flight Checks for Adapter Deployment"
Assert-Command -Name "forge" -InstallHint "Install Foundry (which includes 'forge') and ensure it is on PATH."
Assert-Ok -Condition (Test-Path $resolvedEnvPath) -Message "Environment file not found at '$resolvedEnvPath'. Configure OMEGA_ENV_PATH or environment profile."

$envConfig = Parse-EnvFile -FilePath $resolvedEnvPath
$privateKey = $envConfig.EXECUTOR_PRIVATE_KEY
$rpcUrl = $envConfig.BROADCAST_RPC_URL
Assert-Ok -Condition (-not ([string]::IsNullOrEmpty($privateKey) -or $privateKey.Contains("..."))) -Message "EXECUTOR_PRIVATE_KEY is not set in '$resolvedEnvPath'. It is required to deploy contracts."
Assert-Ok -Condition (-not ([string]::IsNullOrEmpty($rpcUrl))) -Message "BROADCAST_RPC_URL is not set in '$resolvedEnvPath'. It is required to deploy contracts."

if (-not $Force) {
    Write-Host "You are about to deploy new adapter contracts to Polygon Mainnet." -ForegroundColor Yellow
    Write-Host "This will spend POL from the executor wallet for gas." -ForegroundColor Yellow
    $confirmation = Read-Host "Are you sure you want to proceed? [y/N]"
    if ($confirmation.ToLower() -ne 'y') {
        throw "Deployment cancelled by user."
    }
}

Write-Phase -Title "Step 2: Compiling and Deploying Adapters"
$adaptersToDeploy = @(
    "OmegaV2CpmmAdapter",
    "OmegaV3ClmmAdapter",
    "OmegaAlgebraClmmAdapter",
    "OmegaCurveStableAdapter",
    "OmegaBalancerWeightedAdapter",
    "OmegaKyberElasticAdapter",
    "OmegaDodoPmmAdapter"
)

$deploymentJobs = @()
$deploymentScriptBlock = {
    param($adapterName, $privateKey, $rpcUrl, $repoRoot)

    # This block runs in a separate thread, so we need to re-establish context.
    Set-Location $repoRoot

    try {
        # Construct a clean, Unix-style path that forge can reliably parse on any OS.
        # This is the definitive fix for the Windows pathing issue.
        $contractSpecifier = "contracts/adapters/${adapterName}.sol:${adapterName}"

        # For debugging: show the exact forge command being executed
        Write-Host "DEBUG: Executing forge create --root . $contractSpecifier --private-key ***** --rpc-url $rpcUrl"

        # Execute forge create and capture output
        # The --json flag provides reliable, machine-readable output.
        $outputJson = forge create --root . $contractSpecifier --private-key $privateKey --rpc-url $rpcUrl --json | ConvertFrom-Json
        $deployedAddress = $outputJson.deployedTo

        if ([string]::IsNullOrEmpty($deployedAddress)) {
            throw "Failed to parse deployed address from forge output for $adapterName."
        }

        return [PSCustomObject]@{ AdapterName = $adapterName; Address = $deployedAddress; Success = $true }
    } catch {
        $errorMessage = "Failed to deploy $adapterName. Error: $($_.Exception.Message)"
        Write-Error $errorMessage
        return [PSCustomObject]@{ AdapterName = $adapterName; Address = $null; Success = $false; Error = $errorMessage }
    }
}

Write-Host "Starting parallel deployment of $($adaptersToDeploy.Count) adapters..."
foreach ($adapterName in $adaptersToDeploy) {
    $job = Start-ThreadJob -ScriptBlock $deploymentScriptBlock -ArgumentList $adapterName, $privateKey, $rpcUrl, $repoRoot
    $deploymentJobs += $job
}

$results = $deploymentJobs | Wait-Job | Receive-Job

$deployedAddresses = @{}
$results | ForEach-Object {
    Assert-Ok -Condition $_.Success -Message "Deployment job failed for $($_.AdapterName): $($_.Error)"
    $deployedAddresses[$_.AdapterName] = $_.Address
    Write-Host "✅ Deployed $($_.AdapterName) to: $($_.Address)" -ForegroundColor Green
}

Write-Phase -Title "Step 3: Saving Deployment Artifacts"
$outputPath = "out/adapter_deployments.json"
$deployedAddresses | ConvertTo-Json -Depth 5 | Set-Content -Path $outputPath
Write-Host "✅ Deployment complete. Adapter addresses saved to '$outputPath'." -ForegroundColor Green
Write-Host "You may now proceed to 'configure_onchain_executor.ps1' to register these adapters."