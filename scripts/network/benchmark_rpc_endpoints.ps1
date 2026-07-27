<#
.SYNOPSIS
  Benchmarks the latency and reliability of multiple RPC endpoints.
.DESCRIPTION
  This script performs a series of tests against a list of HTTP and WSS RPC
  endpoints to measure their performance. It calculates success rate, average
  latency, and other statistics, presenting a ranked report to help identify
  the best-performing endpoints for different roles (e.g., discovery, broadcast).

  It can automatically discover endpoints from your .env file or accept a
  custom list.
.EXAMPLE
  # Benchmark all RPC endpoints found in the .env file with 5 samples each.
  .\scripts\network\benchmark_rpc_endpoints.ps1 -IncludeEnv -Samples 5

  # Benchmark a custom list of HTTP endpoints.
  .\scripts\network\benchmark_rpc_endpoints.ps1 -Urls "https://polygon.drpc.org,https://polygon.publicnode.com"

  # Benchmark a mix of HTTP and WSS endpoints.
  .\scripts\network\benchmark_rpc_endpoints.ps1 -Urls "https://polygon.drpc.org,wss://polygon.drpc.org"
#>
[CmdletBinding(DefaultParameterSetName = 'Env')]
param(
    [Parameter(ParameterSetName = 'Env')]
    [switch]$IncludeEnv,

    [Parameter(ParameterSetName = 'Custom')]
    [string]$Urls,

    [int]$Samples = 5,
    [int]$TimeoutSec = 8,
    [string]$OutputFile = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = (Get-Item -Path $PSScriptRoot).Parent.Parent.FullName
Set-Location $repoRoot

# --- Helper Functions ---
function Write-Phase { param([string]$Message) Write-Host "`n" + ("=" * 80) + "`n" + " PHASE: $Message" + "`n" + ("=" * 80) -ForegroundColor Cyan }
function Write-Substep { param([string]$Message) Write-Host "`n -> $Message" }

# --- Main Logic ---

Write-Phase "RPC Endpoint Benchmark"

$allUrls = [System.Collections.Generic.List[string]]@()

if ($IncludeEnv) {
    Write-Substep "Discovering endpoints from .env file..."
    $envFile = Join-Path $repoRoot ".env"
    if (-not (Test-Path $envFile)) {
        $envFile = Join-Path $repoRoot ".env.example"
    }
    if (-not (Test-Path $envFile)) {
        throw ".env or .env.example file not found."
    }

    $envContent = Get-Content $envFile
    $urlPattern = 'https?://[\w\d\.:/\-?=%&_~]+|wss?://[\w\d\.:/\-?=%&_~]+'
    $envContent | ForEach-Object {
        if ($_ -match '^\s*#') { return } # Skip comments
        $lineUrls = ([regex]::Matches($_, $urlPattern)).Value
        foreach ($url in $lineUrls) {
            $allUrls.AddRange(($url -split ',' | ForEach-Object { $_.Trim() }))
        }
    }
    Write-Host "Found $($allUrls.Count) potential endpoint strings in $envFile."
}

if ($PSBoundParameters.ContainsKey('Urls')) {
    $allUrls.AddRange(($Urls -split ',' | ForEach-Object { $_.Trim() }))
}

$uniqueUrls = $allUrls | Where-Object { $_ -and ($_ -match "^(https|http|wss|ws)://") } | Select-Object -Unique

if ($uniqueUrls.Count -eq 0) {
    throw "No valid RPC URLs found to benchmark."
}

Write-Substep "Starting benchmark for $($uniqueUrls.Count) unique endpoints (Samples per endpoint: $Samples)..."

$testBlock = {
    param($url, $samples, $timeout)

    $latencies = [System.Collections.Generic.List[double]]@()
    $successes = 0
    $failures = 0
    $type = "UNKNOWN"
    $writable = $false
    $debuggable = $false
    $mevCapability = "None"

    if ($url.StartsWith("http")) {
        $type = "HTTP"
        $body = '{"jsonrpc":"2.0","id":1,"method":"eth_blockNumber","params":[]}'
        for ($i = 0; $i -lt $samples; $i++) {
            try {
                $duration = Measure-Command {
                    $response = Invoke-RestMethod -Uri $url -Method Post -Body $body -ContentType "application/json" -TimeoutSec $timeout
                }
                if ($response.result) {
                    $successes++
                    $latencies.Add($duration.TotalMilliseconds)
                } else {
                    $failures++
                }
            } catch {
                $failures++
            }
        }

        # Test for eth_sendRawTransaction support (writability)
        # This sends an invalid raw tx and expects a specific error, proving the method exists.
        try {
            $writeTestBody = '{"jsonrpc":"2.0","id":1,"method":"eth_sendRawTransaction","params":["0x0"]}'
            $writeResponse = Invoke-RestMethod -Uri $url -Method Post -Body $writeTestBody -ContentType "application/json" -TimeoutSec $timeout
            if ($writeResponse.error -and $writeResponse.error.message -match "invalid|transaction") {
                $writable = $true
            }
        }
        catch (Microsoft.PowerShell.Commands.HttpResponseException $e) {
            if ($e.Response.Content -match "invalid|transaction") {
                $writable = $true
            }
        }

        # Test for MEV capabilities
        try {
            # Flashbots: eth_sendBundle
            $flashbotsTestBody = '{"jsonrpc":"2.0","id":1,"method":"eth_sendBundle","params":[{}]}'
            Invoke-RestMethod -Uri $url -Method Post -Body $flashbotsTestBody -ContentType "application/json" -TimeoutSec $timeout -ErrorAction SilentlyContinue
            if ($LASTEXITCODE -eq 0 -or ($_.Exception.Response.Content -match "invalid params")) {
                $mevCapability = "Flashbots"
            }
        } catch {}

        if ($mevCapability -eq "None") {
            try {
                # Generic PrivateTx: eth_sendPrivateTransaction
                $privateTxTestBody = '{"jsonrpc":"2.0","id":1,"method":"eth_sendPrivateTransaction","params":[{"tx":"0x0"}]}'
                Invoke-RestMethod -Uri $url -Method Post -Body $privateTxTestBody -ContentType "application/json" -TimeoutSec $timeout -ErrorAction SilentlyContinue
                if ($LASTEXITCODE -eq 0 -or ($_.Exception.Response.Content -match "invalid params")) {
                    $mevCapability = "PrivateTx"
                }
            } catch {}
        }

        if ($url -match "titanbuilder") { $mevCapability = "Titan" }

        # Test for debug_traceTransaction support
        # We trace a known, historical transaction (genesis block on Polygon)
        # We don't care if the trace succeeds, only that the method is not rejected.
        try {
            $traceTestBody = '{"jsonrpc":"2.0","id":1,"method":"debug_traceTransaction","params":["0x0d9a2b808a50545a21b9a9388c16a2b3a357d32c25841f452a2517ad3b4b813b"]}'
            $traceResponse = Invoke-RestMethod -Uri $url -Method Post -Body $traceTestBody -ContentType "application/json" -TimeoutSec $timeout
            # If it doesn't error with "method not found", it supports it.
            if (-not ($traceResponse.error -and $traceResponse.error.message -match "not found|not supported")) {
                $debuggable = $true
            }
        }
        catch (Microsoft.PowerShell.Commands.HttpResponseException $e) {
            if (-not ($e.Response.Content -match "not found|not supported")) {
                $debuggable = $true
            }
        }
    }
    elseif ($url.StartsWith("ws")) {
        $type = "WSS"
        # Using .NET WebSocket client for robust WSS handling
        Add-Type -AssemblyName System.Net.WebSockets.Client
        for ($i = 0; $i -lt $samples; $i++) {
            $ws = New-Object System.Net.WebSockets.Client.ClientWebSocket
            $cancellationTokenSource = New-Object System.Threading.CancellationTokenSource($timeout * 1000)
            try {
                $duration = Measure-Command {
                    $ws.ConnectAsync($url, $cancellationTokenSource.Token).GetAwaiter().GetResult()
                    $requestBytes = [System.Text.Encoding]::UTF8.GetBytes('{"jsonrpc":"2.0","id":1,"method":"eth_blockNumber","params":[]}')
                    $ws.SendAsync($requestBytes, [System.Net.WebSockets.WebSocketMessageType]::Text, $true, $cancellationTokenSource.Token).GetAwaiter().GetResult()

                    $buffer = New-Object byte[] 8192
                    $result = $ws.ReceiveAsync($buffer, $cancellationTokenSource.Token).GetAwaiter().GetResult()
                    $responseJson = [System.Text.Encoding]::UTF8.GetString($buffer, 0, $result.Count)
                    $ws.CloseAsync([System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure, "Done", $cancellationTokenSource.Token).GetAwaiter().GetResult()
                }
                $response = $responseJson | ConvertFrom-Json
                if ($response.result) {
                    $successes++
                    $latencies.Add($duration.TotalMilliseconds)
                } else {
                    $failures++
                }
            } catch {
                $failures++
            } finally {
                if ($ws) { $ws.Dispose() }
                if ($cancellationTokenSource) { $cancellationTokenSource.Dispose() }
            }
        }
    }

    return [PSCustomObject]@{
        Url       = $url
        Type      = $type
        Successes = $successes
        Failures  = $failures
        Writable  = $writable
        Debuggable = $debuggable
        MevCapability = $mevCapability
        Latencies = $latencies
    }
}

$jobs = @()
foreach ($url in $uniqueUrls) {
    $jobs += Start-ThreadJob -ScriptBlock $testBlock -ArgumentList $url, $Samples, $TimeoutSec
}

Write-Host "All benchmark jobs started. Waiting for completion..."
$rawResults = $jobs | Wait-Job | Receive-Job

Write-Phase "Benchmark Results"

$finalReport = @()
foreach ($result in $rawResults) {
    $stats = [PSCustomObject]@{
        Url = $result.Url
        Type = $result.Type
        Writable = if ($result.Type -eq "HTTP") {
            $result.Writable
        } else { "N/A" }
        Debug = if ($result.Type -eq "HTTP") {
            $result.Debuggable
        } else { "N/A" }
        MevCapability = if ($result.Type -eq "HTTP") {
            $result.MevCapability
        } else { "N/A" }
        SuccessRate = if (($result.Successes + $result.Failures) -gt 0) {
            [math]::Round(($result.Successes / ($result.Successes + $result.Failures)) * 100, 2)
        } else { 0 }
        AvgLatencyMs = if ($result.Latencies.Count -gt 0) {
            [math]::Round(($result.Latencies | Measure-Object -Average).Average, 2)
        } else { -1 }
        MinLatencyMs = if ($result.Latencies.Count -gt 0) {
            [math]::Round(($result.Latencies | Measure-Object -Minimum).Minimum, 2)
        } else { -1 }
        MaxLatencyMs = if ($result.Latencies.Count -gt 0) {
            [math]::Round(($result.Latencies | Measure-Object -Maximum).Maximum, 2)
        } else { -1 }
        P95LatencyMs = if ($result.Latencies.Count -gt 0) {
            $sortedLatencies = $result.Latencies | Sort-Object
            $p95Index = [math]::Min($sortedLatencies.Count - 1, [math]::Ceiling($sortedLatencies.Count * 0.95) - 1)
            [math]::Round($sortedLatencies[$p95Index], 2)
        } else { -1 }
        Successes = $result.Successes
        Failures = $result.Failures
    }
    $finalReport += $stats
}

$sortedReport = $finalReport | Sort-Object -Property @{Expression = "SuccessRate"; Descending = $true }, @{Expression = "AvgLatencyMs"; Ascending = $true }

$sortedReport | Format-Table -AutoSize -Wrap

if (-not [string]::IsNullOrEmpty($OutputFile)) {
    $outputDir = Split-Path -Path $OutputFile -Parent
    if ($outputDir -and (-not (Test-Path $outputDir))) {
        New-Item -ItemType Directory -Path $outputDir | Out-Null
    }
    $sortedReport | ConvertTo-Json -Depth 5 | Out-File -FilePath $OutputFile -Encoding utf8
    Write-Host "`nBenchmark report saved to '$OutputFile'" -ForegroundColor Green
}

Write-Host "`nBenchmark complete. The table above is ranked by success rate, then by average latency." -ForegroundColor Green
Write-Host "Lower latency is better. Use this data to populate your primary and fallback RPC URLs."

```