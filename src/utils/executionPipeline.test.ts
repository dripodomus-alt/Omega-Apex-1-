import { describe, it, expect, vi } from 'vitest';
import { runExecutionPipeline } from './executionPipeline';
import { DryRunDispatcher } from './dispatcher';
import type { ArbitrageRoute, PoolInfo } from '../types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makePool(overrides: Partial<PoolInfo> = {}): PoolInfo {
  return {
    id: 'pool-1',
    name: 'TestPool',
    protocol: 'V2_CPMM',
    category: 'SWAPPABLE_EXECUTION',
    address: '0xabc',
    token0: { symbol: 'WMATIC / WPOL', decimals: 18, address: '0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270' },
    token1: { symbol: 'USDC.e', decimals: 6, address: '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174' },
    feeBps: 30,
    reserve0USD: 500000,
    reserve1USD: 500000,
    isFundingPool: false,
    status: 'ACTIVE',
    ...overrides,
  };
}

function makeRoute(overrides: Partial<ArbitrageRoute> = {}): ArbitrageRoute {
  return {
    id: 'route-test-1',
    pathString: 'WMATIC→USDC.e→WETH',
    length: 2,
    pools: [makePool()],
    expectedYieldUSD: 0,
    vqcAlphaScore: 0.88,
    vqcWinProbability: 0.82,
    optimalInputUSD: 50000,
    optimalInputWei: '50000000000000000000000',
    grossProfitUSD: 310,
    estimatedGasUSD: 0.55,
    netProfitUSD: 309.45,
    stage: 'SIMULATED',
    timestamp: new Date().toISOString(),
    slippageToleranceBps: 40,
    isSelfFundingRisk: false,
    ...overrides,
  };
}

// Shared dry-run dispatcher used across tests — no network calls
const dryRunDispatcher = new DryRunDispatcher();

// ---------------------------------------------------------------------------
// Unified pipeline contract: shared stages 1–3
// ---------------------------------------------------------------------------

describe('runExecutionPipeline — unified shared stages', () => {
  it('returns four stage results in order: DISCOVERY, RANKING, STAGING, DISPATCH', async () => {
    const result = await runExecutionPipeline(
      makeRoute(),
      [makePool()],
      'DRY_RUN',
      38,
      dryRunDispatcher
    );
    const names = result.stageResults.map((s) => s.stage);
    expect(names).toEqual(['DISCOVERY', 'RANKING', 'STAGING', 'DISPATCH']);
  });

  it('all four stages pass for a well-formed route in DRY_RUN mode', async () => {
    const result = await runExecutionPipeline(
      makeRoute(),
      [makePool()],
      'DRY_RUN',
      38,
      dryRunDispatcher
    );
    expect(result.stageResults.every((s) => s.passed)).toBe(true);
  });

  it('stages 1–3 produce identical pass/fail results regardless of mode', async () => {
    // Supply the same custom DryRunDispatcher for both invocations so no real
    // network call is made, while the mode label differs.
    const dryResult = await runExecutionPipeline(
      makeRoute(),
      [makePool()],
      'DRY_RUN',
      38,
      dryRunDispatcher
    );
    const liveResult = await runExecutionPipeline(
      makeRoute(),
      [makePool()],
      'LIVE',
      38,
      dryRunDispatcher  // same dispatcher to isolate stage 1-3 comparison
    );

    const sharedDry = dryResult.stageResults.slice(0, 3);
    const sharedLive = liveResult.stageResults.slice(0, 3);
    expect(sharedDry.map((s) => s.passed)).toEqual(sharedLive.map((s) => s.passed));
    expect(sharedDry.map((s) => s.stage)).toEqual(sharedLive.map((s) => s.stage));
  });
});

// ---------------------------------------------------------------------------
// No synthetic opportunity generation
// ---------------------------------------------------------------------------

describe('runExecutionPipeline — no synthetic opportunity paths', () => {
  it('requires an externally-supplied route — pipeline has no internal route generator', () => {
    // Verify the public signature: the first parameter is a required ArbitrageRoute.
    // A pipeline with an internal synthetic branch would not need this parameter.
    expect(runExecutionPipeline).toHaveLength(5); // (route, pools, mode, gasGwei, dispatcher?)
  });

  it('output route preserves the supplied route id unchanged', async () => {
    const route = makeRoute({ id: 'live-discovered-route-99' });
    const result = await runExecutionPipeline(route, [], 'DRY_RUN', 38, dryRunDispatcher);
    expect(result.executedRoute.id).toBe('live-discovered-route-99');
  });

  it('output route preserves the supplied pathString unchanged', async () => {
    const route = makeRoute({ pathString: 'WETH→WMATIC→USDC.e→WETH' });
    const result = await runExecutionPipeline(route, [], 'DRY_RUN', 38, dryRunDispatcher);
    expect(result.executedRoute.pathString).toBe('WETH→WMATIC→USDC.e→WETH');
  });

  it('output route preserves the supplied profit figures unchanged', async () => {
    const route = makeRoute({ grossProfitUSD: 412.5, netProfitUSD: 411.9 });
    const result = await runExecutionPipeline(route, [], 'DRY_RUN', 38, dryRunDispatcher);
    expect(result.executedRoute.grossProfitUSD).toBe(412.5);
    expect(result.executedRoute.netProfitUSD).toBe(411.9);
  });
});

// ---------------------------------------------------------------------------
// DRY_RUN dispatch: transaction broadcasting is disabled
// ---------------------------------------------------------------------------

describe('runExecutionPipeline — DRY_RUN has tx broadcasting disabled', () => {
  it('dispatch result has isDryRun true in DRY_RUN mode', async () => {
    const result = await runExecutionPipeline(
      makeRoute(),
      [],
      'DRY_RUN',
      38,
      dryRunDispatcher
    );
    expect(result.dispatchResult.isDryRun).toBe(true);
  });

  it('audit log isDryRun flag is true in DRY_RUN mode', async () => {
    const result = await runExecutionPipeline(
      makeRoute(),
      [],
      'DRY_RUN',
      38,
      dryRunDispatcher
    );
    expect(result.auditLog.isDryRun).toBe(true);
  });

  it('executed route notes mention approved envelope was archived with no submission', async () => {
    const result = await runExecutionPipeline(
      makeRoute(),
      [],
      'DRY_RUN',
      38,
      dryRunDispatcher
    );
    expect(result.executedRoute.notes).toContain('Approved envelope archived');
    expect(result.executedRoute.notes).toContain('No signature or chain submission');
  });

  it('dispatch result has isDryRun false when a LiveDispatcher is supplied', async () => {
    // Use a custom dispatcher stub that mimics LiveDispatcher output without
    // making a real network call.
    const liveStub = {
      dispatch: vi.fn().mockResolvedValue({
        success: true,
        txHash: '0x' + 'b'.repeat(64),
        approvedEnvelopeHash: '0xaaaaaaaa',
        submissionOutcome: 'BROADCAST_SUBMITTED' as const,
        isDryRun: false,
        mode: 'LIVE' as const,
        logs: [],
        routeId: 'route-test-1',
        netProfitUSD: 309.45,
        timestamp: new Date().toISOString(),
        polygonscanUrl: 'https://polygonscan.com/tx/0x' + 'b'.repeat(64),
      }),
    };
    const result = await runExecutionPipeline(makeRoute(), [], 'LIVE', 38, liveStub);
    expect(result.dispatchResult.isDryRun).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Pipeline stage failures
// ---------------------------------------------------------------------------

describe('runExecutionPipeline — Discovery stage rejects malformed routes', () => {
  it('throws when route id is empty', async () => {
    await expect(
      runExecutionPipeline(makeRoute({ id: '' }), [], 'DRY_RUN', 38, dryRunDispatcher)
    ).rejects.toThrow(/Discovery stage failed/);
  });

  it('throws when pathString is empty', async () => {
    await expect(
      runExecutionPipeline(makeRoute({ pathString: '' }), [], 'DRY_RUN', 38, dryRunDispatcher)
    ).rejects.toThrow(/Discovery stage failed/);
  });

  it('throws when route has no pools', async () => {
    await expect(
      runExecutionPipeline(makeRoute({ pools: [] }), [], 'DRY_RUN', 38, dryRunDispatcher)
    ).rejects.toThrow(/Discovery stage failed/);
  });
});

describe('runExecutionPipeline — Ranking stage rejects unprofitable routes', () => {
  it('throws when VQC alpha score is below threshold (0.75)', async () => {
    await expect(
      runExecutionPipeline(
        makeRoute({ vqcAlphaScore: 0.74 }),
        [],
        'DRY_RUN',
        38,
        dryRunDispatcher
      )
    ).rejects.toThrow(/Ranking stage rejected/);
  });

  it('throws when net profit is zero', async () => {
    await expect(
      runExecutionPipeline(
        makeRoute({ netProfitUSD: 0 }),
        [],
        'DRY_RUN',
        38,
        dryRunDispatcher
      )
    ).rejects.toThrow(/Ranking stage rejected/);
  });

  it('throws when net profit is negative', async () => {
    await expect(
      runExecutionPipeline(
        makeRoute({ netProfitUSD: -5 }),
        [],
        'DRY_RUN',
        38,
        dryRunDispatcher
      )
    ).rejects.toThrow(/Ranking stage rejected/);
  });
});

// ---------------------------------------------------------------------------
// Output shape
// ---------------------------------------------------------------------------

describe('runExecutionPipeline — output shape', () => {
  it('executed route stage is ACCOUNTED', async () => {
    const result = await runExecutionPipeline(
      makeRoute(),
      [],
      'DRY_RUN',
      38,
      dryRunDispatcher
    );
    expect(result.executedRoute.stage).toBe('ACCOUNTED');
  });

  it('audit log has a non-empty id and simulationId', async () => {
    const result = await runExecutionPipeline(
      makeRoute(),
      [],
      'DRY_RUN',
      38,
      dryRunDispatcher
    );
    expect(result.auditLog.id).toBeTruthy();
    expect(result.auditLog.simulationId).toBeTruthy();
  });

  it('audit log simulationId starts with "archive_" in DRY_RUN mode', async () => {
    const result = await runExecutionPipeline(
      makeRoute(),
      [],
      'DRY_RUN',
      38,
      dryRunDispatcher
    );
    expect(result.auditLog.simulationId).toMatch(/^archive_/);
  });

  it('audit log status is SUCCESS for a passing route', async () => {
    const result = await runExecutionPipeline(
      makeRoute(),
      [],
      'DRY_RUN',
      38,
      dryRunDispatcher
    );
    expect(result.auditLog.status).toBe('SUCCESS');
  });
});

