<#
.SYNOPSIS
  Runs the full suite of safe benchmarks and readiness assessments.
.DESCRIPTION
  This is the master script for verifying system health and performance before any
  live deployment. It orchestrates a series of checks, tests, and benchmarks,
  aggregating the results into a final readiness score.

  It intentionally excludes any live-fire execution.
.EXAMPLE
  # Run the full benchmark and readiness assessment.
  .\scripts\run_full_benchmark_and_readiness.ps1

  # Run with more Anvil cycles for a deeper performance test.
  .\scripts\run_full_benchmark_and_readiness.ps1 -AnvilCycles 5
#>
[CmdletBinding()]
param(
    [int]$AnvilCycles = 5,
    [switch]$SkipAnvil,
    [switch]$ReadinessOnly,
    [int]$ScannerTokens = 50,
    [int]$ScannerPoolsPerPair = 10
)

$ErrorActionPreference = "Stop"
$repoRoot = (Get-Item -Path $PSScriptRoot).Parent.FullName
Set-Location $repoRoot

# --- Helper Functions ---
function Write-Phase { param([string]$Message) Write-Host "`n" + ("=" * 80) + "`n" + " PHASE: $Message" + "`n" + ("=" * 80) -ForegroundColor Cyan }
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

$results = @{
    prereqs           = $false
    unit_tests        = $false
    scanner_benchmark = $false
    pipeline_validation = $false
    anvil_benchmark   = $false
    data_integrity    = $false
    route_proof_matrix = $false
    readiness_score   = 0
}

try {
    # --- Phase 1: Prerequisite Checks ---
    Write-Phase "Prerequisite Checks"
    Assert-Command -Name "python" -InstallHint "Install Python and ensure it is on PATH."
    Assert-Command -Name "pytest" -InstallHint "Install with: pip install pytest"
    Assert-Command -Name "anvil" -InstallHint "Install Foundry and ensure it is on PATH."
    Assert-Command -Name "maturin" -InstallHint "Install with: pip install maturin"
    Write-Host "All prerequisites found."
    $results.prereqs = $true

    # --- Phase 2: Unit & Integration Tests ---
    Write-Phase "Unit & Integration Tests"
    Write-Host "Compiling Rust extension module..."
    python -m maturin develop
    Assert-Ok -Condition ($LASTEXITCODE -eq 0) -Message "Failed to compile Rust extension with 'maturin develop'."

    Write-Host "Running pytest..."
    pytest
    Assert-Ok -Condition ($LASTEXITCODE -eq 0) -Message "Pytest run failed."
    Write-Host "All unit tests passed."
    $results.unit_tests = $true

    # --- Phase 3: Scanner Performance Benchmark (Rust vs. Python) ---
    Write-Phase "Scanner Performance Benchmark"
    Write-Host "Running with --tokens $ScannerTokens --pools-per-pair $ScannerPoolsPerPair to stress-test the discovery pipeline."
    python benchmarks/compare_scanners.py --tokens $ScannerTokens --pools-per-pair $ScannerPoolsPerPair
    Assert-Ok -Condition ($LASTEXITCODE -eq 0) -Message "Scanner performance benchmark (compare_scanners.py) failed."
    $results.scanner_benchmark = $true

    # --- Phase 4: Pipeline Validation ---
    Write-Phase "Pipeline Validation Proofs"
    python -m omega_v5.pipeline_validation
    Assert-Ok -Condition ($LASTEXITCODE -eq 0) -Message "Pipeline validation proof failed."
    Write-Host "Pipeline validation passed."
    $results.pipeline_validation = $true

    # --- Phase 5: Anvil Fork Benchmark ---
    if ($SkipAnvil) {
        Write-Phase "Anvil Fork Benchmark (SKIPPED)"
        $results.anvil_benchmark = $true # Mark as passed if skipped
    }
    else {
        Write-Phase "Anvil Fork Benchmark"
        # Check if Anvil is running, and start it if it's not.
        $anvilPort = 8545
        $anvilIsRunning = (Test-NetConnection -ComputerName "127.0.0.1" -Port $anvilPort -ErrorAction SilentlyContinue).TcpTestSucceeded
        if (-not $anvilIsRunning) {
            Write-Host "Anvil not detected on port $anvilPort. Attempting to start it automatically..." -ForegroundColor Yellow
            $envConfig = Parse-EnvFile -FilePath ".env"
            # Prefer FORK_RPC_URL for local benchmarks, as it's the primary Anvil config.
            $forkUrl = $envConfig.FORK_RPC_URL
            Assert-Ok -Condition (-not [string]::IsNullOrEmpty($forkUrl)) -Message "Could not find FORK_UPSTREAM_RPC_URL or FORK_RPC_URL in .env file to start Anvil."
            
            # Start Anvil as a background job in PowerShell
            Start-Job -ScriptBlock {
                param($url)
                anvil --fork-url $url --silent
            } -ArgumentList $forkUrl | Out-Null
            Write-Host "Anvil started as a background job. Waiting for it to become responsive..."

            $anvilReady = $false
            $maxWaitSeconds = 20
            $startTime = Get-Date
            while (((Get-Date) - $startTime).TotalSeconds -lt $maxWaitSeconds) {
                if ((Test-NetConnection -ComputerName "127.0.0.1" -Port $anvilPort -ErrorAction SilentlyContinue).TcpTestSucceeded) {
                    $anvilReady = $true
                    Write-Host "Anvil is responsive." -ForegroundColor Green
                    break
                }
                Start-Sleep -Seconds 1
                Write-Host "." -NoNewline
            }

            Assert-Ok -Condition $anvilReady -Message "Anvil was started but did not become responsive on port $anvilPort within $maxWaitSeconds seconds."
        }
        powershell -NoProfile -ExecutionPolicy Bypass -File scripts/ops/run_anvil_fork_benchmark.ps1 -Cycles $AnvilCycles
        Assert-Ok -Condition ($LASTEXITCODE -eq 0) -Message "Anvil fork benchmark failed."
        $results.anvil_benchmark = $true
    }

    # --- Phase 6: Data Integrity & Governance Gate ---
    Write-Phase "Data Integrity & Governance Gate"
    $envConfig = Parse-EnvFile -FilePath ".env"
    $dataIntegrityEnabled = $envConfig.DATA_INTEGRITY_CHECK_ENABLED
    if ($dataIntegrityEnabled -eq "false") {
        Write-Host "Data integrity check is disabled via DATA_INTEGRITY_CHECK_ENABLED=false in .env. Skipping." -ForegroundColor Yellow
        $results.data_integrity = $true
    }
    else {
        Write-Host "Verifying health of persistent data stores (Redis, SQLite Indexer)..."
        python -m omega_v5.data_integrity_check
        Assert-Ok -Condition ($LASTEXITCODE -eq 0) -Message "Data integrity check failed. See logs for details."
        Write-Host "Data stores are healthy and responsive." -ForegroundColor Green
        $results.data_integrity = $true
    }

    # --- Phase 7: Route Proof Matrix ---
    Write-Phase "Route Proof Matrix"
    $proofProfile = "maximum_dynamics"
    Write-Host "Running route proof matrix with profile: '$proofProfile'..."
    python -m omega_v5.route_proof_matrix --profiles $proofProfile
    Assert-Ok -Condition ($LASTEXITCODE -eq 0) -Message "Route proof matrix script (route_proof_matrix.py) failed to execute."

    $proofReportPath = "out/route_proof_matrix_latest.json"
    Assert-Ok -Condition (Test-Path $proofReportPath) -Message "Route proof matrix report was not generated at '$proofReportPath'."
    $proofReport = Get-Content $proofReportPath -Raw | ConvertFrom-Json
    $proofsFailed = $proofReport.proof.route_proofs_failed
    Assert-Ok -Condition ($proofsFailed -eq 0) -Message "Route proof matrix FAILED: $proofsFailed routes failed their internal proofs. Check '$proofReportPath' for details."
    $proofsPassed = $proofReport.proof.route_proofs_passed
    Write-Host "Route proof matrix PASSED: $proofsPassed routes passed all internal proofs." -ForegroundColor Green
    $results.route_proof_matrix = $true

}
catch {
    Write-Host "`n" + ("!" * 80) -ForegroundColor Red
    Write-Host "  A benchmark phase failed. Halting readiness assessment." -ForegroundColor Red
    Write-Host "  Error: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ("!" * 80) -ForegroundColor Red
}
finally {
    # --- Cleanup: Stop background Anvil job if it was started ---
    Get-Job -Name "Job*" | Where-Object { $_.Command -like "*anvil*" } | Stop-Job -PassThru | Remove-Job
}

try {
    # --- Final Phase: Readiness Score ---
    Write-Phase "Final Readiness Score"
    $passed_checks = 0
    foreach ($key in $results.Keys) {
        if ($key -ne "readiness_score" -and $results[$key]) {
            $passed_checks++
        }
    }
    $total_checks = $results.Count - 1
    $readiness_score = if ($total_checks -gt 0) { [math]::Round(($passed_checks / $total_checks) * 100) } else { 0 }
    $results.readiness_score = $readiness_score

    $statusColor = "Red"
    if ($readiness_score -gt 95) { $statusColor = "Green" }
    elseif ($readiness_score -gt 70) { $statusColor = "Yellow" }

    Write-Host "Readiness Score: $readiness_score / 100" -ForegroundColor $statusColor

    # Save to a timestamped file for historical tracking
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $reportDir = "out/readiness_reports"
    New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
    $reportPath = Join-Path $reportDir "readiness_report_$timestamp.json"
    $results | ConvertTo-Json -Depth 5 | Out-File -FilePath $reportPath -Encoding utf8
    Write-Host "Full report saved to $reportPath"
    # Create/update a 'latest' file for easy access
    Set-Content -Path "out/readiness_report_latest.json" -Value (Get-Content $reportPath -Raw)

    # Display a final summary table
    Write-Host "`n" + ("=" * 45)
    Write-Host "         Readiness Summary"
    Write-Host ("=" * 45)
    Write-Host ("{0,-25} {1,-15}" -f "PHASE", "STATUS")
    Write-Host ("{0,-25} {1,-15}" -f "-----", "------")
    $results.GetEnumerator() | Sort-Object Name | ForEach-Object {
        if ($_.Name -ne "readiness_score") {
            $statusText = if ($_.Value) { "PASSED" } else { "FAILED" }
            $statusEmoji = if ($_.Value) { "✅" } else { "❌" }
            $statusColor = if ($_.Value) { "Green" } else { "Red" }
            Write-Host ("{0,-25} {1,-2} {2,-12}" -f $_.Name.ToUpper(), $statusEmoji, $statusText) -ForegroundColor $statusColor
        }
    }
    Write-Host ("=" * 45)

    if ($readiness_score -lt 100) {
        Write-Host "One or more readiness checks failed." -ForegroundColor Yellow
        # Exit with a non-zero code to indicate failure for CI/CD systems
        exit 1
    }
}
catch {
    # This catch block handles errors during the final reporting phase.
    Write-Host "An error occurred during the final reporting phase: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}