$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $repoRoot

pm2 status
Write-Host ""
Write-Host "Recent logs:"
pm2 logs --lines 30 --nostream
