import { describe, expect, it } from 'vitest';
import {
  runMarketEngine,
  usdToX18,
  X18,
  type ExecutableVenueQuote,
  type MarketEngineConfig,
} from './marketEngine';

const config: MarketEngineConfig = {
  chainId: 137,
  minPoolTvlUsdX18: usdToX18(50_000),
  stateTtlBlocks: 4,
  minRawSpreadBps: 1n,
  latestBlock: 100,
  maxCandidates: 100,
};

function quote(
  id: string,
  buy: bigint,
  sell: bigint,
  tvlUsd = 100_000,
  blockNumber = 100,
): ExecutableVenueQuote {
  return {
    schemaVersion: 'apex.market.quote.v1',
    chainId: 137,
    venue: id,
    protocol: 'TEST',
    invariantFamily: 'V2_CPMM',
    destinationId: `dest:${id}`,
    poolId: `pool:${id}`,
    baseAsset: {
      address: '0x0000000000000000000000000000000000000001',
      symbol: 'BASE',
      decimals: 18,
    },
    quoteAsset: {
      address: '0x0000000000000000000000000000000000000002',
      symbol: 'QUOTE',
      decimals: 6,
    },
    quoteBasis: 'EXACT_IN',
    amountInRaw: '1000000',
    buyPriceX18: buy.toString(),
    sellPriceX18: sell.toString(),
    tvlUsdX18: usdToX18(tvlUsd).toString(),
    feeBps: 30,
    executable: true,
    blockNumber,
    observedAtMs: Date.now(),
    stateHash: `state:${id}`,
  };
}

describe('Apex market engine', () => {
  it('rejects TVL below $50K', () => {
    const result = runMarketEngine(
      [
        quote('A', 90n * X18, 100n * X18, 49_999),
        quote('B', 95n * X18, 110n * X18, 100_000),
      ],
      config,
      'SIMULATION',
    );

    expect(result.eligibleRows).toBe(1);
    expect(result.rejectedRows[0]?.reason).toBe('TVL_BELOW_GATE');
  });

  it('rejects stale state', () => {
    const result = runMarketEngine(
      [quote('A', 90n * X18, 100n * X18, 100_000, 95)],
      config,
      'SIMULATION',
    );

    expect(result.eligibleRows).toBe(0);
    expect(result.rejectedRows[0]?.reason).toBe('STALE_STATE');
  });

  it('finds the best distinct route when the absolute buy and sell extrema are the same venue', () => {
    const result = runMarketEngine(
      [
        quote('A', 90n * X18, 110n * X18),
        quote('B', 95n * X18, 108n * X18),
        quote('C', 97n * X18, 107n * X18),
      ],
      config,
      'SIMULATION',
    );

    expect(result.candidateCount).toBeGreaterThan(0);
    expect(result.candidates[0]?.buy.venue).toBe('A');
    expect(result.candidates[0]?.sell.venue).toBe('B');
    expect(result.candidates[0]?.rawSpreadBps).toBe('2000');
  });

  it('never emits a same-pool candidate', () => {
    const result = runMarketEngine(
      [
        quote('A', 90n * X18, 110n * X18),
        quote('B', 95n * X18, 108n * X18),
      ],
      config,
      'SIMULATION',
    );

    for (const candidate of result.candidates) {
      expect(candidate.buy.poolId).not.toBe(candidate.sell.poolId);
      expect(candidate.buy.destinationId).not.toBe(candidate.sell.destinationId);
    }
  });

  it('is deterministic for identical inputs', () => {
    const rows = [
      quote('A', 90n * X18, 110n * X18),
      quote('B', 95n * X18, 108n * X18),
      quote('C', 97n * X18, 107n * X18),
    ];

    const a = runMarketEngine(rows, config, 'SIMULATION');
    const b = runMarketEngine(rows, config, 'SIMULATION');

    expect(
      a.candidates.map((candidate) => candidate.candidateHash),
    ).toEqual(
      b.candidates.map((candidate) => candidate.candidateHash),
    );
  });
});
