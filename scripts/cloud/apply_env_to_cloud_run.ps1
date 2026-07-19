param(
    [string]$Project = "apex-scanner-live1",
    [string]$Region = "us-east1",
    [string]$Service = "flashloan-execution-monitor",
    [string]$EnvPath = ".env"
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $root

if (-not (Test-Path $EnvPath)) {
    throw "Environment file not found: $EnvPath"
}

$python = (Get-Command python -ErrorAction Stop).Source
$env:CLOUDSDK_PYTHON = $python

$gcloudBin = Join-Path $env:LOCALAPPDATA "Google\CloudSDKPortable\google-cloud-sdk\bin"
if (Test-Path $gcloudBin) {
    $env:Path = "$env:Path;$gcloudBin"
}

$null = Get-Command gcloud -ErrorAction Stop

$values = [ordered]@{}
foreach ($line in Get-Content $EnvPath) {
    $trimmed = $line.Trim()
    if (-not $trimmed -or $trimmed.StartsWith("#")) {
        continue
    }
    if ($trimmed -notmatch "^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$") {
        continue
    }
    $key = $Matches[1]
    $value = $Matches[2].Trim()
    if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
        $value = $value.Substring(1, $value.Length - 2)
    }
    $values[$key] = $value
}

if ($values.Count -eq 0) {
    throw "No valid KEY=value entries found in $EnvPath"
}

$tmp = Join-Path $env:TEMP ("cloud-run-env-" + [guid]::NewGuid().ToString("N") + ".yaml")
try {
    $lines = foreach ($key in $values.Keys) {
        $jsonValue = $values[$key] | ConvertTo-Json -Compress
        "${key}: ${jsonValue}"
    }
    Set-Content -Path $tmp -Value $lines -Encoding UTF8

    Write-Host "Applying $($values.Count) environment variables to $Service in $Project/$Region"
    gcloud run services update $Service `
        --project=$Project `
        --region=$Region `
        --env-vars-file=$tmp `
        --quiet
    if ($LASTEXITCODE -ne 0) {
        throw "gcloud run services update failed with exit code $LASTEXITCODE"
    }

    $revision = gcloud run services describe $Service --project=$Project --region=$Region --format="value(status.latestReadyRevisionName)"
    if ($LASTEXITCODE -ne 0) {
        throw "gcloud run services describe failed with exit code $LASTEXITCODE"
    }
    Write-Host "Latest ready revision: $revision"
}
finally {
    if (Test-Path $tmp) {
        Remove-Item -LiteralPath $tmp -Force
    }
}
