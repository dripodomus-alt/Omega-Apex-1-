<#
.SYNOPSIS
Safely updates Cloud Run service apex-omega scaling and ingress settings.
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Project = "apex-scanner-live1"
$Service = "flashloan-execution-monitor"
$Region = "us-east1"

Write-Host "=== PHASE 1: ENVIRONMENT VALIDATION ==="

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    Write-Error "gcloud could not be found. Please install Google Cloud SDK."
}

Write-Host "gcloud version:"
gcloud version

$ActiveAccount = gcloud auth list --filter="status:ACTIVE" --format="value(account)"
if (-not $ActiveAccount -or $ActiveAccount -notmatch "@") {
    Write-Error "No authenticated active gcloud account found."
}
Write-Host "Active account: $ActiveAccount"

gcloud config set project $Project

$ServiceExists = gcloud run services describe $Service --region=$Region --format="value(status.url)" 2>$null
if (-not $ServiceExists) {
    Write-Error "Service $Service not found in region $Region."
}

Write-Host "Saving current service configuration before mutation..."
gcloud run services describe $Service --project=$Project --region=$Region --format=export | Out-File -Encoding UTF8 cloudrun-before.yaml

Write-Host "Saving current IAM policy..."
gcloud run services get-iam-policy $Service --project=$Project --region=$Region --format=export | Out-File -Encoding UTF8 cloudrun-iam-before.yaml

$CurrentUrl = gcloud run services describe $Service --region=$Region --format="value(status.url)"
$CurrentRevision = gcloud run services describe $Service --region=$Region --format="value(status.latestReadyRevisionName)"

Write-Host "Current URL: $CurrentUrl"
Write-Host "Current Revision: $CurrentRevision"

Write-Host "`n=== PHASE 2: APPLY MINIMAL CLOUD RUN UPDATE ==="
Write-Host "Updating Cloud Run service ingress and scaling..."
gcloud run services update $Service --project=$Project --region=$Region --ingress=all --min-instances=1 --max-instances=3 --quiet

Write-Host "Granting public invocation (roles/run.invoker to allUsers)..."
try {
    gcloud run services add-iam-policy-binding $Service --project=$Project --region=$Region --member=allUsers --role=roles/run.invoker --quiet
} catch {
    Write-Host "Warning: Organization policy may block allUsers. Output: $_"
}

Write-Host "`n=== PHASE 3: POST-DEPLOY VERIFICATION ==="
gcloud run services describe $Service --project=$Project --region=$Region --format=export | Out-File -Encoding UTF8 cloudrun-after.yaml
gcloud run services get-iam-policy $Service --project=$Project --region=$Region --format=export | Out-File -Encoding UTF8 cloudrun-iam-after.yaml

$NewUrl = gcloud run services describe $Service --region=$Region --format="value(status.url)"
Write-Host "New URL: $NewUrl"

try {
    Write-Host "Testing /health endpoint..."
    $Response = Invoke-WebRequest -Uri "$NewUrl/health" -TimeoutSec 30 -UseBasicParsing -ErrorAction SilentlyContinue
    Write-Host "HTTP Status: $($Response.StatusCode)"
    Write-Host "Health Response: $($Response.Content)"
} catch {
    Write-Host "HTTP Status: $($_.Exception.Response.StatusCode.value__)"
    Write-Host "Health Request Failed: $_"
}

Write-Host "Update complete. Please review cloudrun-after.yaml to verify preserved environment variables and secrets."
