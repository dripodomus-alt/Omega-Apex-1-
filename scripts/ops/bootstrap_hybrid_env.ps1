<#
.SYNOPSIS
  Bootstraps the Omega V5 hybrid Python + Rust local environment.
.DESCRIPTION
  This script:
    1) Creates/uses .venv in the repo root
    2) Installs Python dependencies from requirements.txt (or requirements.in)
    3) Installs maturin into the project venv
    4) Builds and installs the Rust Python extension via maturin develop

  Optional:
    - Build the Rust engine binary using scripts/rust/build_engine.ps1
.EXAMPLE
  .\scripts\ops\bootstrap_hybrid_env.ps1
  .\scripts\ops\bootstrap_hybrid_env.ps1 -DebugRustBuild
  .\scripts\ops\bootstrap_hybrid_env.ps1 -SkipRustPythonExtension
#>
[CmdletBinding()]
param(
    [switch]$SkipRustPythonExtension,
    [switch]$BuildRustEngineBinary,
    [switch]$DebugRustBuild
)

$ErrorActionPreference = "Stop"
$repoRoot = (Get-Item -Path $PSScriptRoot).Parent.Parent.FullName
Set-Location $repoRoot

$venvPath = Join-Path $repoRoot ".venv"

if ($IsWindows) {
    $venvPython = Join-Path $venvPath "Scripts\python.exe"
} else {
    $venvPython = Join-Path $venvPath "bin/python"
}

function Resolve-SystemPython {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return "py"
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return "python"
    }
    throw "Neither 'py' nor 'python' is available on PATH. Install Python 3.10+ and retry."
}

Write-Host "=== Omega V5 Hybrid Bootstrap ===" -ForegroundColor Cyan
Write-Host "Repo root: $repoRoot"

if (!(Test-Path -LiteralPath $venvPython)) {
    $sysPython = Resolve-SystemPython
    Write-Host "[1/5] Creating project virtual environment at $venvPath" -ForegroundColor Yellow
    if ($sysPython -eq "py") {
        & py -3 -m venv $venvPath
    } else {
        & python -m venv $venvPath
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create virtual environment."
    }
}

if (!(Test-Path -LiteralPath $venvPython)) {
    throw "Virtual environment python not found at $venvPython"
}

Write-Host "[2/5] Using venv interpreter: $venvPython" -ForegroundColor Yellow

Write-Host "[3/5] Upgrading pip/setuptools/wheel" -ForegroundColor Yellow
& $venvPython -m pip install --upgrade pip setuptools wheel
if ($LASTEXITCODE -ne 0) {
    throw "pip bootstrap failed."
}

$reqTxt = Join-Path $repoRoot "requirements.txt"
$reqIn = Join-Path $repoRoot "requirements.in"
if (Test-Path -LiteralPath $reqTxt) {
    Write-Host "[4/5] Installing Python dependencies from requirements.txt" -ForegroundColor Yellow
    & $venvPython -m pip install -r $reqTxt
} elseif (Test-Path -LiteralPath $reqIn) {
    Write-Host "[4/5] requirements.txt missing; installing from requirements.in" -ForegroundColor Yellow
    & $venvPython -m pip install -r $reqIn
} else {
    throw "No requirements.txt or requirements.in found in repo root."
}
if ($LASTEXITCODE -ne 0) {
    throw "Dependency installation failed."
}

if (-not $SkipRustPythonExtension) {
    if (!(Get-Command cargo -ErrorAction SilentlyContinue)) {
        throw "cargo is not available on PATH. Install Rust toolchain before building scanner_core extension."
    }

    Write-Host "[5/5] Installing maturin and building scanner_core extension" -ForegroundColor Yellow
    & $venvPython -m pip install --upgrade maturin
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install maturin in project virtual environment."
    }

    & $venvPython -m maturin develop --release --manifest-path (Join-Path $repoRoot "Cargo.toml")
    if ($LASTEXITCODE -ne 0) {
        throw "maturin develop failed."
    }
}

if ($BuildRustEngineBinary) {
    $buildScript = Join-Path $repoRoot "scripts\rust\build_engine.ps1"
    if (!(Test-Path -LiteralPath $buildScript)) {
        throw "Rust build script not found: $buildScript"
    }
    Write-Host "[optional] Building Rust engine binary" -ForegroundColor Yellow
    if ($DebugRustBuild) {
        & $buildScript -DebugBuild
    } else {
        & $buildScript
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Rust engine binary build failed."
    }
}

Write-Host "`nBootstrap complete." -ForegroundColor Green
Write-Host "Next: run .\scripts\ops\start_direct.ps1" -ForegroundColor Green
