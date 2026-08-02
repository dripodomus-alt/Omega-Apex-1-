<#
.SYNOPSIS
  One-command launcher for the hybrid Python/Rust workflow.
.DESCRIPTION
  Runs the hybrid bootstrap script first, then starts the direct entrypoint.
  Useful as a single repo-root command for local development.
#>
[CmdletBinding()]
param(
    [switch]$BuildRustEngineBinary,
    [switch]$DebugRustBuild,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$StartArgs = @()
)

$ErrorActionPreference = "Stop"
$repoRoot = (Get-Item -Path $PSScriptRoot).Parent.Parent.FullName
$bootstrapScript = Join-Path $repoRoot "scripts\ops\bootstrap_hybrid_env.ps1"
$startScript = Join-Path $repoRoot "scripts\ops\start_direct.ps1"

if (!(Test-Path -LiteralPath $bootstrapScript)) {
    throw "Bootstrap script not found: $bootstrapScript"
}

if (!(Test-Path -LiteralPath $startScript)) {
    throw "Start script not found: $startScript"
}

$bootstrapArgs = @()
if ($BuildRustEngineBinary) { $bootstrapArgs += "-BuildRustEngineBinary" }
if ($DebugRustBuild) { $bootstrapArgs += "-DebugRustBuild" }

Write-Host "=== Launching Omega V5 hybrid workflow ===" -ForegroundColor Cyan
& $bootstrapScript @bootstrapArgs
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "=== Starting direct entrypoint ===" -ForegroundColor Cyan
& $startScript @StartArgs
exit $LASTEXITCODE
