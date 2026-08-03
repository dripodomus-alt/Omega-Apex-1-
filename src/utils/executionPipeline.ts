import { ArbitrageRoute, ExecutionMode, PoolInfo, SimulationAuditLog } from '../types';
import { validateRouteAssetRegistry } from './mathEngine';
import { computeLegLedger } from './transientAccounting';
import { StagedPayload, DispatchResult, IDispatcher, createDispatcher } from './dispatcher';

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

const VQC_RANKING_THRESHOLD = 0.75;

export async function runExecutionPipeline(
  route: ArbitrageRoute,
  pools: PoolInfo[],
  mode: ExecutionMode,
  gasGwei: number,
  dispatcher?: IDispatcher
): Promise<PipelineRunResult> {
  const stageResults: PipelineStageResult[] = [];
  const timestamp = new Date().toISOString().replace('T', ' ').substring(0, 19) + ' UTC';

  const discoveryPassed = Boolean(route.id) && Boolean(route.pathString) && route.pools.length > 0;
  stageResults.push({
    stage: 'DISCOVERY',
    passed: discoveryPassed,
    reason: discoveryPassed ? undefined : 'Route is missing required path or pool data',
  });
  if (!discoveryPassed) {
    throw new Error(`[PIPELINE] Discovery stage failed for route ${route.id}: missing path or pool data`);
  }

  const rankingPassed = route.vqcAlphaScore >= VQC_RANKING_THRESHOLD && route.netProfitUSD > 0;
  stageResults.push({
    stage: 'RANKING',
    passed: rankingPassed,
    reason: rankingPassed
      ? undefined
      : `VQC alpha ${route.vqcAlphaScore} below threshold ${VQC_RANKING_THRESHOLD} or net profit <= 0`,
  });
  if (!rankingPassed) {
    throw new Error(
      `[PIPELINE] Ranking stage rejected route ${route.id}: ` +
        `VQC alpha ${route.vqcAlphaScore}, net profit $${route.netProfitUSD}`
    );
  }

  const validation = validateRouteAssetRegistry(route, pools);
  stageResults.push({
    stage: 'STAGING',
    passed: validation.isExecutable,
    reason: validation.isExecutable ? undefined : validation.reason,
  });
  if (!validation.isExecutable) {
    throw new Error(`[PIPELINE] Staging validation rejected route ${route.id}: ${validation.reason}`);
  }

  const stagedPayload: StagedPayload = {
    route,
    pathAddresses: route.pools.map((p) => p.address),
    inputAmountUSD: route.optimalInputUSD,
    expectedProfitUSD: route.netProfitUSD,
    timestamp,
  };

  const activeDispatcher = dispatcher ?? createDispatcher(mode);
  const dispatchResult = await activeDispatcher.dispatch(stagedPayload);
  stageResults.push({ stage: 'DISPATCH', passed: dispatchResult.success });

  const executedRoute: ArbitrageRoute = {
    ...route,
    stage: 'ACCOUNTED',
    txHash: dispatchResult.txHash,
    notes: dispatchResult.submissionOutcome === 'NOT_BROADCAST'
      ? `[${mode}] Approved envelope archived at ${timestamp}. No signature or chain submission.`
      : `Submitted on Polygon Mainnet. Await receipt verification before realized PnL credit.`,
    transientTrace: computeLegLedger(route),
  };

  const auditLog: SimulationAuditLog = {
    id: `log_${Date.now()}`,
    simulationId: `${dispatchResult.submissionOutcome === 'NOT_BROADCAST' ? 'archive' : 'live'}_${Math.random()
      .toString(36)
      .substring(2, 8)}`,
    routeId: route.id,
    pathString: route.pathString,
    optimalInputUSD: route.optimalInputUSD,
    expectedGrossProfitUSD: route.grossProfitUSD,
    netProfitUSD: route.netProfitUSD,
    status: 'SUCCESS',
    gasUsedGwei: gasGwei + 2.5,
    redisStreamKey: `omega:audit:${dispatchResult.submissionOutcome === 'NOT_BROADCAST' ? 'archives' : 'submissions'}:${Date.now()}-0`,
    sqlSynced: false,
    timestamp,
    isDryRun: dispatchResult.isDryRun,
  };

  return { dispatchResult, executedRoute, auditLog, stageResults };
}