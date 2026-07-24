param(
    [ValidateSet("dry_run", "live")]
    [string]$Mode = "dry_run",

    [ValidateSet(5, 10, 15)]
    [int]$ExecuteTop = 5,

    [int]$PrintTopRoutes = 50,
    [int]$Ticks = 1,
    [decimal]$PrincipalUsd = 50000,
    [int]$IntervalSeconds = 60,
    [int]$ExactCallProofRoutes = 5,

    [switch]$InstallDeps,
    [switch]$ResetPm2,
    [switch]$RunOnce,
    [switch]$WithScanner,
    [switch]$SkipExactCallProof,
    [switch]$SkipSessionProof,

    [switch]$AllowBroadcast,
    [string]$LiveAck = ""
)

$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

Write-Host "================================== DEPRECATION WARNING ==================================" -ForegroundColor Yellow
Write-Host "This script ('full_system_ops.ps1') is part of the legacy omega_v5 (Python/PM2) architecture." -ForegroundColor Yellow
Write-Host "It is deprecated for local development in favor of 'scripts/ops/start_local_dev.ps1' for the new monorepo." -ForegroundColor Yellow
Write-Host "For production, use the Docker/Kubernetes infrastructure defined in the OMEGA-FINALLY-RICH monorepo." -ForegroundColor Yellow
Write-Host "========================================================================================="
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $repoRoot

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$proofDir = Join-Path $repoRoot "out\ops\$stamp"
New-Item -ItemType Directory -Force -Path $proofDir | Out-Null
$env:OMEGA_TRUTH_MAX_CANDIDATES = "$ExactCallProofRoutes"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message"
}

function Require-Command {
    param([string]$Name, [string]$InstallHint)
    if (!(Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name is not available on PATH. $InstallHint"
    }
}

function Invoke-JsonPost {
    param(
        [string]$Uri,
        [hashtable]$Body
    )
    $json = $Body | ConvertTo-Json -Depth 12
    Invoke-RestMethod -Method Post -Uri $Uri -ContentType "application/json" -Body $json
}

function Assert-File-Freshness {
    param([string]$FilePath, [int]$MaxAgeSeconds)
    $file = Get-Item $FilePath
    $age = (Get-Date) - $file.LastWriteTime
    Assert-Ok ($age.TotalSeconds -lt $MaxAgeSeconds) "Proof artifact '$FilePath' is stale (age $($age.TotalSeconds)s > ${MaxAgeSeconds}s). The proof command may have failed to update it."
}

function Assert-Ok {
    param(
        [bool]$Condition,
        [string]$Message
    )
    if (!$Condition) {
        throw $Message
    }
}

Write-Step "Preflight command checks"
Require-Command "python" "Install Python and ensure it is on PATH."
Require-Command "pm2" "Install with: npm install -g pm2"
Require-Command "node" "Install Node.js and ensure it is on PATH."
Require-Command "anvil" "Install Foundry, then restart this shell."
Require-Command "redis-server" "Install Redis or point PM2 at an existing Redis instance."

if ($Mode -eq "live") {
    Assert-Ok $AllowBroadcast.IsPresent "Live mode requested without -AllowBroadcast. Refusing to arm live broadcast."
    Assert-Ok ($LiveAck -eq "I_UNDERSTAND_POLYGON_MAINNET_RISK") "Live mode requires -LiveAck I_UNDERSTAND_POLYGON_MAINNET_RISK"
}

Write-Step "Compile Python entrypoints and PM2 config"
python -m py_compile `
    omega_v5\config.py `
    omega_v5\api.py `
    omega_v5\main.py `
    omega_v5\execution.py `
    omega_v5\runtime_alignment.py `
    omega_v5\pipeline_validation.py
node -c ecosystem.config.cjs

Write-Step "Build Rust hybrid engine and run Rust preflight"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\rust\build_engine.ps1 |
    Tee-Object -FilePath (Join-Path $proofDir "rust_build.txt")
python -m omega_v5.rust_preflight |
    Tee-Object -FilePath (Join-Path $proofDir "rust_preflight.txt")

Write-Step "Boot PM2-managed services"
$bootArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "scripts\pm2\boot_all.ps1")
if ($InstallDeps) { $bootArgs += "-InstallDeps" }
if ($ResetPm2) { $bootArgs += "-Reset" }
powershell @bootArgs | Tee-Object -FilePath (Join-Path $proofDir "pm2_boot.txt")

Write-Step "API health and runtime configuration"
$api = "http://127.0.0.1:8080"
Start-Sleep -Seconds 2
$health = Invoke-RestMethod "$api/health"
$health | ConvertTo-Json -Depth 12 | Tee-Object -FilePath (Join-Path $proofDir "api_health.json")
Assert-Ok ([bool]$health.ok) "API health check failed."

$settings = Invoke-JsonPost "$api/api/runtime/settings" @{
    execute_top = $ExecuteTop
    print_top_routes = $PrintTopRoutes
    ticks = $Ticks
    principal_usd = "$PrincipalUsd"
    interval_seconds = $IntervalSeconds
    no_scan = !$WithScanner.IsPresent
    canary_mode = $false
}
$settings | ConvertTo-Json -Depth 12 | Tee-Object -FilePath (Join-Path $proofDir "runtime_settings.json")

$runtime = Invoke-JsonPost "$api/api/runtime/mode" @{
    mode = $Mode
    actor = "full_system_ops"
}
$runtime | ConvertTo-Json -Depth 12 | Tee-Object -FilePath (Join-Path $proofDir "runtime_mode.json")
Assert-Ok ($runtime.mode -eq $Mode) "Runtime mode did not apply."

Write-Step "PM2 status and local dependency health"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\pm2\health_check.ps1 |
    Tee-Object -FilePath (Join-Path $proofDir "pm2_health.txt")

Write-Step "Runtime alignment proof"
python -m omega_v5.runtime_alignment --probe |
    Tee-Object -FilePath (Join-Path $proofDir "runtime_alignment.txt")
Assert-Ok ($LASTEXITCODE -eq 0) "Runtime alignment proof failed."
Assert-File-Freshness "out\runtime_alignment_latest.json" 15

if (!$SkipSessionProof) {
    Write-Step "SESSION_SIGNER / WaaS dry-run isolation proof"
    python -m omega_v5.session_proof --samples 3 |
        Tee-Object -FilePath (Join-Path $proofDir "session_proof.txt")
    Assert-Ok ($LASTEXITCODE -eq 0) "Session signer proof failed."
    Assert-File-Freshness "out\session_signer_proof_latest.json" 15
}
Assert-File-Freshness "out\session_signer_proof_latest.json" 15

Write-Step "Pipeline validation proof"
$pipelineArgs = @("-m", "omega_v5.pipeline_validation", "--max-opps", "$ExactCallProofRoutes")
if ($SkipExactCallProof) {
    $pipelineArgs += "--no-eth-call"
}
python @pipelineArgs |
    Tee-Object -FilePath (Join-Path $proofDir "pipeline_validation.txt")
Assert-Ok ($LASTEXITCODE -eq 0) "Pipeline validation failed."
Assert-File-Freshness "out\pipeline_validation_latest.json" 15

if ($Mode -eq "live") {
    $alignmentJson = Get-Content "out\runtime_alignment_latest.json" -Raw | ConvertFrom-Json
    $broadcastOk = [bool]$alignmentJson.checks.probed_chain_ids.detail.broadcast.ok
    Assert-Ok $broadcastOk "Live broadcast proof failed: configured broadcast RPC is not healthy. No live cycle was started."
}

if ($RunOnce) {
    Write-Step "One-shot autonomous cycle"
    $cycleArgs = @(
        "-m", "omega_v5.main",
        "--ticks", "$Ticks",
        "--principal", "$PrincipalUsd",
        "--print-top-routes", "$PrintTopRoutes",
        "--execute-top", "$ExecuteTop"
    )
    if (!$WithScanner) {
        $cycleArgs += "--no-scan"
    }
    python @cycleArgs |
        Tee-Object -FilePath (Join-Path $proofDir "autonomous_cycle.txt")
    Assert-Ok ($LASTEXITCODE -eq 0) "Autonomous cycle failed."
}

Write-Step "Final runtime proof snapshot"
$status = Invoke-RestMethod "$api/api/runtime/status"
$status | ConvertTo-Json -Depth 20 | Tee-Object -FilePath (Join-Path $proofDir "runtime_status.json")

$pnl = Invoke-RestMethod "$api/api/pnl"
$pnl | ConvertTo-Json -Depth 20 | Tee-Object -FilePath (Join-Path $proofDir "pnl_snapshot.json")

$traces = Invoke-RestMethod "$api/api/traces?limit=20"
$traces | ConvertTo-Json -Depth 20 | Tee-Object -FilePath (Join-Path $proofDir "recent_traces.json")

pm2 status | Tee-Object -FilePath (Join-Path $proofDir "pm2_status_final.txt")

Write-Host ""
Write-Host "FULL_SYSTEM_OPS=PASS"
    Write-Host "mode=$Mode"
    Write-Host "execute_top=$ExecuteTop print_top_routes=$PrintTopRoutes principal_usd=$PrincipalUsd"
    Write-Host "exact_call_proof_routes=$ExactCallProofRoutes"
Write-Host "proof_dir=$proofDir"
Write-Host "api=$api"
Write-Host "pm2=INTACT"
if ($Mode -eq "dry_run") {
    Write-Host "broadcast_policy=NOT_ATTEMPTED_DRY_RUN"
} else {
    Write-Host "broadcast_policy=LIVE_ALLOWED_AND_GATED"
}
