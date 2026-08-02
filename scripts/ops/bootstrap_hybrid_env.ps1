<#
.SYNOPSIS
  Bootstraps the Omega V5 hybrid Python + Rust local environment.
.DESCRIPTION
  This script:
    1) Creates/uses .venv in the repo root
    2) Installs Python dependencies from requirements.txt (or requirements.in)
    3) Installs maturin into the project venv
    4) Builds and installs the Rust Python extension via maturin develop
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

function Get-PythonVersion {
    param([string]$pythonPath)

    if (!(Test-Path -LiteralPath $pythonPath)) {
        return $null
    }

    $versionText = & $pythonPath -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    if ($LASTEXITCODE -ne 0) {
        return $null
    }

    try {
        return [version]$versionText.Trim()
    } catch {
        return $null
    }
}

function Resolve-SystemPython {
    $candidateVersions = @("3.13", "3.12", "3.11", "3.10")

    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($version in $candidateVersions) {
            try {
                $probe = & py -$version -c "import sys; print(sys.executable)" 2>$null
                if ($LASTEXITCODE -eq 0) {
                    return @{ Command = "py"; Version = $version }
                }
            } catch {
                continue
            }
        }
    }

    if (Get-Command python -ErrorAction SilentlyContinue) {
        return @{ Command = "python"; Version = $null }
    }

    throw "Neither 'py' nor 'python' is available on PATH. Install Python 3.10+ and retry."
}

$venvScriptsDir = Join-Path $venvPath "Scripts"
$venvBinDir = Join-Path $venvPath "bin"
$venvPythonCandidates = @(
    (Join-Path $venvScriptsDir "python.exe"),
    (Join-Path $venvScriptsDir "python"),
    (Join-Path $venvBinDir "python"),
    (Join-Path $venvBinDir "python3")
)

$venvPython = $null
foreach ($candidate in $venvPythonCandidates) {
    if (Test-Path -LiteralPath $candidate) {
        $venvPython = $candidate
        break
    }
}

if (-not $venvPython) {
    $venvPython = if ($IsWindows -or $env:OS -eq 'Windows_NT') { Join-Path $venvScriptsDir "python.exe" } else { Join-Path $venvBinDir "python" }
}

$targetInterpreter = Resolve-SystemPython
$existingVersion = Get-PythonVersion -pythonPath $venvPython
$compatibleMin = [version]"3.12"
$compatibleMax = [version]"3.13"
$needsVenvRecreate = $false

if ($existingVersion -and ($existingVersion -lt $compatibleMin -or $existingVersion -gt $compatibleMax)) {
    $needsVenvRecreate = $true
    Write-Host "[0/5] Recreating .venv with a compatible Python runtime (current: $existingVersion)" -ForegroundColor Yellow
}

Write-Host "=== Omega V5 Hybrid Bootstrap ===" -ForegroundColor Cyan
Write-Host "Repo root: $repoRoot"
Write-Host "[0/5] Preparing Python environment and dependencies before Rust build" -ForegroundColor Yellow

if (!(Test-Path -LiteralPath $venvPython) -or $needsVenvRecreate) {
    if (Test-Path -LiteralPath $venvPath) {
        Remove-Item -LiteralPath $venvPath -Recurse -Force
    }

    Write-Host "[1/5] Creating project virtual environment at $venvPath" -ForegroundColor Yellow
    if ($targetInterpreter.Command -eq "py") {
        & py -$($targetInterpreter.Version) -m venv $venvPath
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
    & $venvPython -m pip install -r $reqTxt --prefer-binary
} elseif (Test-Path -LiteralPath $reqIn) {
    Write-Host "[4/5] requirements.txt missing; installing from requirements.in" -ForegroundColor Yellow
    & $venvPython -m pip install -r $reqIn --prefer-binary
} else {
    throw "No requirements.txt or requirements.in found in repo root."
}
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Python dependency installation reported an issue; continuing so the hybrid build can proceed with the existing environment."
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
