param(
    [switch]$Install,
    [switch]$Producer,
    [switch]$Transformer,
    [switch]$SkipContainers,
    [switch]$NoAutoStartDocker,
    [int]$DockerWaitSeconds = 120
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$IndexerDir = Join-Path $Root "indexer\omega-polygon-indexer"
$ComposeFile = Join-Path $Root "infra\compose\docker-compose.indexer.yml"

function Test-DockerDaemon {
    try {
        $server = docker version --format '{{json .Server}}' 2>$null
        return -not [string]::IsNullOrWhiteSpace($server) -and $server -ne "null"
    } catch {
        return $false
    }
}

function Get-DockerDesktopPath {
    $candidates = @(
        (Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"),
        (Join-Path $env:LOCALAPPDATA "Docker\Docker Desktop.exe")
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            return $candidate
        }
    }
    return $null
}

function Ensure-DockerDaemon {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "Docker CLI is not installed or is not on PATH. Install Docker Desktop, then rerun this script."
    }

    if (Test-DockerDaemon) {
        return
    }

    if ($NoAutoStartDocker) {
        throw "Docker daemon is not reachable. Start Docker Desktop, then rerun this script."
    }

    $dockerDesktop = Get-DockerDesktopPath
    if (-not $dockerDesktop) {
        throw "Docker daemon is not reachable and Docker Desktop was not found. Install/start Docker Desktop, or rerun with -SkipContainers to install indexer packages only."
    }

    Write-Host "Docker daemon is not reachable. Starting Docker Desktop and waiting up to $DockerWaitSeconds seconds..."
    Start-Process -FilePath $dockerDesktop -WindowStyle Hidden | Out-Null

    $deadline = (Get-Date).AddSeconds($DockerWaitSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-DockerDaemon) {
            Write-Host "Docker daemon is online."
            return
        }
        Start-Sleep -Seconds 3
    }

    throw "Docker Desktop did not expose the Docker daemon within $DockerWaitSeconds seconds. Open Docker Desktop once, wait until it reports Running, then rerun this script."
}

Set-Location $Root

if ($Install) {
    Set-Location $IndexerDir
    npm install
    Set-Location $Root
}

if (-not $SkipContainers) {
    Ensure-DockerDaemon
    docker compose -f $ComposeFile up -d
    Write-Host "Omega indexer infrastructure online."
    Write-Host "Kafka: 127.0.0.1:9092"
    Write-Host "Redpanda Admin: http://127.0.0.1:9644"
    Write-Host "Mongo: mongodb://127.0.0.1:27017/omega_indexer"
} else {
    Write-Host "Skipping Redpanda/Mongo container startup because -SkipContainers was set."
}

if ($Producer) {
    Set-Location $IndexerDir
    npm run producer
    exit $LASTEXITCODE
}

if ($Transformer) {
    Set-Location $IndexerDir
    npm run transformer
    exit $LASTEXITCODE
}

Write-Host "Run with -Install once, then -Producer and -Transformer in managed processes."
