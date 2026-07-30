<#
.SYNOPSIS
Rolls back the Cloud Run service using the exported YAML configuration.
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Project = "apex-scanner-live1"
$Service = "flashloan-execution-monitor"
$Region = "us-east1"

Write-Host "Replacing service $Service from cloudrun-before.yaml..."
if (Test-Path cloudrun-before.yaml) {
    gcloud run services replace cloudrun-before.yaml --project=$Project --region=$Region
    Write-Host "Rollback of service config complete."
} else {
    Write-Error "cloudrun-before.yaml not found."
}

Write-Host "Reverting IAM policy..."
if (Test-Path cloudrun-iam-before.yaml) {
    gcloud run services set-iam-policy $Service cloudrun-iam-before.yaml --project=$Project --region=$Region
    Write-Host "Rollback of IAM policy complete."
} else {
    Write-Error "cloudrun-iam-before.yaml not found."
}
