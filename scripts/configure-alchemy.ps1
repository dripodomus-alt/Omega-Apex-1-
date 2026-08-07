param(
    [Parameter(Mandatory = $true)]
    [string]$AlchemyHttpUrl,

    [Parameter(Mandatory = $true)]
    [string]$AlchemyWssUrl,

    [Parameter(Mandatory = $false)]
    [string]$EnvPath = ".env.alchemy",

    [Parameter(Mandatory = $false)]
    [int]$MulticallBatchSize = 128
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $AlchemyHttpUrl.StartsWith("https://")) {
    throw "AlchemyHttpUrl must start with https://"
}

if (-not $AlchemyWssUrl.StartsWith("wss://")) {
    throw "AlchemyWssUrl must start with wss://"
}

if ($MulticallBatchSize -lt 1 -or $MulticallBatchSize -gt 500) {
    throw "MulticallBatchSize must be between 1 and 500"
}

$content = @"
# Apex-Omega Polygon 137 — Alchemy optimized runtime
# DO NOT COMMIT THIS FILE.

CHAIN_ID=137

ALCHEMY_POLYGON_HTTP_URL=$AlchemyHttpUrl
ALCHEMY_POLYGON_WSS_URL=$AlchemyWssUrl

POLYGON_RPC_URL=$AlchemyHttpUrl
POLYGON_WSS_URL=$AlchemyWssUrl
DISCOVERY_RPC_URL=$AlchemyHttpUrl
DISCOVERY_RPC_WSS=$AlchemyWssUrl

POLYGON_FALLBACK_HTTP_URL=https://polygon-bor-rpc.publicnode.com
POLYGON_FALLBACK_WSS_URL=wss://polygon-bor-rpc.publicnode.com

MULTICALL_BATCH_SIZE=$MulticallBatchSize

MIN_POOL_TVL_USD=50000
MARKET_STATE_TTL_BLOCKS=4
MIN_RAW_SPREAD_BPS=1
MARKET_MAX_CANDIDATES=500
MARKET_API_PORT=8797
"@

Set-Content `
    -Path $EnvPath `
    -Value $content `
    -Encoding UTF8

Write-Host "Created $EnvPath" -ForegroundColor Green
Write-Host "Do not commit this file; it contains your Alchemy credential." -ForegroundColor Yellow

Write-Host ""
Write-Host "Load into current PowerShell session:" -ForegroundColor Cyan
Write-Host @"
Get-Content "$EnvPath" | ForEach-Object {
    if (`$_ -match '^\s*([^#][^=]*)=(.*)$') {
        [Environment]::SetEnvironmentVariable(
            `$matches[1].Trim(),
            `$matches[2].Trim(),
            'Process'
        )
    }
}
"@
