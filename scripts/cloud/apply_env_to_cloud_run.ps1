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
# Regex to parse KEY=VALUE, handling single quotes, double quotes, unquoted values, and inline comments.
# - Group 1: The key (e.g., "API_KEY")
# - Group 2: The value if it's single-quoted (e.g., 'value') -> content only
# - Group 3: The value if it's double-quoted (e.g., "value") -> content only
# - Group 4: The value if it's unquoted (e.g., value)
$envRegex = '^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:\'([^\']*)\'|"([^"]*)"|([^#]*))\s*(?:#.*)?$'

foreach ($line in Get-Content $EnvPath) {
    $trimmed = $line.Trim()
    # Skip blank lines or lines that are only comments
    if (-not $trimmed -or $trimmed.StartsWith("#")) {
        continue
    }

    if ($trimmed -match $envRegex) {
        $key = $Matches[1]
        # The value is in one of the capturing groups 2, 3, or 4. Coalesce them.
        # Group 4 (unquoted) needs an extra trim for trailing whitespace before a comment.
        $value = $Matches[2] + $Matches[3] + $Matches[4].TrimEnd()
        $values[$key] = $value
    }
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
