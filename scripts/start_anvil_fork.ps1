param(
    [int]$Port = 8545,
    [string]$HostAddress = "127.0.0.1",
    [int]$ChainId = 137,
    [switch]$VerboseAnvil,
    [string[]]$AnvilArgs = @()
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

$pythonExecutable = "python"
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $pythonExecutable = $venvPython
    Write-Host "[i] Using Python from virtual environment: $pythonExecutable"
}

function Test-AnvilAlive {
    param([string]$Url, [int]$ExpectedChainId)
    $body = '{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}'
    try {
        $response = Invoke-RestMethod -Uri $Url -Method Post -Body $body -ContentType "application/json" -TimeoutSec 2
        return ([Convert]::ToInt32([string]$response.result, 16) -eq $ExpectedChainId)
    } catch {
        return $false
    }
}

$localUrl = "http://$HostAddress`:$Port"
if (Test-AnvilAlive -Url $localUrl -ExpectedChainId $ChainId) {
    Write-Host "Anvil Polygon fork already healthy on $localUrl; holding wrapper process."
    while ($true) {
        Start-Sleep -Seconds 3600
    }
}

$forkOutput = & $pythonExecutable -m omega_v5.fork_rpc --print-url 2>$null
$forkUrl = $forkOutput | Where-Object { $_ -match "^https?://" } | Select-Object -First 1
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($forkUrl)) {
    throw "Could not resolve a Polygon fork RPC URL."
}

Write-Host "Starting Anvil Polygon fork on $localUrl"
$quietArgs = @()
if (!$VerboseAnvil) {
    $quietArgs += "--quiet"
}

anvil --host $HostAddress --port $Port --chain-id $ChainId --fork-url $forkUrl @quietArgs @AnvilArgs
