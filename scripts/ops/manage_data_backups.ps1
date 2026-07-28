<#
.SYNOPSIS
  Manages the backup and archival of critical application data.
.DESCRIPTION
  This script provides functions to back up the 'out/' directory (containing logs,
  reports, and benchmark results) and the SQLite indexer database. It creates
  timestamped archives for disaster recovery and historical analysis.

  This aligns with the Data Governance policy for data lifecycle and recovery.
.EXAMPLE
  # Create a full backup of the 'out' directory and the indexer DB.
  .\scripts\ops\manage_data_backups.ps1 -Backup

  # List existing backups.
  .\scripts\ops\manage_data_backups.ps1 -List

  # Prune backups older than 30 days.
  .\scripts\ops\manage_data_backups.ps1 -Prune -Days 30
#>
[CmdletBinding()]
param(
    [switch]$Backup,
    [switch]$List,
    [switch]$Prune,
    [int]$Days = 30
)

$ErrorActionPreference = "Stop"
$repoRoot = (Get-Item -Path $PSScriptRoot).Parent.Parent.FullName
Set-Location $repoRoot

$backupDir = Join-Path $repoRoot "out/backups"
$outDir = Join-Path $repoRoot "out"
$indexerDbPath = Join-Path $repoRoot "out/polygon_indexer.sqlite" # From config.py

function Write-Phase { param([string]$Message) Write-Host "`n" + ("=" * 50) + "`n" + " $Message" + "`n" + ("=" * 50) -ForegroundColor Cyan }

if ($Backup) {
    Write-Phase "Creating Data Backup"
    New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $archiveName = "omega_v5_data_backup_$timestamp.zip"
    $archivePath = Join-Path $backupDir $archiveName

    Write-Host "Archiving critical 'out' subdirectories and indexer DB to: $archivePath"
    # Select specific sub-folders from 'out' to avoid archiving the backups folder itself
    $itemsToArchive = Get-ChildItem -Path $outDir -Exclude "backups"
    if (Test-Path $indexerDbPath) {
        # Ensure the indexer DB is included if it exists at the expected path
        $itemsToArchive += Get-Item $indexerDbPath
    }

    Compress-Archive -Path $itemsToArchive.FullName -DestinationPath $archivePath -Force
    Write-Host "Backup complete." -ForegroundColor Green
}
elseif ($List) {
    Write-Phase "Listing Existing Backups"
    Get-ChildItem -Path $backupDir -Filter "*.zip" | Select-Object Name, Length, LastWriteTime
}
elseif ($Prune) {
    Write-Phase "Pruning Backups Older Than $Days Days"
    $cutoffDate = (Get-Date).AddDays(-$Days)
    Get-ChildItem -Path $backupDir -Filter "*.zip" | Where-Object { $_.LastWriteTime -lt $cutoffDate } | ForEach-Object {
        Write-Host "Removing old backup: $($_.Name)" -ForegroundColor Yellow
        Remove-Item -Path $_.FullName -Force
    }
    Write-Host "Pruning complete."
}
else {
    Write-Host "No action specified. Use -Backup, -List, or -Prune."
}