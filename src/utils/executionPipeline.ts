import { ArbitrageRoute, ExecutionMode, PoolInfo, SimulationAuditLog } from '../types';
import { validateRouteAssetRegistry } from './mathEngine';
import { computeLegLedger } from './transientAccounting';
import { POLYGON_CHAIN_CONFIG } from '../config/chainConfig';
import { StagedPayload, DispatchResult, IDispatcher, createDispatcher } from './dispatcher';
import {
  C1_SYNC,
  isLiveRoute,
  runSyncSafetyGates,
  resolveRuntimeMode,
  isLiveTradingEnabled,
} from './c1SyncContract';

export type PipelineStageName = 'DISCOVERY' | 'RANKING' | 'STAGING' | 'DISPATCH';

export interface PipelineStageResult {
  stage: PipelineStageName;
  passed: boolean;
  reason?: string;
}

export interface PipelineRunResult {
  dispatchResult: DispatchResult;
  executedRoute: ArbitrageRoute;
  auditLog: SimulationAuditLog;
  stageResults: PipelineStageResult[];
}

/**
 * Unified execution pipeline — C1 ↔ Omega synchronized.
 * Ranking rejects mock/synthetic when requireLiveQuotesForRanking is true.
 * Live broadcast only when isLiveTradingEnabled().
 */
export async function runExecutionPipeline(
  route: ArbitrageRoute,
  pools: PoolInfo[],
  mode: ExecutionMode,
  gasGwei: number,
  dispatcher?: IDispatcher
): Promise<PipelineRunResult> {
  const stageResults: PipelineStageResult[] = [];
  const timestamp = new Date().toISOString().replace('T', ' ').substring(0, 19) + ' UTC';
  const runtime = resolveRuntimeMode();

  // ── Stage 1: Discovery ────────────────────────────────────────────────────
  const discoveryPassed =
    Boolean(route.id) && Boolean(route.pathString) && route.pools.length > 0;
  stageResults.push({
    stage: 'DISCOVERY',
    passed: discoveryPassed,
    reason: discoveryPassed ? undefined : 'Route is missing required path or pool data',
  });
  if (!discoveryPassed) {
    throw new Error(
      `[PIPELINE] Discovery stage failed for route ${route.id}: missing path or pool data`
    );
  }

  // ── Stage 2: Ranking (C1-aligned gates + live filter) ─────────────────────
  const live = isLiveRoute(route);
  const slipBps = route.slippageToleranceBps ?? 0;
  const syncGates = runSyncSafetyGates({
    netPnlUsd: route.netProfitUSD,
    slippageBps: slipBps,
    gasGwei,
    isLiveQuote: live,
  });

  const vqcOk = route.vqcAlphaScore >= C1_SYNC.vqcRankingThreshold;
  const rankingPassed = vqcOk && syncGates.overallPassed;

  stageResults.push({
    stage: 'RANKING',
    passed: rankingPassed,
    reason: rankingPassed
      ? undefined
      : !vqcOk
        ? `VQC alpha ${route.vqcAlphaScore} below ${C1_SYNC.vqcRankingThreshold}`
        : syncGates.reason,
  });
  if (!rankingPassed) {
    throw new Error(
      `[PIPELINE] Ranking stage rejected route ${route.id}: ${
        !vqcOk
          ? `VQC ${route.vqcAlphaScore}`
          : syncGates.reason || 'sync gates failed'
      }`
    );
  }

  // ── Stage 3: Staging / registry ───────────────────────────────────────────
  const validation = validateRouteAssetRegistry(route, pools);
  stageResults.push({
    stage: 'STAGING',
    passed: validation.isExecutable,
    reason: validation.isExecutable ? undefined : validation.reason,
  });
  if (!validation.isExecutable) {
    throw new Error(
      `[PIPELINE] Staging validation rejected route ${route.id}: ${validation.reason}`
    );
  }

  const stagedPayload: StagedPayload = {
    route,
    pathAddresses: route.pools.map((p) => p.address),
    inputAmountUSD: route.optimalInputUSD,
    expectedProfitUSD: route.netProfitUSD,
    timestamp,
  };

  // ── Stage 4: Dispatch (force non-broadcast unless live armed) ─────────────
  let effectiveMode = mode;
  if (!isLiveTradingEnabled() && mode === 'LIVE') {
    effectiveMode = 'DRY_RUN';
  }
  if (runtime === 'dry-run' && mode === 'LIVE') {
    effectiveMode = 'DRY_RUN';
  }

  const activeDispatcher = dispatcher ?? createDispatcher(effectiveMode);
  const dispatchResult = await activeDispatcher.dispatch(stagedPayload);
  stageResults.push({ stage: 'DISPATCH', passed: dispatchResult.success });

  const executedRoute: ArbitrageRoute = {
    ...route,
    stage: 'ACCOUNTED',
    txHash: dispatchResult.txHash,
    notes:
      dispatchResult.submissionOutcome === 'NOT_BROADCAST' ||
      effectiveMode === 'DRY_RUN' ||
      effectiveMode === 'SIM' ||
      effectiveMode === 'DEV' ||
      effectiveMode === 'TEST'
        ? `[${effectiveMode}] C1-sync archive at ${timestamp}. No chain submission. runtime=${runtime}`
        : `Submitted on Polygon Mainnet. Await receipt verification before realized PnL credit.`,
    transientTrace: computeLegLedger(route),
  };

  const auditLog: SimulationAuditLog = {
    id: `log_${Date.now()}`,
    simulationId: `${
      dispatchResult.submissionOutcome === 'NOT_BROADCAST' || effectiveMode !== 'LIVE'
        ? 'archive'
        : 'live'
    }_${Math.random().toString(36).substring(2, 8)}`,
    routeId: route.id,
    pathString: route.pathString,
    optimalInputUSD: route.optimalInputUSD,
    expectedGrossProfitUSD: route.grossProfitUSD,
    netProfitUSD: route.netProfitUSD,
    status: 'SUCCESS',
    gasUsedGwei: gasGwei + (POLYGON_CHAIN_CONFIG.defaultPriorityFeeGwei ?? 0),
    redisStreamKey: `omega:audit:${
      effectiveMode !== 'LIVE' ? 'archives' : 'submissions'
    }:${Date.now()}-0`,
    sqlSynced: false,
    timestamp,
    isDryRun: effectiveMode !== 'LIVE' || dispatchResult.isDryRun,
  };

  return { dispatchResult, executedRoute, auditLog, stageResults };
}
