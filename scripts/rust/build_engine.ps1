param(
    [switch]$DebugBuild
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Manifest = Join-Path $Root "rust_engine\Cargo.toml"

if (!(Get-Command cargo -ErrorAction SilentlyContinue)) {
    throw "cargo is not available on PATH. Install Rust toolchain before booting Omega."
}

$argsList = @("build", "--manifest-path", $Manifest)
if (!$DebugBuild) {
    $argsList += "--release"
}

Set-Location $Root
cargo @argsList
if ($LASTEXITCODE -ne 0) {
    throw "Rust engine build failed with exit code $LASTEXITCODE"
}

$profile = if ($DebugBuild) { "debug" } else { "release" }
$exe = if ($IsWindows -or $env:OS -like "*Windows*") { "omega_rust_engine.exe" } else { "omega_rust_engine" }
$binary = Join-Path $Root "rust_engine\target\$profile\$exe"
if (!(Test-Path -LiteralPath $binary)) {
    throw "Rust engine binary missing after build: $binary"
}

Write-Host "Omega Rust engine built: $binary"
