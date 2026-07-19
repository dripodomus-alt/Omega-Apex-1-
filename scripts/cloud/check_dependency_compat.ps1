$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $root

Write-Host "Checking pinned deployment toolchain..."

$dockerfile = Get-Content Dockerfile -Raw
if ($dockerfile -notmatch "node:20-bookworm") {
    throw "Dockerfile must stay on the Node 20 line unless vendor dependencies are upgraded and tested."
}
if ($dockerfile -notmatch "pnpm@10\.34\.5") {
    throw "pnpm must be pinned to a Node-20-compatible version."
}

Push-Location vendor\web3-rpc-provider
try {
    npm pkg get engines
    npm outdated --long
}
finally {
    Pop-Location
}

python -m pytest tests/test_balancer_weighted_math.py -q
Write-Host "Compatibility gate completed."
