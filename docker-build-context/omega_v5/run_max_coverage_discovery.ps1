<#
.SYNOPSIS
    Runs the Omega V5 discovery pipeline with maximum coverage settings.
.DESCRIPTION
    This script executes a read-only validation run of the pipeline with unbounded
    discovery settings. It is designed to demonstrate the system's full capability
    to discover liquidity pools and arbitrage routes across the entire configured
    protocol and token universe.

    The output is a detailed report at `out/live_pool_scan_report.json` which
    lists all discovered pools and their metadata.
.NOTES
    This script does NOT perform any on-chain transactions. It is a read-only
    diagnostic tool.
#>

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $repoRoot

Write-Host "==> Starting Maximum Coverage Discovery Run" -ForegroundColor Cyan

$env:BACKGROUND_DISCOVERY_UNBOUNDED = "true"
$env:DISCOVERY_MAX_TOKEN_PAIRS = "0"
$env:DISCOVERY_MAX_PROMOTED_POOLS = "0"

Write-Host "  Discovery settings set to maximum coverage. Running pipeline validation..."
python -m omega_v5.pipeline_validation --no-eth-call

Write-Host ""
Write-Host "✅ Maximum coverage discovery run COMPLETE." -ForegroundColor Green
Write-Host "   A detailed report of all discovered pools has been saved to: out\live_pool_scan_report.json"