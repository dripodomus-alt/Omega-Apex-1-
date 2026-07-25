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
$repoRoot = (Get-Item -Path $PSScriptRoot).Parent.Parent.FullName
Set-Location $repoRoot

# --- Helper Functions (aligned with project standards) ---
function Write-Phase { param([string]$Message) Write-Host "`n" + ("=" * 80) + "`n" + " PHASE: $Message" + "`n" + ("=" * 80) -ForegroundColor Cyan }
function Write-Substep { param([string]$Message) Write-Host "`n -> $Message" }
function Assert-Ok { param([bool]$Condition, [string]$Message) if (!$Condition) { throw $Message } }
function Assert-Command { param([string]$Name, [string]$InstallHint) if (!(Get-Command $Name -ErrorAction SilentlyContinue)) { throw "$Name is not available on PATH. $InstallHint" } }
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
                    # Overwrite existing key, effectively taking the last one.
                    $config[$key] = $value
                }
            }
        }
    }
    return $config
}

# --- PRE-FLIGHT CHECKS ---
Write-Phase "Pre-flight System & Sanity Checks"

if (-not $ConfirmLiveFire) {
    throw "This is a high-risk script. You must explicitly acknowledge the risk by adding the '-ConfirmLiveFire' parameter."
}

Assert-Command "python" "Install Python and ensure it is on PATH."
Assert-Command "cast" "Install Foundry (which includes 'cast') and ensure it is on PATH."

Write-Substep "Verifying environment and wallet configuration..."
if (-not (Test-Path ".env")) { throw ".env file not found. Cannot proceed." }

# Use a robust parser that handles duplicate keys by taking the last value.
$envConfig = Parse-EnvFile -FilePath ".env"

Write-Host "Resolving best broadcast RPC endpoint via rpc_layer..."
$rpcUrl = (& python -m omega_v5.broadcast_rpc 2>$null | Where-Object { $_ -match "^https?://" } | Select-Object -First 1).Trim()
Assert-Ok (-not [string]::IsNullOrEmpty($rpcUrl)) "Could not resolve a broadcast RPC URL via rpc_layer. Check rpc_benchmark.json and .env fallbacks."
Write-Host "Using broadcast RPC: $rpcUrl" -ForegroundColor Green

$env:ETH_RPC_URL = $rpcUrl # Set for subsequent cast commands

$publicRpc = $envConfig.TELEMETRY_RPC_URL
Assert-Ok (-not [string]::IsNullOrEmpty($publicRpc)) "TELEMETRY_RPC_URL is not set in .env. A public RPC is required for chain sync verification."

$executorContractAddress = (& python -m omega_v5.executor_address 2>$null | Where-Object { $_ -match '^0x[a-fA-F0-9]{40}$' } | Select-Object -First 1).Trim()
Assert-Ok (-not [string]::IsNullOrEmpty($executorContractAddress)) "Could not resolve the main EXECUTOR_CONTRACT from config.py. Check .env variables like C1_PAYLOAD_TARGET, EXECUTOR_CONTRACT_ADDR, etc."
Assert-Ok ($executorContractAddress.Length -eq 42 -and $executorContractAddress.StartsWith("0x")) "Resolved EXECUTOR_CONTRACT '$executorContractAddress' is not a valid Ethereum address."

Write-Substep "Verifying chain synchronization..."
try {
    $primaryBlock = cast block-number --rpc-url $rpcUrl
    $publicBlock = cast block-number --rpc-url $publicRpc
    $blockLag = $publicBlock - $primaryBlock
    Assert-Ok ([Math]::Abs($blockLag) -lt 5) "FATAL: High block lag between primary RPC ($rpcUrl) and public RPC ($publicRpc). Lag: $blockLag blocks. Halting for safety."
    Write-Host "RPCs are synchronized (Lag: $blockLag blocks)." -ForegroundColor Green
} catch {
    throw "Could not verify chain synchronization. Primary or public RPC may be down. Error: $($_.Exception.Message)"
}

$chainId = cast chain-id

Write-Substep "Sanity-checking executor wallet..."
$privateKey = $envConfig.EXECUTOR_PRIVATE_KEY
Assert-Ok (-not ([string]::IsNullOrEmpty($privateKey) -or $privateKey.Contains("..."))) "EXECUTOR_PRIVATE_KEY is not set in .env for a PrivateKey-signed test."
$derivedAddress = (cast wallet address $privateKey).Trim()
$configuredAddress = $envConfig.EXECUTOR_WALLET
Assert-Ok ($derivedAddress.ToLower() -eq $configuredAddress.ToLower()) "FATAL: Address derived from EXECUTOR_PRIVATE_KEY ($derivedAddress) does not match EXECUTOR_WALLET ($configuredAddress) in .env file. Check for typos."
Write-Host "Wallet sanity checks passed." -ForegroundColor Green

Write-Host "------------------------------------------------------------" -ForegroundColor Yellow
Write-Host "  SIGNER TYPE     : PrivateKey (SDK Mode)" -ForegroundColor Yellow
Write-Host "  EXECUTOR WALLET : $envConfig.EXECUTOR_WALLET" -ForegroundColor Yellow
Write-Host "  NETWORK (ChainID) : $chainId" -ForegroundColor Yellow
Write-Host "  RPC ENDPOINT    : $rpcUrl" -ForegroundColor Yellow
Write-Host "------------------------------------------------------------" -ForegroundColor Yellow

$initialBalanceWei = cast balance $envConfig.EXECUTOR_WALLET
$initialBalanceNative = cast from-wei $initialBalanceWei
Write-Host "Initial wallet balance: $initialBalanceNative POL" -ForegroundColor Green

$confirmation = Read-Host "`nThis script will execute REAL transactions on the network above. Are you absolutely sure you want to proceed? [y/N]"
if ($confirmation -ne 'y') {
    throw "Live-fire benchmark cancelled by user."
}

Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host " Live-Fire Benchmark (SDK-Driven)" -ForegroundColor Cyan
Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host "This script will now invoke the high-performance Python benchmark runner."
Write-Host "All core logic has been migrated to 'scripts/ops/run_benchmark.py' for efficiency."

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