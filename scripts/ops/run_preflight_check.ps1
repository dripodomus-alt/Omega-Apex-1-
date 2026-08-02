<#
.SYNOPSIS
  Runs a comprehensive pre-flight check of the entire system configuration.
.DESCRIPTION
  This script is a master validation tool that verifies all critical components
  required for the Omega V5 engine to run successfully. It checks:
  - Local toolchain dependencies (python, cast, etc.).
  - The presence and validity of the .env file and its critical variables.
  - RPC connectivity, chain ID, and synchronization status.
  - Wallet integrity by matching the private key to the configured address.
  - On-chain presence of the executor smart contract.
  - Internal Python configuration integrity via `validate_config.py`.

  Run this script before any live or benchmark run to ensure a stable environment.
.EXAMPLE
  # Run the full pre-flight check.
  .\scripts\ops\run_preflight_check.ps1

  # Run the check and skip the RPC sync test (useful for single-node setups).
  .\scripts\ops\run_preflight_check.ps1 -SkipRpcSyncCheck

  # Run the check and skip the wallet balance check.
  .\scripts\ops\run_preflight_check.ps1 -SkipBalanceCheck
#>
[CmdletBinding()]
param(
    [switch]$SkipRpcSyncCheck,
    [switch]$SkipBalanceCheck
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

$totalTime = Measure-Command {
    # --- 1. Toolchain Verification ---
    Write-Phase -Title "Step 1: Verifying Toolchain Dependencies"
    Assert-Command -Name "python" -InstallHint "Install Python (3.10+) and ensure it is on PATH."
    Assert-Command -Name "cast" -InstallHint "Install Foundry (which includes 'cast') and ensure it is on PATH."
    Assert-Command -Name "anvil" -InstallHint "Install Foundry (which includes 'anvil') and ensure it is on PATH."
    Assert-Command -Name "node" -InstallHint "Install Node.js and ensure it is on PATH."
    Write-Host "✅ All required tools are available on PATH." -ForegroundColor Green

    # --- 2. Environment Configuration (.env) ---
    Write-Phase -Title "Step 2: Verifying Environment Configuration"
    Assert-Ok -Condition (Test-Path $resolvedEnvPath) -Message "Environment file not found at '$resolvedEnvPath'. Configure OMEGA_ENV_PATH or environment profile."
    $envConfig = Parse-EnvFile -FilePath $resolvedEnvPath

    Assert-Ok -Condition ($envConfig.ContainsKey("PRIMARY_READ_RPC_URL")) -Message "PRIMARY_READ_RPC_URL is not set in .env."
    Assert-Ok -Condition ($envConfig.ContainsKey("BROADCAST_RPC_URL")) -Message "BROADCAST_RPC_URL is not set in .env."
    Assert-Ok -Condition ($envConfig.ContainsKey("EXECUTOR_WALLET")) -Message "EXECUTOR_WALLET is not set in .env."
    Assert-Ok -Condition ($envConfig.ContainsKey("EXECUTOR_PRIVATE_KEY")) -Message "EXECUTOR_PRIVATE_KEY is not set in .env."
    Write-Host "✅ Environment file found at '$resolvedEnvPath' and critical variables are present." -ForegroundColor Green

    # --- Conditional: Redis Connectivity ---
    if ($envConfig.ContainsKey("REDIS_ENABLED") -and $envConfig.REDIS_ENABLED.ToLower() -eq 'true') {
        Write-Phase -Title "Step 2.5: Verifying Redis Connectivity"
        Assert-Command -Name "redis-cli" -InstallHint "Install Redis (which includes 'redis-cli') or ensure 'redis-cli' is on your PATH."
        Assert-Ok -Condition ($envConfig.ContainsKey("REDIS_URL")) -Message "REDIS_ENABLED is true, but REDIS_URL is not set in .env."
        
        $redisUrl = $envConfig.REDIS_URL
        Write-Host "Pinging Redis server at $redisUrl..."
        try {
            # The -u flag is the most robust way to handle complex URLs with auth/db.
            $pingResult = redis-cli -u $redisUrl PING
            Assert-Ok -Condition ($pingResult -eq "PONG") -Message "Redis server responded with '$pingResult' instead of 'PONG'. The server is running but may be misconfigured."
            Write-Host "✅ Redis server responded with PONG." -ForegroundColor Green
        } catch {
            throw "Could not connect to Redis server at '$redisUrl'. Please ensure the Redis server is running and accessible, and that the URL is correct in your .env file. Error: $($_.Exception.Message)"
        }
    } else {
        Write-Host "`n[INFO] Redis is disabled (REDIS_ENABLED is not 'true' in .env). Skipping Redis check." -ForegroundColor Gray
    }

    # --- 3. RPC and Chain Connectivity ---
    Write-Phase -Title "Step 3: Verifying RPC and Chain Connectivity"
    $primaryRpc = $envConfig.PRIMARY_READ_RPC_URL
    $broadcastRpc = $envConfig.BROADCAST_RPC_URL
    $env:ETH_RPC_URL = $primaryRpc # Set for subsequent cast commands

    try {
        $chainId = cast chain-id
        Assert-Ok -Condition ($chainId -eq 137) -Message "RPC endpoint ($primaryRpc) is connected to the wrong chain (ID: $chainId). Expected Polygon mainnet (ID: 137)."
        Write-Host "✅ Connected to Polygon Mainnet (ChainID: $chainId) via primary RPC." -ForegroundColor Green
    } catch {
        throw "Could not connect to primary RPC at '$primaryRpc'. Is the URL correct and the service running? Error: $($_.Exception.Message)"
    }

    if (-not $SkipRpcSyncCheck) {
        $publicRpc = "https://polygon-bor-rpc.publicnode.com"
        try {
            $primaryBlock = cast block-number --rpc-url $primaryRpc
            $publicBlock = cast block-number --rpc-url $publicRpc
            $blockLag = $publicBlock - $primaryBlock
            Assert-Ok -Condition ([Math]::Abs($blockLag) -lt 10) -Message "High block lag detected. Primary RPC is lagging by $blockLag blocks. Halting for safety."
            Write-Host "✅ Primary RPC is synchronized with public node (Lag: $blockLag blocks)." -ForegroundColor Green
        } catch {
            Write-Host "⚠️ Could not verify RPC sync against public node. This might be a transient network issue. Error: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }

    # --- 4. Wallet and Executor Integrity ---
    Write-Phase -Title "Step 4: Verifying Wallet and Executor Integrity"
    $privateKey = $envConfig.EXECUTOR_PRIVATE_KEY
    $configuredAddress = $envConfig.EXECUTOR_WALLET
    Assert-Ok -Condition (-not ([string]::IsNullOrEmpty($privateKey) -or $privateKey.Contains("..."))) -Message "EXECUTOR_PRIVATE_KEY is not set or is a placeholder value in .env."
    Assert-Ok -Condition ($configuredAddress.Length -eq 42 -and $configuredAddress.StartsWith("0x")) -Message "EXECUTOR_WALLET '$configuredAddress' is not a valid Ethereum address."

    $derivedAddress = (cast wallet address $privateKey).Trim()
    Assert-Ok -Condition ($derivedAddress.ToLower() -eq $configuredAddress.ToLower()) -Message "Address derived from EXECUTOR_PRIVATE_KEY ($derivedAddress) does not match EXECUTOR_WALLET ($configuredAddress) in .env file. Check for typos."
    Write-Host "✅ Wallet private key correctly derives to the configured executor address." -ForegroundColor Green

    if (-not $SkipBalanceCheck) {
        $balanceWei = cast balance $configuredAddress
        Assert-Ok -Condition ($balanceWei -gt 0) -Message "Executor wallet $configuredAddress has a zero balance. It needs POL to pay for gas."
        $balanceNative = cast from-wei $balanceWei
        Write-Host "✅ Wallet has a non-zero balance: $balanceNative POL." -ForegroundColor Green
    }

    # --- Live Mode Security Checks ---
    if ($envConfig.ContainsKey("EXECUTION_MODE") -and $envConfig.EXECUTION_MODE.ToLower() -eq 'live') {
        Write-Host "Verifying live-mode wallet security configuration..." -ForegroundColor Yellow
        $profitRecipient = $envConfig.PROFIT_RECIPIENT_ADDRESS
        Assert-Ok -Condition (-not [string]::IsNullOrEmpty($profitRecipient)) -Message "EXECUTION_MODE is 'live', but PROFIT_RECIPIENT_ADDRESS is not set in .env. This is required for secure profit collection."
        Assert-Ok -Condition ($profitRecipient.Length -eq 42 -and $profitRecipient.StartsWith("0x")) -Message "PROFIT_RECIPIENT_ADDRESS '$profitRecipient' is not a valid Ethereum address."
        Assert-Ok -Condition ($profitRecipient.ToLower() -ne $configuredAddress.ToLower()) -Message "SECURITY RISK: PROFIT_RECIPIENT_ADDRESS cannot be the same as EXECUTOR_WALLET in live mode. Use a separate, secure wallet (e.g., a hardware wallet) for profits."
        Write-Host "✅ Profit recipient is configured to a separate, secure address." -ForegroundColor Green
    }

    # --- 5. On-Chain Contract Verification ---
    Write-Phase -Title "Step 5: Verifying On-Chain Contracts"
    $executorContractAddress = (& python -m omega_v5.executor_address 2>$null | Where-Object { $_ -match '^0x[a-fA-F0-9]{40}$' } | Select-Object -First 1).Trim()
    Assert-Ok -Condition (-not [string]::IsNullOrEmpty($executorContractAddress)) -Message "Could not resolve the EXECUTOR_CONTRACT address from config. Check .env variables."

    $contractCode = cast code $executorContractAddress
    Assert-Ok -Condition ($contractCode -ne "0x") -Message "No contract bytecode found at the configured executor address '$executorContractAddress' on chain 137. Is the contract deployed and the address correct in .env?"
    Write-Host "✅ Found deployed bytecode for executor contract at $executorContractAddress." -ForegroundColor Green

    # --- 5.5 On-Chain Adapter Configuration Verification ---
    Write-Phase -Title "Step 5.5: Verifying On-Chain Adapter Registrations"
    $adapterToProtocolIdMap = @{
        "OmegaV2CpmmAdapter"           = 1
        "OmegaV3ClmmAdapter"           = 2
        "OmegaAlgebraClmmAdapter"      = 3
        "OmegaCurveStableAdapter"      = 4
        "OmegaBalancerWeightedAdapter" = 5
        "OmegaKyberElasticAdapter"     = 6
        "OmegaDodoPmmAdapter"          = 7
    }
    $allAdaptersOk = $true
    foreach ($adapterName in $adapterToProtocolIdMap.Keys) {
        $protocolId = $adapterToProtocolIdMap.$adapterName
        try {
            $registeredAddress = (cast call $executorContractAddress "adapters(uint8) returns (address)" $protocolId).Trim()
            if ($registeredAddress -eq "0x0000000000000000000000000000000000000000") {
                Write-Host "  [FAIL] Adapter for '$adapterName' (Protocol ID $protocolId) is not registered on-chain." -ForegroundColor Red
                $allAdaptersOk = $false
            } else {
                Write-Host "  [OK] Adapter for '$adapterName' (ID $protocolId) is registered at $registeredAddress." -ForegroundColor Gray
            }
        } catch {
            Write-Host "  [FAIL] Could not query adapter for '$adapterName' (Protocol ID $protocolId). Error: $($_.Exception.Message)" -ForegroundColor Red
            $allAdaptersOk = $false
        }
    }
    Assert-Ok -Condition $allAdaptersOk -Message "One or more on-chain adapters are not correctly registered. Run 'configure_onchain_executor.ps1' to fix."
    Write-Host "✅ All required on-chain adapters are registered with the executor." -ForegroundColor Green

    # --- 6. Internal Configuration Integrity ---
    Write-Phase -Title "Step 6: Verifying Internal Python Configuration"
    python scripts/ops/validate_config.py
    Assert-Ok -Condition ($LASTEXITCODE -eq 0) -Message "Internal configuration validation (validate_config.py) FAILED. Check the output above for details."
    Write-Host "✅ Internal Python configuration integrity checks passed." -ForegroundColor Green
}

Write-Host "`n" + ("=" * 80)
Write-Host "✅ PRE-FLIGHT CHECK COMPLETE: All systems nominal." -ForegroundColor Green
Write-Host "   Total Time: $($totalTime.TotalSeconds.ToString('F2')) seconds" -ForegroundColor Green
Write-Host ("=" * 80)