param(
    [Parameter(Mandatory = $true)]
    [string]$AlchemyHttpUrl,

    [Parameter(Mandatory = $true)]
    [string]$AlchemyWssUrl,

    [Parameter(Mandatory = $true)]
    [string]$GetBlockGrpcUrl,

    [Parameter(Mandatory = $false)]
    [string]$EnvPath = ".env.network",

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

if (-not $GetBlockGrpcUrl.StartsWith("https://")) {
    throw "GetBlockGrpcUrl must be an HTTPS gRPC endpoint."
}

if ($MulticallBatchSize -lt 1 -or $MulticallBatchSize -gt 500) {
    throw "MulticallBatchSize must be between 1 and 500."
}

$content = @"
# Apex-Omega Polygon 137 — multi-provider network runtime
# DO NOT COMMIT. Endpoint URLs contain provider credentials.

CHAIN_ID=137

# Alchemy primary JSON-RPC / Enhanced API
ALCHEMY_POLYGON_HTTP_URL=$AlchemyHttpUrl
ALCHEMY_POLYGON_WSS_URL=$AlchemyWssUrl

POLYGON_RPC_URL=$AlchemyHttpUrl
POLYGON_WSS_URL=$AlchemyWssUrl
DISCOVERY_RPC_URL=$AlchemyHttpUrl
DISCOVERY_RPC_WSS=$AlchemyWssUrl

# GetBlock Polygon gRPC high-throughput lane
GETBLOCK_POLYGON_GRPC_URL=$GetBlockGrpcUrl
GETBLOCK_POLYGON_GRPC_REGION=ap-southeast-1

# Independent PublicNode fallback
POLYGON_FALLBACK_HTTP_URL=https://polygon-bor-rpc.publicnode.com
POLYGON_FALLBACK_WSS_URL=wss://polygon-bor-rpc.publicnode.com

# Dense read batching
MULTICALL_BATCH_SIZE=$MulticallBatchSize

# Market gates
MIN_POOL_TVL_USD=50000
MARKET_STATE_TTL_BLOCKS=4
MIN_RAW_SPREAD_BPS=1
MARKET_MAX_CANDIDATES=500
MARKET_API_PORT=8797
"@

Set-Content -Path $EnvPath -Value $content -Encoding UTF8

Write-Host "Created $EnvPath" -ForegroundColor Green
Write-Host "Network policy:" -ForegroundColor Cyan
Write-Host "  Standard reads       -> Alchemy HTTP"
Write-Host "  Multicall3           -> Alchemy HTTP"
Write-Host "  Subscriptions        -> Alchemy WSS"
Write-Host "  High-throughput gRPC -> GetBlock gRPC (ap-southeast-1)"
Write-Host "  Fallback reads       -> PublicNode HTTP"
Write-Host "  Fallback subs        -> PublicNode WSS"
Write-Host ""
Write-Host "Do not commit $EnvPath." -ForegroundColor Yellow
