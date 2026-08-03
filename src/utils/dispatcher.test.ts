import { describe, it, expect, vi, beforeEach } from 'vitest';
import { DryRunDispatcher, LiveDispatcher, ModeTerminal, createDispatcher } from './dispatcher';
import type { StagedPayload } from './dispatcher';
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
    slippageToleranceBps: 50,
    isSelfFundingRisk: false,
    ...overrides,
  };
}

function makeStagedPayload(overrides: Partial<StagedPayload> = {}): StagedPayload {
  const route = makeRoute();
  return {
    route,
    pathAddresses: route.pools.map((p) => p.address),
    inputAmountUSD: route.optimalInputUSD,
    expectedProfitUSD: route.netProfitUSD,
    timestamp: new Date().toISOString(),
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// DryRunDispatcher
// ---------------------------------------------------------------------------

describe('DryRunDispatcher', () => {
  it('sets isDryRun to true', async () => {
    const dispatcher = new DryRunDispatcher();
    const result = await dispatcher.dispatch(makeStagedPayload());
    expect(result.isDryRun).toBe(true);
  });

  it('sets mode to DRY_RUN', async () => {
    const dispatcher = new DryRunDispatcher();
    const result = await dispatcher.dispatch(makeStagedPayload());
    expect(result.mode).toBe('DRY_RUN');
  });

  it('reports success without any network call', async () => {
    const dispatcher = new DryRunDispatcher();
    const result = await dispatcher.dispatch(makeStagedPayload());
    expect(result.success).toBe(true);
  });

  it('does not fabricate a txHash', async () => {
    const dispatcher = new DryRunDispatcher();
    const result = await dispatcher.dispatch(makeStagedPayload());
    expect(result.txHash).toBeUndefined();
  });

  it('does not set a polygonscanUrl (no on-chain submission)', async () => {
    const dispatcher = new DryRunDispatcher();
    const result = await dispatcher.dispatch(makeStagedPayload());
    expect(result.polygonscanUrl).toBeUndefined();
  });

  it('sets submissionOutcome to NOT_BROADCAST', async () => {
    const dispatcher = new DryRunDispatcher();
    const result = await dispatcher.dispatch(makeStagedPayload());
    expect(result.submissionOutcome).toBe('NOT_BROADCAST');
  });

  it('returns an approvedEnvelopeHash', async () => {
    const dispatcher = new DryRunDispatcher();
    const result = await dispatcher.dispatch(makeStagedPayload());
    expect(result.approvedEnvelopeHash).toMatch(/^0x[0-9a-f]{8}$/);
  });

  it('emits [MODE TERMINAL] marker lines in logs', async () => {
    const dispatcher = new DryRunDispatcher();
    const result = await dispatcher.dispatch(makeStagedPayload());
    expect(result.logs.length).toBeGreaterThan(0);
    expect(result.logs.every((l) => l.startsWith('[MODE TERMINAL]'))).toBe(true);
  });

  it('echoes the route id from the payload', async () => {
    const dispatcher = new DryRunDispatcher();
    const payload = makeStagedPayload();
    const result = await dispatcher.dispatch(payload);
    expect(result.routeId).toBe(payload.route.id);
  });

  it('echoes the net profit from the route', async () => {
    const dispatcher = new DryRunDispatcher();
    const payload = makeStagedPayload();
    const result = await dispatcher.dispatch(payload);
    expect(result.netProfitUSD).toBe(payload.route.netProfitUSD);
  });
});

// ---------------------------------------------------------------------------
// LiveDispatcher
// ---------------------------------------------------------------------------

describe('LiveDispatcher', () => {
  beforeEach(() => {
    vi.mock('./ethersBroadcaster', () => ({
      broadcastEthersOnChainTransaction: vi.fn().mockResolvedValue({
        success: true,
        txHash: '0x' + 'a'.repeat(64),
        confirmationLogs: ['[BROADCAST SUCCESS] mock'],
        polygonscanUrl: 'https://polygonscan.com/tx/0x' + 'a'.repeat(64),
      }),
    }));
  });

  it('sets isDryRun to false', async () => {
    const dispatcher = new LiveDispatcher();
    const result = await dispatcher.dispatch(makeStagedPayload());
    expect(result.isDryRun).toBe(false);
  });

  it('sets mode to LIVE', async () => {
    const dispatcher = new LiveDispatcher();
    const result = await dispatcher.dispatch(makeStagedPayload());
    expect(result.mode).toBe('LIVE');
  });
});

// ---------------------------------------------------------------------------
// createDispatcher factory
// ---------------------------------------------------------------------------

describe('createDispatcher', () => {
  it('returns the canonical terminal for DRY_RUN mode', () => {
    const dispatcher = createDispatcher('DRY_RUN');
    expect(dispatcher).toBeInstanceOf(ModeTerminal);
  });

  it('returns the canonical terminal for LIVE mode', () => {
    const dispatcher = createDispatcher('LIVE');
    expect(dispatcher).toBeInstanceOf(ModeTerminal);
  });

  it('DRY_RUN dispatcher result has isDryRun true without network calls', async () => {
    const dispatcher = createDispatcher('DRY_RUN');
    const result = await dispatcher.dispatch(makeStagedPayload());
    expect(result.isDryRun).toBe(true);
    expect(result.mode).toBe('DRY_RUN');
  });
});

