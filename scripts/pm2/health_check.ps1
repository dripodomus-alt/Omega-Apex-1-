param(
    [string]$ApiUrl = "http://127.0.0.1:8080"
)

$ErrorActionPreference = "Stop"

Write-Host "PM2 status"
pm2 status

Write-Host ""
Write-Host "Redis ping"
if (Get-Command redis-cli -ErrorAction SilentlyContinue) {
    redis-cli -h 127.0.0.1 -p 6379 ping
} else {
    Write-Host "redis-cli unavailable"
}

Write-Host ""
Write-Host "Anvil chainId"
$body = '{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}'
try {
    Invoke-RestMethod -Uri "http://127.0.0.1:8545" -Method Post -Body $body -ContentType "application/json" |
        ConvertTo-Json -Depth 8
} catch {
    Write-Host "anvil_unavailable: $($_.Exception.Message)"
}

Write-Host ""
Write-Host "API health"
Invoke-RestMethod -Uri "$ApiUrl/health" -Method Get | ConvertTo-Json -Depth 8

Write-Host ""
Write-Host "Runtime status"
Invoke-RestMethod -Uri "$ApiUrl/api/runtime/status" -Method Get | ConvertTo-Json -Depth 12
