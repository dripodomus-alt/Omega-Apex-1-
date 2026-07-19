param(
    [int]$Port = 6379,
    [string]$Bind = "127.0.0.1"
)

$ErrorActionPreference = "Stop"

if ($env:REDIS_PORT) {
    $Port = [int]$env:REDIS_PORT
}
if ($env:REDIS_BIND) {
    $Bind = $env:REDIS_BIND
}

$redis = Get-Command redis-server -ErrorAction SilentlyContinue
if (!$redis) {
    throw "redis-server is not available on PATH. Install Redis or point PM2 at an existing Redis instance."
}

Write-Host "Starting Redis on $Bind`:$Port"
& $redis.Source --bind $Bind --port $Port --save "" --appendonly no
