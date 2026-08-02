function Resolve-EnvContractPath {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot
    )

    $explicit = $env:OMEGA_ENV_PATH
    if (-not [string]::IsNullOrWhiteSpace($explicit)) {
        if ([System.IO.Path]::IsPathRooted($explicit)) {
            return $explicit
        }
        return (Join-Path $RepoRoot $explicit)
    }

    $profile = "$($env:OMEGA_ENV_PROFILE)$($env:OMEGA_RUNTIME_PROFILE)$($env:ENVIRONMENT)".ToLowerInvariant()
    $candidates = @(".env")

    if ($profile -match "test|tests|testing|ci") {
        $candidates = @("test.env", ".env.test", ".env.testing", ".env")
    }
    elseif ($profile -match "prod|production|live") {
        $candidates = @("production.env", "prodution.env", ".env.production", ".env")
    }

    foreach ($candidate in $candidates) {
        $candidatePath = Join-Path $RepoRoot $candidate
        if (Test-Path $candidatePath) {
            return $candidatePath
        }
    }

    return (Join-Path $RepoRoot ".env")
}
