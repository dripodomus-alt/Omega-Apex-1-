<#
.DEPRECATION_NOTICE
  This script is part of the legacy omega_v5 (Python) architecture and is now obsolete.
  The functionality for deploying on-chain adapters has been migrated to a TypeScript
  script within the OMEGA-FINALLY-RICH monorepo.

.USAGE
  To deploy adapters, use the new pnpm command from the project root:

  pnpm --filter execution deploy

  This file is preserved as a historical artifact and should not be used.
#>

Write-Host "[DEPRECATED] This script is obsolete. Use 'pnpm --filter execution deploy' instead." -ForegroundColor Yellow
exit 1