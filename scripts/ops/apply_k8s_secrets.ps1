<#
.SYNOPSIS
  Creates or updates a Kubernetes secret from a local .env file.
.DESCRIPTION
  This script parses a .env file and uses its key-value pairs to create a
  Kubernetes generic secret. This is the recommended way to apply environment
  configuration to the OMEGA-FINALLY-RICH stack when deploying to Kubernetes.
.EXAMPLE
  # Create a secret named 'omega-secrets' in the default namespace from .env
  .\scripts\ops\apply_k8s_secrets.ps1 -SecretName "omega-secrets"

  # Perform a dry run to see what command would be executed
  .\scripts\ops\apply_k8s_secrets.ps1 -SecretName "omega-secrets" -DryRun

  # Create a secret in a specific namespace
  .\scripts\ops\apply_k8s_secrets.ps1 -SecretName "omega-secrets" -Namespace "production"
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [string]$SecretName,

    [string]$Namespace = "default",
    [string]$EnvPath = ".env",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$repoRoot = (Get-Item -Path $PSScriptRoot).Parent.Parent.FullName
Set-Location $repoRoot

if (-not (Test-Path $EnvPath)) {
    throw "Environment file not found at '$EnvPath'. Please create it from the .env.example template."
}
if (-not (Get-Command kubectl -ErrorAction SilentlyContinue)) {
    throw "kubectl is not available on your PATH. Please install it and configure your context."
}

Write-Host "Parsing environment variables from '$EnvPath'..."
$fromLiteralArgs = @()
$count = 0
# Regex to parse KEY=VALUE, handling single quotes, double quotes, unquoted values, and inline comments.
# Group 1: The key
# Group 2: The raw value part (which may include quotes)
$envRegex = '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*((?:\'[^\']*\''|"[^"]*"|[^#]*))\s*(?:#.*)?$'

foreach ($line in Get-Content $EnvPath) {
    $trimmed = $line.Trim()
    if ($trimmed -and -not $trimmed.StartsWith("#") -and $trimmed.Contains("=")) {
        $key, $value = $trimmed.Split("=", 2)
    # Skip blank lines or lines that are only comments
    if (-not $line.Trim() -or $line.Trim().StartsWith("#")) {
        continue
    }

    if ($line -match $envRegex) {
        $key = $Matches[1]
        $value = $Matches[2].TrimEnd() # This is the raw value, e.g., "some string" or just a_value
        $fromLiteralArgs += "--from-literal=$key=$value"
        $count++
    }
}

if ($count -eq 0) {
    throw "No valid KEY=value pairs found in '$EnvPath'."
}

Write-Host "Found $count variables to apply to secret '$SecretName' in namespace '$Namespace'."

$baseCommand = "kubectl create secret generic $SecretName --namespace $Namespace"
$fullCommand = "$baseCommand $($fromLiteralArgs -join ' ')"

if ($DryRun) {
    Write-Host "`n[DRY RUN] The following command would be executed:" -ForegroundColor Yellow
    Write-Host $fullCommand
} else {
    Write-Host "`nApplying secret..."
    # Add --dry-run=client -o yaml to first create, then pipe to apply for idempotency
    $yamlOutput = Invoke-Expression "$fullCommand --dry-run=client -o yaml"
    $yamlOutput | kubectl apply -f -
    Write-Host "✅ Secret '$SecretName' created/updated successfully." -ForegroundColor Green
}