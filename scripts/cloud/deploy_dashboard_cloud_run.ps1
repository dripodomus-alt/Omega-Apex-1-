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

# --- API Prerequisite Check ---
$requiredApis = @(
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com"
)

Write-HostColored "`n🔍 Checking for required GCP APIs in project '$Project'..." "Cyan"
$enabledApis = gcloud services list --project $Project --format="value(config.name)"
foreach ($api in $requiredApis) {
    if ($enabledApis -notcontains $api) {
        Write-HostColored "  [!] API '$api' is not enabled." "Yellow"
        $enableConfirmation = Read-Host "Do you want to enable it now? This is required for deployment. [Y/n]"
        if ($enableConfirmation -ne 'n') {
            Write-Host "  Enabling $api... this may take a minute."
            gcloud services enable $api --project $Project
            if ($LASTEXITCODE -ne 0) {
                throw "Failed to enable API '$api'."
            }
            Write-HostColored "  [✅] API '$api' enabled." "Green"
        } else {
            throw "Deployment cannot proceed without the required API: $api"
        }
    } else {
        Write-Host "  [✅] $api is enabled."
    }
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
    "--allow-unauthenticated", # The API has its own token auth, so the service can be public
    # --- ARCHITECTURAL ALIGNMENT ---
    # Override the Dockerfile's CMD to run ONLY the stateless services on Cloud Run,
    # aligning with the documented split-deployment model. The stateful engine
    # should run on the secure VM.
    "--command", "pm2-runtime",
    "--args", "start", "--args", "ecosystem.config.cjs",
    "--args", "--only", "--args", "omega-api,omega-telegram-bot" # This was pointing to the wrong file
)

& gcloud @deployArgs
if ($LASTEXITCODE -ne 0) {
    Write-HostColored "❌ gcloud run deploy failed with exit code $LASTEXITCODE" "Red"
    throw "Deployment failed."
}

# --- Post-Deployment Verification ---
if (-not $SkipHealthCheck) {
    Write-HostColored "`n🔍 Verifying service health (with retries)..." "Cyan"
    $url = gcloud run services describe $Service --project=$Project --region=$Region --format="value(status.url)"
    $token = gcloud auth print-identity-token
    if ($LASTEXITCODE -ne 0) {
        throw "gcloud auth print-identity-token failed with exit code $LASTEXITCODE"
    }

    $maxRetries = 5
    $retryDelaySeconds = 10
    $healthCheckSuccess = $false

    for ($i = 1; $i -le $maxRetries; $i++) {
        Write-Host "  Attempt $i of $maxRetries..."
        try {
            $response = Invoke-WebRequest -Uri "$url/health" -Headers @{ Authorization = "Bearer $token" } -UseBasicParsing -TimeoutSec 20
            Write-Host "  Health check URL: $url/health"
            Write-Host "  Response Status: HTTP $($response.StatusCode)"
            Write-Host "  Response Body: $($response.Content)"
            if ($response.StatusCode -eq 200) {
                $healthCheckSuccess = $true
                break
            }
        }
        catch {
            Write-HostColored "  Caught exception: $($_.Exception.Message)" "Yellow"
        }

        if ($i -lt $maxRetries) {
            Write-Host "  Health check failed. Retrying in $retryDelaySeconds seconds..."
            Start-Sleep -Seconds $retryDelaySeconds
        }
    }

    if (-not $healthCheckSuccess) {
        Write-HostColored "❌ Health check failed after $maxRetries attempts. Check the service logs for errors:" "Red"
        Write-Host "gcloud run services logs tail $Service --project $Project --region $Region"
        throw "Post-deployment health check failed."
    }
    Write-HostColored "✅ Health check passed." "Green"
}

Write-HostColored "`n🎉 Deployment complete." "Green"
$finalUrl = gcloud run services describe $Service --project=$Project --region=$Region --format="value(status.url)"
Write-Host "Service URL: $finalUrl"
