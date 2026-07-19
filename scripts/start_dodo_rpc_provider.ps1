[CmdletBinding()]
param(
    [Parameter(Mandatory=$false)]
    [ValidateSet("Start", "Stop", "Status")]
    [string]$Mode = "Start",

    [Parameter(Mandatory=$false)]
    [string]$NodeCommand = "pnpm",

    [Parameter(Mandatory=$false)]
    [int]$Port = 3000,

    [Parameter(Mandatory=$false)]
    [string]$BrowserPath = "",

    [Parameter(Mandatory=$false)]
    [switch]$Foreground
)

$ErrorActionPreference = "Stop"
$JobName = "DodoRpcProvider"

$repoRoot = Split-Path -Parent $PSScriptRoot
$providerDir = Join-Path $repoRoot "vendor\web3-rpc-provider"
if (!(Test-Path -LiteralPath $providerDir)) {
    throw "DODOEX web3-rpc-provider is missing at $providerDir"
}

function Test-PortInUse($port) {
    try {
        $tcpConnection = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
        if ($null -ne $tcpConnection) {
            return $true
        }
        return $false
    } catch {
        return $false
    }
}

Write-Host "INFO: Locating a valid browser executable for Puppeteer..."
if ([string]::IsNullOrWhiteSpace($BrowserPath)) {
    $candidates = @(
        $env:PUPPETEER_EXECUTABLE_PATH,
        (Get-ItemProperty -Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe' -ErrorAction SilentlyContinue).'(default)',
        (Get-ItemProperty -Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe' -ErrorAction SilentlyContinue).'(default)',
        (Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Google\Chrome\Application\chrome.exe'),
        (Join-Path $env:ProgramFiles 'Microsoft\Edge\Application\msedge.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe')
    ) | Where-Object {
        -not [string]::IsNullOrWhiteSpace($_) -and (Test-Path -LiteralPath $_ -PathType Leaf)
    } | Get-Unique

    if ($candidates) {
        $BrowserPath = $candidates[0]
        Write-Host "INFO: Found browser at '$BrowserPath'."
    }
}

if ([string]::IsNullOrWhiteSpace($BrowserPath) -or !(Test-Path -LiteralPath $BrowserPath)) {
    Write-Error "FATAL: Could not find a suitable browser for Puppeteer."
    Write-Error "Please set the PUPPETEEER_EXECUTABLE_PATH environment variable or pass the -BrowserPath parameter."
    exit 1
}

$env:PUPPETEER_EXECUTABLE_PATH = $BrowserPath
$env:PORT = "$Port"

if (-not (Get-Command $NodeCommand -ErrorAction SilentlyContinue)) {
    Write-Error "FATAL: '$NodeCommand' command not found. Please ensure Node.js and the specified package manager are installed and in your PATH."
    exit 1
}

if ($Mode -eq "Stop") {
    $job = Get-Job -Name $JobName -ErrorAction SilentlyContinue
    if ($job) {
        Write-Host "INFO: Stopping DODO RPC provider job..."
        Stop-Job -Job $job
        Remove-Job -Job $job
        Write-Host "INFO: Job '$JobName' stopped and removed."
    } else {
        Write-Host "INFO: No active job named '$JobName' found."
    }
    exit 0
}

if ($Mode -eq "Status") {
    $job = Get-Job -Name $JobName -ErrorAction SilentlyContinue
    if ($job) {
        Write-Host "INFO: Job '$JobName' is running."
        $job
    } else {
        Write-Host "INFO: No active job named '$JobName' found."
    }
    exit 0
}

if ($Mode -eq "Start") {
    if (Get-Job -Name $JobName -ErrorAction SilentlyContinue) {
        Write-Error "FATAL: Job '$JobName' is already running. Use -Mode Stop to stop it first."
        exit 1
    }
    if (Test-PortInUse -port $Port) {
        if ($Foreground) {
            Write-Host "INFO: Port $Port is already in use; assuming provider is already active and holding PM2 wrapper."
            while ($true) {
                Start-Sleep -Seconds 3600
            }
        }
        Write-Error "FATAL: Port $Port is already in use. Please use a different port or stop the existing process."
        exit 1
    }

    $scriptBlock = {
        param($providerDir, $NodeCommand)
        Push-Location $providerDir
        try {
            if (!(Test-Path -LiteralPath "node_modules")) {
                & $NodeCommand install --frozen-lockfile
            }
            if (!(Test-Path -LiteralPath "dist\bootstrap.js")) {
                & $NodeCommand build
            }
            & $NodeCommand start:prod
        }
        finally {
            Pop-Location
        }
    }

    if ($Foreground) {
        Write-Host "INFO: Starting DODO RPC provider in foreground on port $Port..."
        & $scriptBlock $providerDir $NodeCommand
        exit $LASTEXITCODE
    }

    Write-Host "INFO: Starting DODO RPC provider as a background job on port $Port..."
    Start-Job -Name $JobName -ScriptBlock $scriptBlock -ArgumentList $providerDir, $NodeCommand
    Write-Host "INFO: Job '$JobName' started. Use '-Mode Status' to check or '-Mode Stop' to terminate."
}
