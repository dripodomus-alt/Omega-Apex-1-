param(
    # This script is now fully autonomous. It decides the mode based on proofs.
    # The -Mode and -LiveAck parameters have been removed in favor of a proof-based autonomous decision.
)

$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$api = "http://127.0.0.1:8080"
Set-Location $repoRoot

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$proofDir = Join-Path $repoRoot "out\finalizer\$stamp"
New-Item -ItemType Directory -Force -Path $proofDir | Out-Null

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
function Assert-File-Freshness {
    param([string]$FilePath, [int]$MaxAgeSeconds)
    $file = Get-Item $FilePath
    $age = (Get-Date) - $file.LastWriteTime
    Assert-Ok -Condition ($age.TotalSeconds -lt $MaxAgeSeconds) -Message "Proof artifact '$FilePath' is stale (age $($age.TotalSeconds)s > ${MaxAgeSeconds}s). The proof command may have failed to update it."
}
function Invoke-JsonPost {
    param([string]$Uri, [hashtable]$Body)
    try {
        $json = $Body | ConvertTo-Json -Depth 12
        Invoke-RestMethod -Method Post -Uri $Uri -ContentType "application/json" -Body $json -ErrorAction Stop
    } catch {
        throw "Failed to send POST request to API at '$Uri'. Is the API service running and accessible? Error: $($_.Exception.Message)"
    }
}

$totalTime = Measure-Command {
try {

# --- 1. Pre-flight Checks ---
Write-Phase -Title "Step 1: Pre-flight System & Cloud Checks" -Subtitle "Verifying toolchain, wallet, and cloud prerequisites..."
Assert-Command -Name "python" -InstallHint "Install Python and ensure it is on PATH."
Assert-Command -Name "pm2" -InstallHint "Install with: npm install -g pm2"
Assert-Command -Name "node" -InstallHint "Install Node.js and ensure it is on PATH."
Assert-Command -Name "anvil" -InstallHint "Install Foundry, then restart this shell."
Assert-Command -Name "redis-server" -InstallHint "Install Redis or point PM2 at an existing Redis instance."
Assert-Command -Name "gcloud" -InstallHint "Install Google Cloud SDK and authenticate with `gcloud auth login`."

Write-Host "Verifying wallet configuration..."
Assert-Ok -Condition ($env:EXECUTOR_WALLET -ne $null -and $env:EXECUTOR_WALLET -ne "") -Message "EXECUTOR_WALLET environment variable is not set. This is required."
Assert-Ok -Condition ($env:EXECUTOR_WALLET.Length -eq 42 -and $env:EXECUTOR_WALLET.StartsWith("0x")) -Message "EXECUTOR_WALLET is not a valid Ethereum address."
# The private key is essential for any potential live run.
Assert-Ok -Condition ($null -ne $env:EXECUTOR_PRIVATE_KEY -and $env:EXECUTOR_PRIVATE_KEY -ne "") -Message "EXECUTOR_PRIVATE_KEY environment variable is not set. This is required for any potential live run."
Write-Host "[SECURITY NOTE] For production, it is recommended that the application fetches the private key from a secret manager at runtime, rather than relying on a persistent environment variable." -ForegroundColor Yellow

Write-Host "Verifying core configuration integrity..."
python scripts/ops/validate_config.py
Assert-Ok -Condition ($LASTEXITCODE -eq 0) -Message "Core configuration validation (validate_config.py) FAILED."

Write-Host "Verifying GCP prerequisites for live activation..."
# Try to get project ID from env var, then from gcloud config
$effectiveProject = $env:GCP_PROJECT_ID
if ([string]::IsNullOrEmpty($effectiveProject)) {
    try {
        $effectiveProject = gcloud config get-value project 2>$null
    }
    catch {
        # gcloud might not be configured; we'll catch this in the Assert-Ok below.
    }
}
# Assert-Ok that we have a project ID, and provide a helpful error if not.
Assert-Ok -Condition (-not [string]::IsNullOrEmpty($effectiveProject)) -Message "GCP_PROJECT_ID environment variable is not set, and no active project is configured in gcloud. This is required for a live run to fetch secrets. Set it via `$env:GCP_PROJECT_ID='your-project'` or `gcloud config set project your-project`."
Write-Host "GCP prerequisites passed." -ForegroundColor Green

Write-Host "Wallet configuration checks passed." -ForegroundColor Green

# --- 2. System Boot ---
    Write-Phase -Title "Step 2: Booting All PM2-Managed Services" -Subtitle "Starting all daemons via PM2 for a clean boot..."
    $pm2LogPath = Join-Path $proofDir "pm2_boot.txt"
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\pm2\boot_all.ps1 -Reset | Tee-Object -FilePath $pm2LogPath
    if ($LASTEXITCODE -ne 0) {
        Write-Host "PM2 boot FAILED. See full log at: $pm2LogPath" -ForegroundColor Red
        $logTail = Get-Content $pm2LogPath -Tail 20
        Write-Host "Last 20 lines of boot log:" -ForegroundColor Yellow
        $logTail | ForEach-Object { Write-Host $_ -ForegroundColor Gray }
        throw "PM2 boot failed."
    }
    $apiHealthcheckTimeoutSec = 30
    $healthCheckStart = Get-Date
    $apiHealthy = $false

    Write-Host "Waiting for API to become healthy at $api/health (Timeout: ${apiHealthcheckTimeoutSec}s)..."
    while (((Get-Date) - $healthCheckStart).TotalSeconds -lt $apiHealthcheckTimeoutSec) {
        try {
            $response = Invoke-RestMethod -Uri "$api/health" -Method Get -TimeoutSec 2
            if ($response.ok) {
                $apiHealthy = $true
                break
            }
        } catch {
            Write-Host "." -NoNewline
            Start-Sleep -Seconds 2
        }
    }
    Assert-Ok -Condition ($apiHealthy) -Message "API health check failed after boot. It did not become healthy within $apiHealthcheckTimeoutSec seconds."
    Write-Host "All services are online." -ForegroundColor Green

    # --- 3. Verification Proofs ---
    Write-Phase -Title "Step 3: Running Verification Proofs" -Subtitle "Executing runtime, pipeline, and integrity proofs to verify system health..."
    Write-Host "Running Runtime Alignment Proof..."
    python -m omega_v5.runtime_alignment --probe | Tee-Object -FilePath (Join-Path $proofDir "runtime_alignment.txt")
    Assert-Ok -Condition ($LASTEXITCODE -eq 0) -Message "Runtime alignment proof FAILED."
    Assert-File-Freshness "out\runtime_alignment_latest.json" 15

    Write-Host "Running Pipeline Validation Proof..."
    python -m omega_v5.pipeline_validation | Tee-Object -FilePath (Join-Path $proofDir "pipeline_validation.txt")
    Assert-Ok -Condition ($LASTEXITCODE -eq 0) -Message "Pipeline validation proof FAILED."
    Assert-File-Freshness "out\pipeline_validation_latest.json" 15

    Write-Host "Running Pipeline Integrity Proof..."
    python -m omega_v5.pipeline_integrity_proof | Tee-Object -FilePath (Join-Path $proofDir "pipeline_integrity_proof.txt")
    Assert-Ok -Condition ($LASTEXITCODE -eq 0) -Message "Pipeline integrity proof FAILED."
    Assert-File-Freshness "out\pipeline_integrity_proof_latest.json" 15
    Write-Host "All verification proofs PASSED." -ForegroundColor Green

    # --- 4. Finalizer Verdict ---
    Write-Phase -Title "Step 4: Generating Finalizer Verdict" -Subtitle "Aggregating all proofs to make an autonomous Go/No-Go decision..."
    python -m omega_v5.mainnet_finalizer --probe | Tee-Object -FilePath (Join-Path $proofDir "mainnet_finalizer.txt")
    Assert-Ok -Condition ($LASTEXITCODE -eq 0) -Message "Mainnet finalizer script FAILED."
    Assert-File-Freshness "out\mainnet_finalizer_latest.json" 15

    $finalizerReport = Get-Content "out\mainnet_finalizer_latest.json" -Raw | ConvertFrom-Json
    $verdict = $finalizerReport.verdict
    Write-Host "Finalizer Verdict: $verdict" -ForegroundColor Cyan

    # --- 5. Go/No-Go Decision and Autonomous Activation ---
    Write-Phase -Title "Step 5: Go/No-Go Decision & Autonomous Activation"
    if ($verdict -eq "CANARY_READY") {
        Write-Host "Finalizer verdict is CANARY_READY. The system is ready for live trading." -ForegroundColor Green

        Write-Host "Proceeding with AUTONOMOUS LIVE ACTIVATION." -ForegroundColor Yellow
        # Set Canary Mode for initial safety
        Write-Host "Activating Canary Mode (execution capped at 1 per cycle)..."
        Invoke-JsonPost "$api/api/runtime/settings" @{ canary_mode = $true }
        Write-Host "Canary mode ACTIVATED." -ForegroundColor Yellow

        # Arm the system
        Write-Host "Arming system for LIVE trading..."
        Invoke-JsonPost "$api/api/runtime/mode" @{ mode = "live"; actor = "cloud_run_finalizer_autonomous" }
        Write-Host "System ARMED for LIVE trading." -ForegroundColor Green
    } else {
        Write-Host "Finalizer verdict is '$verdict' (not 'CANARY_READY')." -ForegroundColor Yellow
        Write-Host "The system is not ready for live trading. Falling back to DRY_RUN mode."
        # Ensure system is in dry_run mode
        Invoke-JsonPost "$api/api/runtime/mode" @{ mode = "dry_run"; actor = "cloud_run_finalizer_autonomous" }
        Write-Host "System is in DRY_RUN mode. No live transactions will be broadcast." -ForegroundColor Green
    }

    # --- 6. Hand-off to Daemons ---
    Write-Phase -Title "Step 6: Hand-off to Autonomous Daemons"
    Write-Host "=========================================================================="
    Write-Host "✅ SYSTEM IS NOW RUNNING AUTONOMOUSLY IN THE BACKGROUND."
    Write-Host "   The 'omega-engine' and 'omega-liquidation-watcher' daemons are active."
    Write-Host "   Monitor the system via the API/UI: http://127.0.0.1:8080"
    Write-Host "   To stop all services, run: pm2 delete all"
    Write-Host "   To view logs, run: pm2 logs"
    Write-Host "=========================================================================="
    # Persist the PM2 process list to ensure automatic restart on server reboot.
    Write-Host "Saving PM2 process list for startup..."
    pm2 save

    pm2 status

} # End of main try block
catch {
    $errorLine = $_.InvocationInfo.ScriptLineNumber
    $errorMessage = $_.Exception.Message

    Write-Host "`n" + ("!" * 80) -ForegroundColor Red
    Write-Host "  FATAL ERROR DURING FINALIZER EXECUTION. ATTEMPTING CLEAN SHUTDOWN." -ForegroundColor Red
    Write-Host "  Failure at: line $errorLine" -ForegroundColor Red
    Write-Host "  Error: $errorMessage" -ForegroundColor Red
    Write-Host ("!" * 80) -ForegroundColor Red
    
    # Attempt to gracefully stop all services to prevent them from running in a bad state.
    if (Get-Command pm2 -ErrorAction SilentlyContinue) {
        Write-Host "`nAttempting to stop all PM2-managed services..."
        pm2 delete all
        pm2 save --force | Out-Null
        Write-Host "All PM2 services stopped." -ForegroundColor Yellow
    }
    
    # Re-throw the original exception to ensure the script exits with a non-zero code.
    throw
}
} # End of Measure-Command

Write-Host "`n" + ("=" * 80)
Write-Host "  FINALIZER SUMMARY" -ForegroundColor Green
Write-Host "  Final Status: Autonomous loop initiated successfully." -ForegroundColor Green
Write-Host "  Total Time  : $($totalTime.TotalSeconds.ToString('F2')) seconds" -ForegroundColor Green
Write-Host ("=" * 80)
