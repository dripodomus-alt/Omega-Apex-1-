[CmdletBinding()]
param([int]$Cycles = 2, [switch]$SkipAnvil, [switch]$ReadinessOnly)
$ErrorActionPreference = "Continue"
$repoRoot = $PSScriptRoot
if (!$repoRoot) { $repoRoot = Get-Location }
$envHelperPath = Join-Path $repoRoot "ops\env_contract.ps1"
. $envHelperPath
$envPath = Resolve-EnvContractPath -RepoRoot $repoRoot
$env:OMEGA_ENV_PATH = $envPath

function Write-Phase { param($Msg) Write-Host "`n>>> PHASE: $Msg" -ForegroundColor Cyan }
function Write-Sub { param($Msg) Write-Host " -> $Msg" }

Write-Phase "1. VALIDATION"
$envData = @{}
if (Test-Path $envPath) {
    Get-Content $envPath | ForEach-Object {
        if ($_ -match '^([^#][^=]+)=(.*)$') { $envData[$Matches[1].Trim()] = $Matches[2].Trim().Trim("'").Trim('"') }
    }
}

if ($envData.ContainsKey("C1_TARGET")) { 
    Write-Sub "Pinned Target Found: $($envData['C1_TARGET'])" 
} else { 
    Write-Sub "No Target Found. Using Dry-Run mode." 
}

Write-Phase "2. RUST ENGINE"
$rustBin = "rust_engine/target/release/omega_rust_engine.exe"
if (Test-Path $rustBin) { Write-Sub "Rust Engine OK" } else { Write-Sub "Rust Engine MISSING - Run 'cargo build --release' in rust_engine/" }

Write-Phase "3. PIPELINE TEST"
& python -m omega_v5.main --dry-run --cycles 1
if ($LASTEXITCODE -eq 0) { Write-Sub "Pipeline OK" } else { Write-Sub "Pipeline FAILED" }

Write-Phase "4. READINESS SUMMARY"
Write-Host "Readiness check complete. See out/readiness_report.json for details."
