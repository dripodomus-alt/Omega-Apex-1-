<#
.SYNOPSIS
  Starts the local Omega V5 direct entrypoint using the project virtual environment.
.DESCRIPTION
  Resolves the repository root, finds the project .venv interpreter, and runs the
  configured direct startup command with that Python interpreter.
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$ScriptPath = "",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PythonArgs = @()
)

$ErrorActionPreference = "Stop"
$repoRoot = (Get-Item -Path $PSScriptRoot).Parent.Parent.FullName
Set-Location $repoRoot

if ($IsWindows) {
    $venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
} else {
    $venvPython = Join-Path $repoRoot ".venv/bin/python"
}

if (!(Test-Path -LiteralPath $venvPython)) {
    throw "Project virtual environment not found at $venvPython. Run .\\scripts\\ops\\bootstrap_hybrid_env.ps1 first."
}

Write-Host "Using project venv interpreter: $venvPython" -ForegroundColor Cyan

$cmdArgs = @()
if ($ScriptPath -and $ScriptPath.Trim()) {
    $cmdArgs += $ScriptPath
}

if ($PythonArgs.Count -gt 0) {
    $cmdArgs += $PythonArgs
}

& $venvPython @cmdArgs
exit $LASTEXITCODE
