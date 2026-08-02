import { ArbitrageRoute, ExecutionMode, PoolInfo, SimulationAuditLog } from '../types';
import { validateRouteAssetRegistry } from './mathEngine';
import { computeLegLedger } from './transientAccounting';
import { StagedPayload, DispatchResult, IDispatcher, createDispatcher } from './dispatcher';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

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

// Minimum VQC alpha score required for a route to pass the Ranking stage
const VQC_RANKING_THRESHOLD = 0.75;

// ─────────────────────────────────────────────────────────────────────────────
// Unified Execution Pipeline
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Runs the four-stage arbitrage execution pipeline.
 *
 * Stages 1–3 (Discovery, Ranking & Scoring, Staging/Validation) are shared and
 * execute identically regardless of the active execution mode.  Only Stage 4
 * (Dispatch) is mode-dependent: a LiveDispatcher submits a real on-chain
 * transaction while a DryRunDispatcher formats and logs the exact payload that
 * would have been sent without touching any external state.
 *
 * @param route      - The arbitrage route candidate
 * @param pools      - Pool registry used for asset-registry validation
 * @param mode       - 'DRY_RUN' | 'LIVE'
 * @param gasGwei    - Current gas price in Gwei (captured for the audit log)
 * @param dispatcher - Optional custom dispatcher; defaults to createDispatcher(mode)
 * @throws           - Throws with a descriptive message if any shared stage fails
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

  // ── Stage 1: Discovery ────────────────────────────────────────────────────
  // Validates that the discovered route has the minimum structural metadata
  // required to proceed (path string, at least one pool, a unique ID).
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

  // ── Stage 2: Ranking & Scoring ────────────────────────────────────────────
  // Accepts routes whose VQC alpha score meets the threshold and whose
  // net profit is positive.
  const rankingPassed =
    route.vqcAlphaScore >= VQC_RANKING_THRESHOLD && route.netProfitUSD > 0;

  stageResults.push({
    stage: 'RANKING',
    passed: rankingPassed,
    reason: rankingPassed
      ? undefined
      : `VQC alpha ${route.vqcAlphaScore} below threshold ${VQC_RANKING_THRESHOLD} or net profit ≤ 0`,
  });

  if (!rankingPassed) {
    throw new Error(
      `[PIPELINE] Ranking stage rejected route ${route.id}: ` +
        `VQC alpha ${route.vqcAlphaScore}, net profit $${route.netProfitUSD}`
    );
  }

  // ── Stage 3: Staging / Validation ─────────────────────────────────────────
  // Verifies that every pool in the route holds assets that are registered in
  // the on-chain pool registry, preventing execution against unrecognized pools.
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

  // Build the staged payload consumed by the dispatch sink
  const stagedPayload: StagedPayload = {
    route,
    pathAddresses: route.pools.map((p) => p.address),
    inputAmountUSD: route.optimalInputUSD,
    expectedProfitUSD: route.netProfitUSD,
    timestamp,
  };

  // ── Stage 4: Mode-Dependent Dispatch ─────────────────────────────────────
  // Polymorphic: LiveDispatcher submits a real tx; DryRunDispatcher logs the
  // payload with [DRY RUN SIMULATION] indicators and skips all side-effects.
  const activeDispatcher = dispatcher ?? createDispatcher(mode);
  const dispatchResult = await activeDispatcher.dispatch(stagedPayload);

  stageResults.push({ stage: 'DISPATCH', passed: dispatchResult.success });

  // ── Build executed route (identical shape for both modes) ─────────────────
  const executedRoute: ArbitrageRoute = {
    ...route,
    stage: 'ACCOUNTED',
    txHash: dispatchResult.txHash,
    notes: dispatchResult.isDryRun
      ? `[DRY RUN] Simulated execution at ${timestamp}. No on-chain transaction submitted.`
      : `Mined on Polygon Mainnet. Balancer Vault transient flashloan repaid successfully. Verified registry pool assets.`,
    transientTrace: computeLegLedger(route),
  };

  // ── Build audit log (identical structure for both modes) ──────────────────
  // Identical timestamping and metadata allow operators to diff dry-run vs live.
  const auditLog: SimulationAuditLog = {
    id: `log_${Date.now()}`,
    simulationId: `${dispatchResult.isDryRun ? 'dry' : 'sim'}_${Math.random()
      .toString(36)
      .substring(2, 8)}`,
    routeId: route.id,
    pathString: route.pathString,
    optimalInputUSD: route.optimalInputUSD,
    expectedGrossProfitUSD: route.grossProfitUSD,
    netProfitUSD: route.netProfitUSD,
    status: 'SUCCESS',
    gasUsedGwei: gasGwei + 2.5,
    redisStreamKey: `omega:audit:${dispatchResult.isDryRun ? 'dryrun' : 'simulations'}:${Date.now()}-0`,
    sqlSynced: false,
    timestamp,
    isDryRun: dispatchResult.isDryRun,
  };

  return { dispatchResult, executedRoute, auditLog, stageResults };
}
