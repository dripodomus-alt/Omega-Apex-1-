<#
.SYNOPSIS
  Runs the high-performance, SDK-driven benchmark in live-fire mode.
.DESCRIPTION
  This script is a lightweight wrapper around the new `run_benchmark.py` script,
  which uses the web3.py SDK for superior performance and maintainability.

  It performs critical safety checks, confirms user intent for a live run, and
  then invokes the Python script in 'live' mode. This provides a safe and
  consistent entry point while centralizing the core benchmark logic in a more
  efficient language (Python).

  WARNING: THIS SCRIPT SUBMITS REAL, LIVE, MAINNET TRANSACTIONS.
  IT WILL SPEND REAL GAS AND ATTEMPT TO EXECUTE TRADES WITH THE CONFIGURED WALLET.
  USE WITH EXTREME CAUTION. START WITH MINIMAL CAPITAL. YOU ARE RESPONSIBLE FOR ANY FINANCIAL LOSS.
.EXAMPLE
  # Run a single benchmark cycle, requiring explicit confirmation.
  .\scripts\ops\run_live_fire_benchmark.ps1 -ConfirmLiveFire

  # Run 5 benchmark cycles in a row.
  .\scripts\ops\run_live_fire_benchmark.ps1 -ConfirmLiveFire -Cycles 5

  # Run a benchmark targeting opportunities with at least $10 estimated profit.
  .\scripts\ops\run_live_fire_benchmark.ps1 -ConfirmLiveFire -MinProfitUSD 10
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [switch]$ConfirmLiveFire,

    # NOTE: The new SDK-driven pipeline currently only supports PrivateKey signing.
    # Hardware signer support can be added to the Python script in the future.

    [int]$Cycles = 1,
    [int]$MaxParallelTx = 10,
    [double]$MinProfitUSD = 5.0,
    [int]$TxConfirmationTimeoutSec = 120
)

$ErrorActionPreference = "Stop"
$repoRoot = (Get-Item -Path (Join-Path $PSScriptRoot "..")).Parent.FullName
Set-Location $repoRoot
$envHelperPath = Join-Path $PSScriptRoot "env_contract.ps1"
. $envHelperPath
$resolvedEnvPath = Resolve-EnvContractPath -RepoRoot $repoRoot
$env:OMEGA_ENV_PATH = $resolvedEnvPath

# --- Helper Functions (aligned with project standards) ---
function Write-Phase {
    param([string]$Title, [string]$Subtitle)
    $timestamp = Get-Date -Format "HH:mm:ss"
    Write-Host "`n" + ("-" * 80)
    Write-Host "[$timestamp] $Title" -ForegroundColor Cyan
    if (-not [string]::IsNullOrEmpty($Subtitle)) { Write-Host "  $Subtitle" -ForegroundColor Gray }
    Write-Host ("-" * 80)
}
function Assert-Ok { param([bool]$Condition, [string]$Message) if (-not $Condition) { throw $Message } }
function Assert-Command {
    param([string]$Name, [string]$InstallHint)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Command '$Name' not found. $InstallHint"
    }
}
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
                    $value = $parts[1].Trim()
                    # Strip quotes from value, if present
                    if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
                        $value = $value.Substring(1, $value.Length - 2)
                    }
                    $config[$key] = $value
                }
            }
        }
    }
    return $config
}

# --- PRE-FLIGHT CHECKS ---
Write-Phase -Title "Step 1: Live-Fire Pre-flight & Safety Checks" -Subtitle "Verifying configuration, chain sync, and wallet integrity..."

if (-not $ConfirmLiveFire) {
    throw "This is a high-risk script. You must explicitly acknowledge the risk by adding the '-ConfirmLiveFire' parameter."
}

Assert-Command -Name "python" -InstallHint "Please install Python and ensure it is available in your PATH."
Assert-Command -Name "cast" -InstallHint "Please install Foundry (which includes 'cast') and ensure it is available in your PATH."

Write-Host "Verifying environment and wallet configuration..."
Assert-Ok -Condition (Test-Path $resolvedEnvPath) -Message "Environment file not found at '$resolvedEnvPath'. Cannot proceed."

# Use a robust parser that handles duplicate keys by taking the last value.
$envConfig = Parse-EnvFile -FilePath $resolvedEnvPath

Write-Host "Resolving best broadcast RPC endpoint via rpc_layer..."
$rpcUrl = (& python -m omega_v5.transport_lanes --lane broadcast 2>$null | Select-Object -First 1).Trim()
Assert-Ok -Condition (-not [string]::IsNullOrEmpty($rpcUrl)) -Message "Could not resolve a broadcast RPC URL via rpc_layer. Check rpc_benchmark.json and .env fallbacks."
Write-Host "Using broadcast RPC: $rpcUrl" -ForegroundColor Green

$env:ETH_RPC_URL = $rpcUrl # Set for subsequent cast commands

$publicRpc = $envConfig.TELEMETRY_RPC_URL
Assert-Ok -Condition (-not [string]::IsNullOrEmpty($publicRpc)) -Message "TELEMETRY_RPC_URL is not set in '$resolvedEnvPath'. A public RPC is required for chain sync verification."

$executorContractAddress = (& python -m omega_v5.contract_deployments --name EXECUTOR_CONTRACT 2>$null | Select-Object -First 1).Trim()
Assert-Ok -Condition (-not [string]::IsNullOrEmpty($executorContractAddress)) -Message "Could not resolve the main EXECUTOR_CONTRACT from config.py. Check .env variables like C1_PAYLOAD_TARGET, EXECUTOR_CONTRACT_ADDR, etc."
Assert-Ok -Condition ($executorContractAddress.Length -eq 42 -and $executorContractAddress.StartsWith("0x")) -Message "Resolved EXECUTOR_CONTRACT '$executorContractAddress' is not a valid Ethereum address."

Write-Host "Verifying chain synchronization..."
try {
    $primaryBlock = cast block-number --rpc-url $rpcUrl
    $publicBlock = cast block-number --rpc-url $publicRpc
    $blockLag = $publicBlock - $primaryBlock
    Assert-Ok -Condition ([Math]::Abs($blockLag) -lt 5) -Message "FATAL: High block lag between primary RPC ($rpcUrl) and public RPC ($publicRpc). Lag: $blockLag blocks. Halting for safety."
    Write-Host "RPCs are synchronized (Lag: $blockLag blocks)." -ForegroundColor Green
} catch {
    throw "Could not verify chain synchronization. Primary or public RPC may be down. Error: $($_.Exception.Message)"
}

$chainId = cast chain-id
Assert-Ok -Condition ($chainId -eq 137) -Message "FATAL: RPC endpoint is connected to the wrong chain (ID: $chainId). Live-fire mode requires Polygon mainnet (ID: 137)."

Write-Host "Sanity-checking executor wallet..."
$privateKey = $envConfig.EXECUTOR_PRIVATE_KEY
Assert-Ok -Condition (-not ([string]::IsNullOrEmpty($privateKey) -or $privateKey.Contains("..."))) -Message "EXECUTOR_PRIVATE_KEY is not set or is a placeholder in '$resolvedEnvPath'. A valid private key is required."
$derivedAddress = (cast wallet address $privateKey).Trim()
$configuredAddress = $envConfig.EXECUTOR_WALLET
Assert-Ok -Condition ($derivedAddress.ToLower() -eq $configuredAddress.ToLower()) -Message "FATAL: Address derived from EXECUTOR_PRIVATE_KEY ($derivedAddress) does not match EXECUTOR_WALLET ($configuredAddress) in '$resolvedEnvPath'. Check for typos."
Write-Host "Wallet sanity checks passed." -ForegroundColor Green

Write-Phase -Title "Step 2: Final Confirmation" -Subtitle "Review details before authorizing live transactions."

try {
    $initialBalanceWei = cast balance $envConfig.EXECUTOR_WALLET
    $initialBalanceNative = cast from-wei $initialBalanceWei
    $balanceDisplay = "$initialBalanceNative POL"
} catch {
    $balanceDisplay = "COULD NOT FETCH (RPC Error)"
}

Write-Host "------------------------------------------------------------" -ForegroundColor Yellow
Write-Host "  SIGNER TYPE     : PrivateKey (SDK Mode)" -ForegroundColor Yellow
Write-Host "  EXECUTOR WALLET : $envConfig.EXECUTOR_WALLET" -ForegroundColor Yellow
Write-Host "  EXECUTOR WALLET : $($envConfig.EXECUTOR_WALLET)" -ForegroundColor Yellow
Write-Host "  NETWORK         : Polygon Mainnet (ChainID: $chainId)" -ForegroundColor Yellow
Write-Host "  RPC ENDPOINT    : $rpcUrl" -ForegroundColor Yellow
Write-Host "------------------------------------------------------------" -ForegroundColor Yellow
Write-Host "  BENCHMARK SCOPE" -ForegroundColor Yellow
Write-Host "  Cycles to Run   : $Cycles" -ForegroundColor Yellow
Write-Host "  Min Profit / Tx : `$ $($MinProfitUSD)" -ForegroundColor Yellow
$initialBalanceWei = cast balance $envConfig.EXECUTOR_WALLET
$initialBalanceNative = cast from-wei $initialBalanceWei
Write-Host "Initial wallet balance: $initialBalanceNative POL" -ForegroundColor Green
Write-Host "Initial wallet balance: $balanceDisplay" -ForegroundColor Green

$confirmation = Read-Host "`nThis script will execute REAL transactions on the network above. Are you absolutely sure you want to proceed? [y/N]"
if ($confirmation.ToLower() -ne 'y') {
    throw "Live-fire benchmark cancelled by user."
}

Write-Phase -Title "Step 3: Invoking Live-Fire Benchmark" -Subtitle "Handing off to the high-performance Python SDK runner..."
Write-Host "This script will now execute the live-fire benchmark."
Write-Host "All core logic resides in 'scripts/ops/run_benchmark.py' for maximum efficiency."

# Build the arguments to pass to the Python script
$pythonArgs = @(
    "scripts/ops/run_benchmark.py",
    "--mode", "live",
    "--cycles", $Cycles,
    "--max-parallel-tx", $MaxParallelTx,
    "--min-profit-usd", $MinProfitUSD,
    "--timeout", $TxConfirmationTimeoutSec,
    "--confirm-live-fire" # Pass confirmation to the Python script
)

Write-Host "`nInvoking Python benchmark runner..."
python @pythonArgs