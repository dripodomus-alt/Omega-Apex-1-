<#
.SYNOPSIS
  Conducts an end-to-end performance benchmark against a local Anvil fork.
.DESCRIPTION
  This script stress-tests the entire arbitrage pipeline using a forked mainnet state.
  It measures the performance of each critical phase: Discovery, Simulation, Broadcasting,
  and Confirmation against the local Anvil RPC endpoint.

  This is a safe way to benchmark the full transaction lifecycle without using real funds.
  It assumes an Anvil fork of Polygon mainnet is already running and accessible at the FORK_SIM_RPC_URL.
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
    [int]$MaxParallelTx = 1,
    [double]$MinProfitUSD = 5.0,
    [int]$TxConfirmationTimeoutSec = 30
)

$ErrorActionPreference = "Stop"
$repoRoot = (Get-Item -Path $PSScriptRoot).Parent.Parent.FullName
Set-Location $repoRoot

# --- Helper Functions (aligned with project standards) ---
function Write-Phase { param([string]$Message) Write-Host "`n" + ("=" * 80) + "`n" + " PHASE: $Message" + "`n" + ("=" * 80) -ForegroundColor Cyan }
function Write-Substep { param([string]$Message) Write-Host "`n -> $Message" }
function Assert-Ok { param([bool]$Condition, [string]$Message) if (!$Condition) { throw $Message } }
function Assert-Command { param([string]$Name, [string]$InstallHint) if (!(Get-Command $Name -ErrorAction SilentlyContinue)) { throw "$Name is not available on PATH. $InstallHint" } }

# --- PRE-FLIGHT CHECKS ---
Write-Phase "Anvil Fork Benchmark: Pre-flight Checks"

Assert-Command "python" "Install Python and ensure it is on PATH."
Assert-Command "cast" "Install Foundry (which includes 'cast') and ensure it is on PATH."
Assert-Command "anvil" "Install Foundry (which includes 'anvil') and ensure it is on PATH."

Write-Substep "Verifying environment and fork configuration..."
if (-not (Test-Path ".env")) { throw ".env file not found. Cannot proceed." }

$envConfig = Get-Content ".env" | Out-String | ConvertFrom-StringData

$privateKey = $envConfig.EXECUTOR_PRIVATE_KEY
Assert-Ok (-not ([string]::IsNullOrEmpty($privateKey) -or $privateKey.Contains("..."))) "EXECUTOR_PRIVATE_KEY is not set in .env. A real private key is required for a fork test."

$rpcUrl = $envConfig.FORK_SIM_RPC_URL
Assert-Ok (-not [string]::IsNullOrEmpty($rpcUrl)) "FORK_SIM_RPC_URL is not set in .env. This is required to target the Anvil fork."

$env:ETH_RPC_URL = $rpcUrl # Set for subsequent cast commands

Write-Substep "Checking Anvil fork connectivity..."
try {
    $chainId = cast chain-id
    Assert-Ok ($chainId -eq 137) "The Anvil fork is running on the wrong chain (ID: $chainId). It must be a fork of Polygon mainnet (ID: 137)."
}
catch {
    throw "Could not connect to Anvil fork at '$rpcUrl'. Please ensure it is running. The `boot_all.ps1` script is marked as obsolete; you may need to start Anvil manually."
}

$configuredAddress = $envConfig.EXECUTOR_WALLET
$balanceWei = cast balance $configuredAddress
$balanceNative = cast from-wei $balanceWei

Write-Host "------------------------------------------------------------" -ForegroundColor Yellow
Write-Host "  BENCHMARK TARGET: Anvil Fork" -ForegroundColor Yellow
Write-Host "  EXECUTOR WALLET : $configuredAddress" -ForegroundColor Yellow
Write-Host "  NETWORK (ChainID) : $chainId" -ForegroundColor Yellow
Write-Host "  RPC ENDPOINT    : $rpcUrl" -ForegroundColor Yellow
Write-Host "  NATIVE BALANCE  : $balanceNative POL (Forked State)" -ForegroundColor Yellow
Write-Host "------------------------------------------------------------" -ForegroundColor Yellow

# --- BENCHMARK EXECUTION ---

$allResults = @()

for ($i = 1; $i -le $Cycles; $i++) {
    Write-Phase "Benchmark Cycle $i of $Cycles"
    $cycleResult = [PSCustomObject]@{
        Cycle = $i
        DiscoveryTimeMs = -1
        BroadcastTimeMs = -1
        ConfirmationTimeMs = -1
        OpportunitiesFound = 0
        TransactionsSent = 0
        TransactionsConfirmed = 0
        TransactionsFailed = 0
        TotalNetProfitUSD = 0
        Error = ""
    }

    try {
        # --- PHASE 1: Opportunity Discovery ---
        Write-Substep "Running discovery pipeline against fork..."
        $discoveryTime = Measure-Command {
            # The --use-fork flag tells the validation script to target the Anvil RPC
            python -m omega_v5.pipeline_validation --use-fork
        }
        $cycleResult.DiscoveryTimeMs = $discoveryTime.TotalMilliseconds
        $opportunities = Get-Content "out\pipeline_validation_latest.json" -Raw | ConvertFrom-Json

        if ($opportunities.opportunities -and $opportunities.opportunities[0].transaction) {
            $profitableOps = $opportunities.opportunities | Where-Object { $_.estimated_profit_usd -ge $MinProfitUSD } | Sort-Object estimated_profit_usd -Descending
        } else {
            throw "The output from 'pipeline_validation.py' does not match the expected format (missing 'transaction' object)."
        }

        $cycleResult.OpportunitiesFound = $profitableOps.Count
        Write-Host "Discovery complete in $($discoveryTime.TotalMilliseconds)ms. Found $($profitableOps.Count) profitable opportunities."

        if ($profitableOps.Count -eq 0) {
            Write-Host "No profitable opportunities found in this cycle. Skipping execution."
            $allResults += $cycleResult
            continue
        }

        $opsToExecute = $profitableOps | Select-Object -First $MaxParallelTx

        # --- PHASE 2: Parallel Broadcast ---
        Write-Substep "Broadcasting $($opsToExecute.Count) transaction(s) to Anvil..."
        $broadcastJobs = @()
        $broadcastTime = Measure-Command {
            foreach ($op in $opsToExecute) {
                $job = Start-ThreadJob -ScriptBlock {
                    param($tx, $rpcUrl, $privateKey)
                    $env:ETH_RPC_URL = $rpcUrl

                    # On a local fork, we can use a simple private key signing flow.
                    $createArgs = @("tx", "create")
                    if ($tx.to) { $createArgs += $tx.to }
                    if ($tx.value -and $tx.value -ne "0") { $createArgs += "--value $($tx.value)" }
                    if ($tx.gasLimit) { $createArgs += "--gas-limit $($tx.gasLimit)" }
                    if ($tx.data) { $createArgs += "--data $($tx.data)" }
                    $createArgs += "--private-key $privateKey"

                    $signedRawTx = ( & cast @createArgs ).Trim()
                    if (-not ($signedRawTx -and $signedRawTx.StartsWith("0x"))) { throw "Failed to create signed transaction with 'cast tx create'." }

                    $txHash = cast send --raw-tx $signedRawTx
                    return $txHash
                } -ArgumentList $op.transaction, $rpcUrl, $privateKey
                $broadcastJobs += $job
            }
            $sentTxs = $broadcastJobs | Wait-Job | Receive-Job
        }
        $cycleResult.BroadcastTimeMs = $broadcastTime.TotalMilliseconds
        $cycleResult.TransactionsSent = $sentTxs.Count
        Write-Host "Broadcast complete in $($broadcastTime.TotalMilliseconds)ms."
        Write-Host "Transaction Hashes: $($sentTxs -join ', ')"

        # --- PHASE 3: Receipt Reconciliation ---
        Write-Substep "Waiting for transaction confirmation (Anvil is instant)..."
        $confirmationTime = Measure-Command {
            $receiptJobs = @()
            foreach ($txHash in $sentTxs) {
                $job = Start-ThreadJob -ScriptBlock {
                    param($hash, $timeout, $rpcUrl)
                    $env:ETH_RPC_URL = $rpcUrl
                    try {
                        # Anvil mines instantly, so timeout can be short.
                        $receipt = cast receipt $hash --timeout "${timeout}s" --json
                        return $receipt | ConvertFrom-Json
                    }
                    catch {
                        return $null # Error
                    }
                } -ArgumentList $txHash, $TxConfirmationTimeoutSec, $rpcUrl
                $receiptJobs += $job
            }
            $receipts = $receiptJobs | Wait-Job | Receive-Job
        }
        $cycleResult.ConfirmationTimeMs = $confirmationTime.TotalMilliseconds

        $confirmedReceipts = $receipts | Where-Object { $_ -ne $null }
        $cycleResult.TransactionsConfirmed = $confirmedReceipts.Count
        $cycleResult.TransactionsFailed = $sentTxs.Count - $confirmedReceipts.Count

        Write-Host "Confirmation phase complete in $($confirmationTime.TotalMilliseconds)ms."
        Write-Host "Confirmed: $($cycleResult.TransactionsConfirmed), Failed/Timed Out: $($cycleResult.TransactionsFailed)"

        # --- PHASE 4: PnL Analysis ---
        $successfulTx = $confirmedReceipts | Where-Object { $_.status -eq '0x1' }
        if ($successfulTx.Count -gt 0) {
            Write-Substep "Invoking PnL Analyzer for profit calculation..."
            $txHashesForPnl = $successfulTx.transactionHash -join ','
            try {
                # The PnL analyzer also needs to target the fork
                $env:RPC_URL = $rpcUrl
                $pnlJson = python -m omega_v5.pnl_analyzer --tx-hashes $txHashesForPnl
                if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrEmpty($pnlJson)) {
                    $pnlResult = $pnlJson | ConvertFrom-Json
                    $cycleResult.TotalNetProfitUSD = $pnlResult.net_profit_usd
                    Write-Host "PnL Analyzer reported a net profit of `$($cycleResult.TotalNetProfitUSD)" -ForegroundColor Green
                } else {
                    Write-Host "PnL Analyzer failed or returned no data. Profit not calculated." -ForegroundColor Yellow
                }
            } catch {
                Write-Host "Could not execute PnL Analyzer: $($_.Exception.Message)" -ForegroundColor Yellow
            }
        }
    }
    catch {
        Write-Host "[ERROR] An error occurred during cycle $i: $($_.Exception.Message)" -ForegroundColor Red
        $cycleResult.Error = $_.Exception.Message
    }
    finally {
        $allResults += $cycleResult
    }
}

Write-Phase "Benchmark Summary"

$allResults | Format-Table -AutoSize

$avgDiscovery = ($allResults | Where-Object { $_.DiscoveryTimeMs -gt 0 } | Measure-Object -Property DiscoveryTimeMs -Average).Average
$avgBroadcast = ($allResults | Where-Object { $_.BroadcastTimeMs -gt 0 } | Measure-Object -Property BroadcastTimeMs -Average).Average
$avgConfirm = ($allResults | Where-Object { $_.ConfirmationTimeMs -gt 0 } | Measure-Object -Property ConfirmationTimeMs -Average).Average
$totalConfirmed = ($allResults | Measure-Object -Property TransactionsConfirmed -Sum).Sum
$totalSent = ($allResults | Measure-Object -Property TransactionsSent -Sum).Sum
$totalProfit = ($allResults | Measure-Object -Property TotalNetProfitUSD -Sum).Sum
$successRate = if ($totalSent -gt 0) { ($totalConfirmed / $totalSent) * 100 } else { 0 }

Write-Host "`n--- Averages & Totals ---"
Write-Host "Average Discovery Latency : $(if ($avgDiscovery) { [math]::Round($avgDiscovery, 2) } else { 'N/A' }) ms"
Write-Host "Average Broadcast Latency : $(if ($avgBroadcast) { [math]::Round($avgBroadcast, 2) } else { 'N/A' }) ms"
Write-Host "Average Confirmation Time : $(if ($avgConfirm) { [math]::Round($avgConfirm, 2) } else { 'N/A' }) ms"
Write-Host "Overall Success Rate      : $([math]::Round($successRate, 2)) % ($totalConfirmed / $totalSent)"
Write-Host "Total Net Profit (USD)    : $([math]::Round($totalProfit, 2))"
Write-Host "---------------------------"

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
