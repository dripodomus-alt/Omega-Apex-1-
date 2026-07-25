<#
.SYNOPSIS
  Conducts a finalized, live-fire, end-to-end performance benchmark of the Omega V5 system.
.DESCRIPTION
  This script stress-tests the entire arbitrage pipeline using live market data and
  executes real transactions on the blockchain. It measures the performance of each
  critical phase: Discovery, Simulation, Broadcasting, and Confirmation.

  It includes critical safety checks, such as verifying the private key against the
  configured wallet address and displaying the wallet's balance before execution.

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

  # Run a benchmark using a Ledger hardware wallet.
  .\scripts\ops\run_live_fire_benchmark.ps1 -ConfirmLiveFire -Signer Ledger

  # Run a benchmark using a Google Cloud KMS key.
  $kmsArgs = @{ KeyName = "projects/my-proj/locations/us-east1/keyRings/my-ring/cryptoKeys/omega-key/cryptoKeyVersions/1" }
  .\scripts\ops\run_live_fire_benchmark.ps1 -ConfirmLiveFire -Signer GcpKms -SignerArgs $kmsArgs
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [switch]$ConfirmLiveFire,

    [Parameter()]
    [ValidateSet('PrivateKey', 'Ledger', 'GcpKms')]
    [string]$Signer = 'PrivateKey',

    [Parameter()]
    [hashtable]$SignerArgs = @{},

    [int]$Cycles = 1,
    [int]$MaxParallelTx = 1,
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

# --- PRE-FLIGHT CHECKS ---
Write-Phase "Pre-flight System & Sanity Checks"

if (-not $ConfirmLiveFire) {
    throw "This is a high-risk script. You must explicitly acknowledge the risk by adding the '-ConfirmLiveFire' parameter."
}

Assert-Command "python" "Install Python and ensure it is on PATH."
Assert-Command "cast" "Install Foundry (which includes 'cast') and ensure it is on PATH."

Write-Substep "Verifying environment and wallet configuration..."
if (-not (Test-Path ".env")) { throw ".env file not found. Cannot proceed." }

$envConfig = Get-Content ".env" | Out-String | ConvertFrom-StringData

$rpcUrl = $envConfig.BROADCAST_RPC_URL
Assert-Ok (-not [string]::IsNullOrEmpty($rpcUrl)) "BROADCAST_RPC_URL is not set in .env. A writeable RPC endpoint is required."

$env:ETH_RPC_URL = $rpcUrl # Set for subsequent cast commands

$chainId = cast chain-id

if ($Signer -eq 'PrivateKey') {
    Write-Substep "Sanity-checking executor wallet (PrivateKey mode)..."
    $privateKey = $envConfig.EXECUTOR_PRIVATE_KEY
    Assert-Ok (-not ([string]::IsNullOrEmpty($privateKey) -or $privateKey.Contains("..."))) "EXECUTOR_PRIVATE_KEY is not set in .env for a PrivateKey-signed test."

    $derivedAddress = (cast wallet address $privateKey).Trim()
    $configuredAddress = $envConfig.EXECUTOR_WALLET
    Assert-Ok ($derivedAddress.ToLower() -eq $configuredAddress.ToLower()) "FATAL: Address derived from EXECUTOR_PRIVATE_KEY ($derivedAddress) does not match EXECUTOR_WALLET ($configuredAddress) in .env file. Check for typos."

    $balanceWei = cast balance $configuredAddress
    $balanceEth = cast from-wei $balanceWei
    Write-Host "Wallet sanity checks passed." -ForegroundColor Green
}
else {
    Write-Substep "Preparing for signing with '$Signer'..."
    $configuredAddress = "N/A (derived from $Signer)"
    $balanceEth = "N/A (derived from $Signer)"
    Write-Host "Wallet address and balance will be determined by the '$Signer' device/service." -ForegroundColor Yellow
    if ($Signer -eq 'GcpKms') {
        Assert-Ok ($SignerArgs.ContainsKey('KeyName') -and -not [string]::IsNullOrEmpty($SignerArgs.KeyName)) "-SignerArgs must contain 'KeyName' for GcpKms signer."
        Assert-Ok ($SignerArgs.KeyName.StartsWith("projects/")) "GCP KMS KeyName must be the full resource name (e.g., projects/my-proj/locations/...)"
        $gcloudAuthStatus = gcloud auth list --filter=status:ACTIVE --format="value(account)"
        Assert-Ok (-not [string]::IsNullOrEmpty($gcloudAuthStatus)) "You must be authenticated with gcloud to use the GcpKms signer. Run 'gcloud auth login'."
        Write-Host "Using GCP Account for KMS: $gcloudAuthStatus" -ForegroundColor Green
    }
    if ($Signer -eq 'Ledger') {
        Write-Host "Please ensure your Ledger device is connected, unlocked, and the Ethereum app is open." -ForegroundColor Yellow
    }
}

Write-Host "------------------------------------------------------------" -ForegroundColor Yellow
Write-Host "  SIGNER TYPE     : $Signer" -ForegroundColor Yellow
Write-Host "  EXECUTOR WALLET : $configuredAddress" -ForegroundColor Yellow
Write-Host "  NETWORK (ChainID) : $chainId" -ForegroundColor Yellow
Write-Host "  RPC ENDPOINT    : $rpcUrl" -ForegroundColor Yellow
Write-Host "  NATIVE BALANCE  : $balanceEth ETH" -ForegroundColor Yellow
Write-Host "------------------------------------------------------------" -ForegroundColor Yellow

$confirmation = Read-Host "`nThis script will execute REAL transactions on the network above. Are you absolutely sure you want to proceed? [y/N]"
if ($confirmation -ne 'y') {
    throw "Live-fire benchmark cancelled by user."
}

# --- BENCHMARK EXECUTION ---

$allResults = @()
$privateKeyForSigning = if ($Signer -eq 'PrivateKey') { $envConfig.EXECUTOR_PRIVATE_KEY } else { $null }

for ($i = 1; $i -le $Cycles; $i++) {
    Write-Phase "Benchmark Cycle $i of $Cycles"
    $cycleResult = [PSCustomObject]@{
        Cycle = $i
        DiscoveryTimeMs = -1
        SimulationTimeMs = -1
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
        Write-Substep "Running discovery pipeline..."
        $discoveryTime = Measure-Command {
            # This command should generate a file with potential opportunities.
            # We assume it creates 'out/pipeline_validation_latest.json' based on your other scripts.
            python -m omega_v5.pipeline_validation
        }
        $cycleResult.DiscoveryTimeMs = $discoveryTime.TotalMilliseconds
        $opportunities = Get-Content "out\pipeline_validation_latest.json" -Raw | ConvertFrom-Json

        # DATA CONTRACT CHANGE: With external signers, the Python script must now output an *unsigned* transaction object.
        # Old format: { "opportunities": [ { "estimated_profit_usd": 10, "raw_tx": "0x..." } ] }
        # New format: { "opportunities": [ { "estimated_profit_usd": 10, "transaction": { "to": "0x..", "data": "0x..", "value": "0", "gasLimit": "500000" } } ] }
        if ($opportunities.opportunities -and $opportunities.opportunities[0].transaction) {
            $profitableOps = $opportunities.opportunities | Where-Object { $_.estimated_profit_usd -ge $MinProfitUSD } | Sort-Object estimated_profit_usd -Descending
        } else {
            throw "The output from 'pipeline_validation.py' does not match the expected format for external signers (missing 'transaction' object)."
        }

        $cycleResult.OpportunitiesFound = $profitableOps.Count
        Write-Host "Discovery complete in $($discoveryTime.TotalMilliseconds)ms. Found $($profitableOps.Count) profitable opportunities."

        if ($profitableOps.Count -eq 0) {
            Write-Host "No profitable opportunities found in this cycle. Skipping execution."
            $allResults += $cycleResult
            continue
        }

        # --- PHASE 2: Transaction Simulation & Preparation ---
        # In this model, we assume the discovery phase already prepared the raw_tx.
        # If you have a separate simulation step, it would go here.
        # For this benchmark, we'll consider preparation time as part of discovery.
        $cycleResult.SimulationTimeMs = 0 # Placeholder

        $opsToExecute = $profitableOps | Select-Object -First $MaxParallelTx

        # --- PHASE 3: Parallel Broadcast ---
        Write-Substep "Broadcasting $($opsToExecute.Count) transaction(s) in parallel..."
        $broadcastJobs = @()
        $broadcastTime = Measure-Command {
            foreach ($op in $opsToExecute) {
                $job = Start-ThreadJob -ScriptBlock {
                    param($tx, $rpcUrl, $signer, $signerArgs, $privateKeyForSigning)

                    $env:ETH_RPC_URL = $rpcUrl

                    if ($signer -eq 'PrivateKey') {
                        # For private key, we must create the signed raw transaction first, then broadcast it.
                        $createArgs = @("tx", "create")
                        if ($tx.to) { $createArgs += $tx.to }
                        if ($tx.value -and $tx.value -ne "0") { $createArgs += "--value $($tx.value)" }
                        if ($tx.gasLimit) { $createArgs += "--gas-limit $($tx.gasLimit)" }
                        if ($tx.data) { $createArgs += "--data $($tx.data)" }
                        $createArgs += "--private-key $privateKeyForSigning"

                        $signedRawTx = ( & cast @createArgs ).Trim()
                        if (-not ($signedRawTx -and $signedRawTx.StartsWith("0x"))) { throw "Failed to create signed transaction with 'cast tx create'." }

                        $txHash = cast send --raw-tx $signedRawTx
                        return $txHash
                    }
                    else {
                        # For hardware/KMS signers, `cast send` handles signing and broadcasting in one step.
                        $sendArgs = @("send")
                        $sendArgs += $tx.to
                        if ($tx.value -and $tx.value -ne "0") { $sendArgs += "--value $($tx.value)" }
                        if ($tx.gasLimit) { $sendArgs += "--gas-limit $($tx.gasLimit)" }
                        if ($tx.data) { $sendArgs += "--data $($tx.data)" }

                        switch ($signer) {
                            'Ledger' {
                                $sendArgs += "--ledger"
                                if ($signerArgs.HdPath) { $sendArgs += "--hd-path $($signerArgs.HdPath)" }
                            }
                            'GcpKms' { $sendArgs += "--gcp-kms"; $sendArgs += $signerArgs.KeyName }
                        }

                        $txHash = & cast @sendArgs
                        return $txHash
                    }
                } -ArgumentList $op.transaction, $rpcUrl, $Signer, $SignerArgs, $privateKeyForSigning
                $broadcastJobs += $job
            }
            $sentTxs = $broadcastJobs | Wait-Job | Receive-Job
        }
        $cycleResult.BroadcastTimeMs = $broadcastTime.TotalMilliseconds
        $cycleResult.TransactionsSent = $sentTxs.Count
        Write-Host "Broadcast complete in $($broadcastTime.TotalMilliseconds)ms."
        Write-Host "Transaction Hashes: $($sentTxs -join ', ')"

        # --- PHASE 4: Receipt Reconciliation ---
        Write-Substep "Waiting for transaction confirmation (Timeout: ${TxConfirmationTimeoutSec}s)..."
        $confirmationTime = Measure-Command {
            $receiptJobs = @()
            foreach ($txHash in $sentTxs) {
                $job = Start-ThreadJob -ScriptBlock {
                    param($hash, $timeout, $rpcUrl)
                    $env:ETH_RPC_URL = $rpcUrl
                    try {
                        # Use 'cast' to wait for the receipt
                        $receipt = cast receipt $hash --timeout "${timeout}s" --json
                        return $receipt | ConvertFrom-Json
                    }
                    catch {
                        return $null # Timeout or error
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

        # --- PHASE 5: PnL Analysis ---
        $successfulTx = $confirmedReceipts | Where-Object { $_.status -eq '0x1' }
        if ($successfulTx.Count -gt 0) {
            Write-Host "$($successfulTx.Count) transactions succeeded on-chain."
            Write-Substep "Invoking PnL Analyzer for accurate profit calculation..."
            $txHashesForPnl = $successfulTx.transactionHash -join ','

            # This assumes you create a 'pnl_analyzer.py' module in the omega_v5 package.
            # It should take hashes, analyze them (e.g., using traces or event logs),
            # and print a JSON object like `{"net_profit_usd": 12.34}` to stdout.
            try {
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
Write-Host "Average Confirmation Time : $(if ($avgConfirm) { [math]::Round($avgConfirm / 1000, 2) } else { 'N/A' }) s"
Write-Host "Overall Success Rate      : $([math]::Round($successRate, 2)) % ($totalConfirmed / $totalSent)"
Write-Host "Total Net Profit (USD)    : $([math]::Round($totalProfit, 2))"
Write-Host "---------------------------"

```