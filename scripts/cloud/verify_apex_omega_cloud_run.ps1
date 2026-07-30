<#
.SYNOPSIS
Verifies the current configuration of the Cloud Run service.
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Project = "apex-scanner-live1"
$Service = "flashloan-execution-monitor"
$Region = "us-east1"

Write-Host "Verifying service $Service in $Region for project $Project..."
gcloud run services describe $Service --project=$Project --region=$Region
