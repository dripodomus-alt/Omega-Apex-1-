param(
    [string]$Project = "apex-scanner-live1",
    [string]$Region = "us-east1",
    [string]$Service = "flashloan-execution-monitor",
    [switch]$SkipHealthCheck,
    [switch]$Force # Add a -Force switch to bypass the confirmation prompt
)

$ErrorActionPreference = "Stop"

# Helper for writing colored output
function Write-HostColored {
    param([string]$Message, [string]$Color)
    Write-Host $Message -ForegroundColor $Color
}

# --- Pre-flight Checks ---
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $root

$python = (Get-Command python -ErrorAction Stop).Source
$env:CLOUDSDK_PYTHON = $python

$gcloudBin = Join-Path $env:LOCALAPPDATA "Google\CloudSDKPortable\google-cloud-sdk\bin"
if (Test-Path $gcloudBin) {
    $env:Path = "$env:Path;$gcloudBin"
}

try {
    $null = Get-Command gcloud -ErrorAction Stop
}
catch {
    Write-HostColored "❌ gcloud command not found. Please install the Google Cloud SDK and ensure it's in your PATH." "Red"
    exit 1
}

# --- Confirmation Gate ---
Write-HostColored "Deployment Plan:" "Yellow"
Write-Host "  Project: $Project"
Write-Host "  Region:  $Region"
Write-Host "  Service: $Service"
Write-Host "  Source:  $root"
Write-Host "This will build the Dockerfile and deploy a new revision to Cloud Run."

if (-not $Force) {
    $confirmation = Read-Host "Do you want to proceed with the deployment? [y/N]"
    if ($confirmation -ne 'y') {
        Write-HostColored "Deployment cancelled by user." "Red"
        exit
    }
}

# --- Deployment ---
Write-HostColored "`n🚀 Starting deployment... this may take several minutes." "Cyan"

$deployArgs = @(
    "run", "deploy", $Service,
    "--source", ".",
    "--project", $Project,
    "--region", $Region,
    "--allow-unauthenticated" # The API has its own token auth, so the service can be public
)

& gcloud @deployArgs
if ($LASTEXITCODE -ne 0) {
    Write-HostColored "❌ gcloud run deploy failed with exit code $LASTEXITCODE" "Red"
    throw "Deployment failed."
}

# --- Post-Deployment Verification ---
if (-not $SkipHealthCheck) {
    Write-HostColored "`n🔍 Verifying service health..." "Cyan"
    $url = gcloud run services describe $Service --project=$Project --region=$Region --format="value(status.url)"
    $token = gcloud auth print-identity-token
    if ($LASTEXITCODE -ne 0) {
        throw "gcloud auth print-identity-token failed with exit code $LASTEXITCODE"
    }
    $response = Invoke-WebRequest -Uri "$url/health" -Headers @{ Authorization = "Bearer $token" } -UseBasicParsing -TimeoutSec 60
    Write-Host "  Health check URL: $url/health"
    Write-Host "  Response Status: HTTP $($response.StatusCode)"
    Write-Host "  Response Body: $($response.Content)"
    if ($response.StatusCode -ne 200) {
        Write-HostColored "❌ Health check failed. Check the service logs for errors:" "Red"
        Write-Host "gcloud run services logs tail $Service --project $Project --region $Region"
        throw "Post-deployment health check failed."
    }
    Write-HostColored "✅ Health check passed." "Green"
}

Write-HostColored "`n🎉 Deployment complete." "Green"
$finalUrl = gcloud run services describe $Service --project=$Project --region=$Region --format="value(status.url)"
Write-Host "Service URL: $finalUrl"
