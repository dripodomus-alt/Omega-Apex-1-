<#
.SYNOPSIS

Runs the high-performance, SDK-driven benchmark against a local Anvil fork.
.DESCRIPTION
  This script is a lightweight wrapper around the new `run_benchmark.py` script,
  which uses the web3.py SDK for superior performance and maintainability.

  It ensures the Anvil fork is running and then invokes the Python script in
  'anvil' mode, passing along any specified parameters. This provides a consistent
  entry point while centralizing the core logic in a more efficient language.
.EXAMPLE
  # First, start an Anvil fork in a separate terminal.
  # The fork must use an RPC URL for Polygon mainnet (chain 137).

  # Then, run a single benchmark cycle against the fork.
  .\scripts\ops\run_anvil_fork_benchmark.ps1

  # Run 5 benchmark cycles in a row.
  .\scripts\ops\run_anvil_fork_benchmark.ps1 -Cycles 5

  # Run a benchmark targeting opportunities with at least $10 estimated profit.
  .\scripts\ops\run_anvil_fork_benchmark.ps1 -MinProfitUSD 10
#>
[CmdletBinding()]
param(
    [int]$Cycles = 1,
    [int]$MaxParallelTx = 10,
    [double]$MinProfitUSD = 5.0,
    [int]$TxConfirmationTimeoutSec = 30
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
function Assert-Ok { param([bool]$Condition, [string]$Message) if (-not $Condition) { throw $Message } }
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
                    $value = $parts[1].Trim()
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
Write-Phase -Title "Step 1: Pre-flight System & Sanity Checks" -Subtitle "Verifying toolchain and Anvil fork connectivity..."

Assert-Command -Name "python" -InstallHint "Install Python and ensure it is on PATH."
Assert-Command -Name "cast" -InstallHint "Install Foundry (which includes 'cast') and ensure it is on PATH."
Assert-Command -Name "anvil" -InstallHint "Install Foundry (which includes 'anvil') and ensure it is on PATH."

$envConfig = Parse-EnvFile -FilePath $resolvedEnvPath
$forkRpcUrl = $envConfig.FORK_RPC_URL
if ([string]::IsNullOrEmpty($forkRpcUrl)) {
    $forkRpcUrl = "http://127.0.0.1:8545"
    Write-Host "FORK_RPC_URL not found in '$resolvedEnvPath', defaulting to $forkRpcUrl" -ForegroundColor Yellow
}

try {
    Write-Host "Probing Anvil fork at $forkRpcUrl..."
    $anvilChainId = cast chain-id --rpc-url $forkRpcUrl
    Assert-Ok -Condition ($anvilChainId -eq 137) -Message "Anvil fork is running on wrong chain (ID: $anvilChainId). It must be a fork of Polygon mainnet (ID: 137)."
    Write-Host "Anvil fork detected on Polygon mainnet (ChainID: $anvilChainId)." -ForegroundColor Green
} catch {
    throw "Could not connect to Anvil fork at '$forkRpcUrl'. Is Anvil running in a separate terminal? Error: $($_.Exception.Message)"
}

Write-Phase -Title "Step 2: Invoking Anvil Fork Benchmark" -Subtitle "Handing off to the high-performance Python SDK runner..."
Write-Host "This script will now execute the benchmark against the local Anvil fork."
Write-Host "All core logic resides in 'scripts/ops/run_benchmark.py' for maximum efficiency."

# Build the arguments to pass to the Python script
$pythonArgs = @(
    "scripts/ops/run_benchmark.py",
    "--mode", "anvil",
    "--cycles", $Cycles,
    "--max-parallel-tx", $MaxParallelTx,
    "--min-profit-usd", $MinProfitUSD,
    "--timeout", $TxConfirmationTimeoutSec
)

Write-Host "`nInvoking Python benchmark runner..."
python @pythonArgs

```

#### Deployment vs. Local: What's the Difference?

This is the most important concept to grasp when moving from development to production. Running on your local drive is for **building and testing**. A production deployment is for **making money, securely and reliably.**

Here is a direct comparison:

| Feature | Local Development (Your PC) | Production Deployment (GCP VM) | Why it Matters |
| :--- | :--- | :--- | :--- |
| **Environment** | Your personal computer, running alongside your web browser, code editor, etc. | A dedicated, isolated Linux server in a Google data center. | **Reliability.** Your PC can be slow, go to sleep, or crash. A server is built for 24/7 uptime. |
| **Security** | `EXECUTOR_PRIVATE_KEY` is in a plain-text `.env` file on your hard drive. | Private key is stored in **GCP Secret Manager** and only loaded into memory at runtime. The VM is hardened with firewall rules. | **Fund Safety.** A compromised local machine means your key is stolen instantly. A production deployment makes this exponentially harder. |
| **Uptime** | The bot only runs when you manually start it and your PC is on. | The bot runs **24/7/365**, managed by `pm2`, which automatically restarts it if it ever crashes. | **Profitability.** The market never sleeps. If your bot isn't running, it's missing opportunities. |
| **Performance** | Slower. Your home internet has higher latency to blockchain nodes. Other apps compete for CPU. | **Faster.** The VM is in a data center with low-latency connections to RPC providers. It has dedicated CPU and RAM. | **Execution Speed.** In arbitrage, milliseconds matter. Lower latency means a higher chance of your transaction succeeding before the opportunity disappears. |
| **Operations** | Manual. You start scripts, watch logs in a terminal, and have to be at your computer. | **Autonomous & Remote.** The `cloud_run_finalizer.ps1` script automates the entire boot and verification process. You can monitor and control it from anywhere via the secure web dashboard. | **Scalability & Freedom.** A deployed system runs itself. You become an operator who monitors performance, not a user who has to constantly run commands. |

In short, running locally is like building a race car in your garage. Deploying it to a secure VM is like putting that car on a professional racetrack with a pit crew, ready to compete 24/7.
