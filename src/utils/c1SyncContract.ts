/**
 * C1_VANGUARD ↔ Omega-Apex live-data & logic sync contract
 *
 * Single source of truth for ranking gates, sizing rules, and runtime mode.
 * Both the lean C1 scanner and Omega control center MUST use these constants
 * and helpers so discovery → ranking → simulate → dry-run stay 100% aligned.
 */

export const C1_SYNC = {
  chainId: 137,
  engineId: 'C1_VANGUARD',
  omegaEngineId: 'OMEGA_APEX',

  /** Hard gates (identical on both systems) */
  minNetPnlUsd: 0.15,
  maxSlippageBps: 40,
  minPoolTvlUsd: 1_000,
  gasFullSizeGwei: 150,
  gasStandDownGwei: 400,
  vqcRankingThreshold: 0.75,
  maxFlashPctOfShallowerPool: 0.25,
  defaultGasUnits: 210_000,
  defaultFlashFeeBps: 5, // Aave; Balancer/DODO = 0

  /** Runtime: never execute live unless both flags allow */
  requireLiveQuotesForRanking: true,
  allowMockInExecutablePath: false,
} as const;

export type RuntimeMode = 'dry-run' | 'simulate' | 'live';

/** Resolve runtime mode from env (Cloud Run / local). Default = dry-run. */
export function resolveRuntimeMode(): RuntimeMode {
  const raw = (
    process.env.OMEGA_RUNTIME_MODE ||
    process.env.EXECUTION_MODE ||
    'dry-run'
  ).toLowerCase();
  if (raw === 'live' && process.env.LIVE_TRADING === '1') return 'live';
  if (raw === 'simulate' || raw === 'sim') return 'simulate';
  return 'dry-run';
}

export function isLiveTradingEnabled(): boolean {
  return (
    resolveRuntimeMode() === 'live' &&
    process.env.LIVE_TRADING === '1' &&
    Boolean(process.env.EXECUTOR_PRIVATE_KEY || process.env.ON_CHAIN_MUSCLE)
  );
}

/** Linear gas shrink — identical to C1 omega-engine. */
export function gasShrinkMultiplier(gwei: number): number {
  if (gwei <= C1_SYNC.gasFullSizeGwei) return 1;
  if (gwei >= C1_SYNC.gasStandDownGwei) return 0;
  const range = C1_SYNC.gasStandDownGwei - C1_SYNC.gasFullSizeGwei;
  return Math.max(0, 1 - (gwei - C1_SYNC.gasFullSizeGwei) / range);
}

export interface SyncSafetyGates {
  minNetPassed: boolean;
  maxSlippagePassed: boolean;
  gasShrinkagePassed: boolean;
  liveQuotePassed: boolean;
  overallPassed: boolean;
  reason?: string;
}

/** Shared safety gates — C1 and Omega must produce the same pass/fail. */
export function runSyncSafetyGates(params: {
  netPnlUsd: number;
  slippageBps: number;
  gasGwei: number;
  isLiveQuote: boolean;
}): SyncSafetyGates {
  const minNetPassed = params.netPnlUsd >= C1_SYNC.minNetPnlUsd;
  const maxSlippagePassed = params.slippageBps <= C1_SYNC.maxSlippageBps;
  const gasShrinkagePassed = gasShrinkMultiplier(params.gasGwei) > 0;
  const liveQuotePassed =
    !C1_SYNC.requireLiveQuotesForRanking || params.isLiveQuote;

  const overallPassed =
    minNetPassed && maxSlippagePassed && gasShrinkagePassed && liveQuotePassed;

  let reason: string | undefined;
  if (!liveQuotePassed) reason = 'mock/synthetic quote blocked from executable path';
  else if (!gasShrinkagePassed) reason = 'gas stand-down';
  else if (!minNetPassed)
    reason = `net PnL $${params.netPnlUsd.toFixed(4)} < $${C1_SYNC.minNetPnlUsd}`;
  else if (!maxSlippagePassed)
    reason = `slippage ${params.slippageBps.toFixed(1)} bps > ${C1_SYNC.maxSlippageBps}`;

  return {
    minNetPassed,
    maxSlippagePassed,
    gasShrinkagePassed,
    liveQuotePassed,
    overallPassed,
    reason,
  };
}

/**
 * Cap analytical optimal size the same way C1 does:
 * min(apexOptimal, 25% shallower TVL) * gasShrink
 */
export function syncFlashSizeUsd(params: {
  apexOptimalUsd: number;
  buyTvlUsd: number;
  sellTvlUsd: number;
  gasGwei: number;
}): number {
  const shallower = Math.min(params.buyTvlUsd, params.sellTvlUsd);
  const maxByDepth = shallower * C1_SYNC.maxFlashPctOfShallowerPool;
  const shrink = gasShrinkMultiplier(params.gasGwei);
  return Math.max(0, Math.min(params.apexOptimalUsd, maxByDepth) * shrink);
}

/** Mark whether a route/quote is live on-chain (not mock/synthetic). */
export function isLiveRoute(route: {
  pools?: { address?: string; status?: string }[];
  notes?: string;
  id?: string;
}): boolean {
  if (!route.pools || route.pools.length === 0) return false;
  if (route.notes?.toLowerCase().includes('mock')) return false;
  if (route.notes?.toLowerCase().includes('synthetic')) return false;
  if (route.id?.startsWith('mock_') || route.id?.startsWith('seed_')) return false;
  const zero = '0x0000000000000000000000000000000000000000';
  return route.pools.every(
    (p) => p.address && p.address.toLowerCase() !== zero && p.status !== 'DEPRECATED'
  );
}
