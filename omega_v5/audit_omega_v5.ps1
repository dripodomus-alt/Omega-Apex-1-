<#
.SYNOPSIS
  Audits source code updates, repository status, security secrets,
  and GCP Cloud Run deployment readiness for omega_v5 / Apex-Omega.
.DESCRIPTION
  This script is a PowerShell conversion of the original audit_omega_v5.sh.
  It performs a comprehensive audit of the project's state, including Git status,
  file architecture, security vulnerabilities (hardcoded secrets), toolchain
  dependencies, and GCP readiness.
.EXAMPLE
  .\scripts\ops\audit_omega_v5.ps1
.EXAMPLE
  .\scripts\ops\audit_omega_v5.ps1 -ProjectDir C:\path\to\your\project
#>
[CmdletBinding()]
param(
    [string]$ProjectDir = (Get-Location).Path
)

$ErrorActionPreference = "Stop"

# --- Color Formatting Helper Functions ---
function log_info { param([string]$Message) Write-Host "[INFO] $Message" -ForegroundColor Blue }
function log_success { param([string]$Message) Write-Host "[SUCCESS] $Message" -ForegroundColor Green }
function log_warning { param([string]$Message) Write-Host "[WARNING] $Message" -ForegroundColor Yellow }
function log_error { param([string]$Message) Write-Host "[ERROR] $Message" -ForegroundColor Red }
function log_header {
    param([string]$Message)
    Write-Host "`n====================================================================" -ForegroundColor Cyan
    Write-Host " $Message " -ForegroundColor Cyan
    Write-Host "====================================================================" -ForegroundColor Cyan
}

# --- Environment & Variables Configuration ---
$TIMESTAMP = Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'
$LOG_FILE = Join-Path $ProjectDir "omega_v5_audit_${TIMESTAMP}.log"

# Define critical expected project paths
$CRITICAL_FILES = @(
    "deploy_omega_v5.sh", # Kept for consistency with original script
    "Dockerfile",
    "package.json"
)

# High Entropy / Secret Patterns for Security Audit
$SECRET_PATTERNS = @(
    "PRIVATE_KEY",
    "SECRET_KEY",
    "AKIA[0-9A-Z]{16}", # AWS Key Pattern
    "ghp_[a-zA-Z0-9]{36}", # GitHub Personal Access Token Pattern
    "AIza[0-9A-Za-z-_]{35}", # GCP API Key Pattern
    "0x[a-fA-F0-9]{64}" # Raw Ethereum Private Key Pattern
)

# --- Banner Output ---
Write-Host @"
  ██████╗ ███╗   ███╗███████╗██████╗  █████╗     ██╗   ██╗███████╗
 ██╔═══██╗████╗ ████║██╔════╝██╔══██╗██╔══██╗    ██║   ██║██╔════╝
 ██║   ██║██╔████╔██║█████╗  ██████╔╝███████║    ██║   ██║███████╗
 ██║   ██║██║╚██╔╝██║██╔══╝  ██╔═══╝ ██╔══██║    ╚██╗ ██╔╝╚════██║
 ╚██████╔╝██║ ╚═╝ ██║███████╗██║     ██║  ██║     ╚████╔╝ ███████║
  ╚═════╝ ╚═╝     ╚═╝╚══════╝╚═╝     ╚═╝  ╚═╝      ╚═══╝  ╚══════╝
                     SOURCE UPDATE AUDITOR v5.0
"@ -ForegroundColor Cyan

# Start logging
Start-Transcript -Path $LOG_FILE -Append

log_info "Starting omega_v5 Source Code Audit..."
log_info "Target Directory: $ProjectDir"
log_info "Audit Log File  : $LOG_FILE"

# ==============================================================================
# SECTION 1: GIT REPOSITORY & SOURCE UPDATES
# ==============================================================================
log_header "1. GIT REPOSITORY STATUS & LATEST UPDATES"

# Check if it's a git repo
try {
    git rev-parse --is-inside-work-tree | Out-Null
    $isGitRepo = $true
} catch {
    $isGitRepo = $false
}

if ($isGitRepo) {
    $CURRENT_BRANCH = git rev-parse --abbrev-ref HEAD
    $CURRENT_COMMIT = git rev-parse --short HEAD
    $COMMIT_DATE = git log -1 --format="%cd" --date=iso
    $COMMIT_MSG = git log -1 --format="%s"

    log_success "Git repository detected."
    log_info "Current Branch : $CURRENT_BRANCH"
    log_info "Latest Commit  : $CURRENT_COMMIT ($COMMIT_DATE)"
    log_info "Commit Message : $COMMIT_MSG"

    Write-Host ""
    log_info "Checking working tree status..."
    $UNCOMMITTED_CHANGES = git status --porcelain
    if ($UNCOMMITTED_CHANGES) {
        log_warning "Uncommitted changes detected in working tree:"
        Write-Host $UNCOMMITTED_CHANGES -ForegroundColor Yellow
    } else {
        log_success "Working tree clean. No uncommitted local changes."
    }

    Write-Host ""
    log_info "Last 5 Commits on $CURRENT_BRANCH:"
    git log -n 5 --oneline --decorate
} else {
    log_warning "Directory is not a Git repository. Skipping Git commit trace."
}

# ==============================================================================
# SECTION 2: FILE SYSTEM & CRITICAL COMPONENT AUDIT
# ==============================================================================
log_header "2. CRITICAL FILE ARCHITECTURE CHECK"

$MISSING_COUNT = 0
foreach ($file in $CRITICAL_FILES) {
    if (Test-Path (Join-Path $ProjectDir $file)) {
        log_success "Found critical file: $file"
    } else {
        log_error "Missing required file: $file"
        $MISSING_COUNT++
    }
}

if ($MISSING_COUNT -eq 0) {
    log_success "All critical files are present."
} else {
    log_warning "$MISSING_COUNT critical file(s) missing from target root."
}

# ==============================================================================
# SECTION 3: SECURITY SCAN FOR EXPOSED SECRETS & KEYS
# ==============================================================================
log_header "3. SECURITY AUDIT - HIGH-ENTROPY SECRET SCAN"

log_info "Scanning source tree for unencrypted API keys, private keys, and secrets..."
$LEAK_FOUND = 0

$excludeDirs = @(".git", "node_modules", "target", "dist", ".venv", "cache", "out")
$excludeFiles = @("*.log", ".env.example", "Cargo.lock")

foreach ($pattern in $SECRET_PATTERNS) {
    $FOUND_LEAKS = Get-ChildItem -Path $ProjectDir -Recurse -Exclude $excludeDirs | Where-Object { $_.PSIsContainer -eq $false } | Select-String -Pattern $pattern -Exclude $excludeFiles -ErrorAction SilentlyContinue

    if ($FOUND_LEAKS) {
        log_error "Potential secret/key exposure detected for pattern '$pattern':"
        $FOUND_LEAKS | ForEach-Object { Write-Host $_ -ForegroundColor Red }
        $LEAK_FOUND = 1
    }
}

if ($LEAK_FOUND -eq 0) {
    log_success "No unencrypted high-entropy secrets or private keys detected in tracking path."
} else {
    log_error "CRITICAL: Potential hardcoded secrets found. Migrate credentials to GCP Secret Manager immediately."
}

# ==============================================================================
# SECTION 4: DEPENDENCY & TOOLCHAIN VERIFICATION
# ==============================================================================
log_header "4. LOCAL TOOLCHAIN & DEPENDENCY CHECK"

function check_tool {
    param([string]$tool_name)
    if (Get-Command $tool_name -ErrorAction SilentlyContinue) {
        try {
            $version = (& $tool_name --version 2>&1 | Select-Object -First 1)
            log_success "Tool found: $tool_name ($version)"
        } catch {
            log_success "Tool found: $tool_name (version check failed)"
        }
    } else {
        log_warning "Tool NOT found: $tool_name"
    }
}

check_tool "git"
check_tool "docker"
check_tool "gcloud"
check_tool "node"
check_tool "cargo"

# Check Node.js dependencies if package.json exists
if (Test-Path (Join-Path $ProjectDir "package.json")) {
    Write-Host ""
    log_info "Auditing package.json dependencies for ethers.js conflicts..."
    $ethersLine = Get-Content (Join-Path $ProjectDir "package.json") | Select-String -Pattern '"ethers":' -ErrorAction SilentlyContinue
    if ($ethersLine) {
        log_info "Ethers dependency version: $ethersLine"
    }
}

# ==============================================================================
# SECTION 5: GCP CLOUD RUN DEPLOYMENT READINESS
# ==============================================================================
log_header "5. GCP DEPLOYMENT READINESS EVALUATION"

if (Get-Command gcloud -ErrorAction SilentlyContinue) {
    $GCP_ACCOUNT = (gcloud config get-value account 2>$null)
    if (!$GCP_ACCOUNT) { $GCP_ACCOUNT = "Not authenticated" }
    
    $GCP_PROJECT = (gcloud config get-value project 2>$null)
    if (!$GCP_PROJECT) { $GCP_PROJECT = "No active project" }

    log_info "Active GCP Account : $GCP_ACCOUNT"
    log_info "Active GCP Project : $GCP_PROJECT"

    if (($GCP_PROJECT -ne "No active project") -and ($GCP_ACCOUNT -ne "Not authenticated")) {
        log_success "gcloud CLI is configured and authenticated."
    } else {
        log_warning "gcloud CLI requires authentication or project setup."
    }
} else {
    log_warning "gcloud CLI is not installed. Cloud Run deployments cannot be verified locally."
}

# ==============================================================================
# AUDIT SUMMARY
# ==============================================================================
log_header "AUDIT SUMMARY & RECOMMENDATIONS"

log_info "Audit complete for omega_v5."
log_info "Full execution transcript written to: $LOG_FILE"

if ($LEAK_FOUND -ne 0) {
    Write-Host "[ACTION REQUIRED] Purge exposed secrets and transition all runtime keys to GCP Secret Manager." -ForegroundColor Red
}

if ($MISSING_COUNT -ne 0) {
    Write-Host "[ACTION REQUIRED] Re-instantiate missing architecture files before triggering deployment." -ForegroundColor Yellow
}

if (($LEAK_FOUND -eq 0) -and ($MISSING_COUNT -eq 0)) {
    Write-Host "[SYSTEM READY] Codebase and deployment environment pass structural verification." -ForegroundColor Green
}

# Stop logging
Stop-Transcript
