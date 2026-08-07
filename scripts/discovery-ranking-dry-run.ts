import {
  runMarketEngine,
  usdToX18,
  X18,
  type ExecutableVenueQuote,
  type MarketEngineConfig,
} from '../src/engine/market/marketEngine';

const LATEST_BLOCK = Number(process.env.APEX_DRY_RUN_BLOCK ?? 100);
const MIN_TVL_USD = Number(process.env.MIN_POOL_TVL_USD ?? 50_000);

const config: MarketEngineConfig = {
  chainId: 137,
  minPoolTvlUsdX18: usdToX18(MIN_TVL_USD),
  stateTtlBlocks: Number(process.env.MARKET_STATE_TTL_BLOCKS ?? 4),
  minRawSpreadBps: BigInt(process.env.MIN_RAW_SPREAD_BPS ?? '1'),
  latestBlock: LATEST_BLOCK,
  maxCandidates: 100,
};

function q(
  venue: string,
  poolId: string,
  buyPrice: bigint,
  sellPrice: bigint,
  tvlUsd: number,
  blockNumber = LATEST_BLOCK,
): ExecutableVenueQuote {
  return {
    schemaVersion: 'apex.market.quote.v1',
    chainId: 137,
    venue,
    protocol: 'DRY_RUN',
    invariantFamily: 'V2_CPMM',
    destinationId: `137:${venue}:${poolId}`,
    poolId,
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
    amountInRaw: '1000000000000000000',
    buyPriceX18: buyPrice.toString(),
    sellPriceX18: sellPrice.toString(),
    tvlUsdX18: usdToX18(tvlUsd).toString(),
    feeBps: 30,
    executable: true,
    blockNumber,
    observedAtMs: Date.now(),
    stateHash: `state:${venue}:${poolId}:${blockNumber}`,
  };
}

const rows: ExecutableVenueQuote[] = [
  // Adversarial case: A is both cheapest buy and highest sell.
  // Correct engine must reject A->A but preserve A->B.
  q('POOL_A', '0xpoolA', 90n * X18, 110n * X18, 200_000),
  q('POOL_B', '0xpoolB', 95n * X18, 108n * X18, 180_000),
  q('POOL_C', '0xpoolC', 97n * X18, 107n * X18, 160_000),

  // TVL rejection proof.
  q('POOL_LOW_TVL', '0xpoolLow', 80n * X18, 120n * X18, 49_999),

  // Staleness rejection proof.
  q('POOL_STALE', '0xpoolStale', 70n * X18, 130n * X18, 200_000, LATEST_BLOCK - 10),
];

const result = runMarketEngine(rows, config, 'SIMULATION');

console.log('APEX_OMEGA_DISCOVERY_RANKING_DRY_RUN_V2');
console.log(JSON.stringify({
  latestBlock: result.latestBlock,
  inputRows: result.inputRows,
  eligibleRows: result.eligibleRows,
  rejectedRows: result.rejectedRows.length,
  comparableMarkets: result.comparableMarkets,
  candidateCount: result.candidateCount,
}, null, 2));

console.log('\nREJECTIONS');
for (const rejection of result.rejectedRows) {
  console.log(JSON.stringify(rejection));
}

console.log('\nRANKED_CANDIDATES');
for (const candidate of result.candidates) {
  console.log(JSON.stringify({
    rank: candidate.rank,
    buyVenue: candidate.buy.venue,
    sellVenue: candidate.sell.venue,
    buyPool: candidate.buy.poolId,
    sellPool: candidate.sell.poolId,
    buyPriceX18: candidate.buyPriceX18,
    sellPriceX18: candidate.sellPriceX18,
    rawSpreadBps: candidate.rawSpreadBps,
    candidateHash: candidate.candidateHash,
  }));
}

const best = result.candidates[0];

if (!best) {
  throw new Error('Expected at least one ranked route');
}

if (best.buy.venue !== 'POOL_A' || best.sell.venue !== 'POOL_B') {
  throw new Error(
    `Distinct-route regression: expected POOL_A -> POOL_B, received ${best.buy.venue} -> ${best.sell.venue}`,
  );
}

if (best.rawSpreadBps !== '2000') {
  throw new Error(
    `Spread regression: expected 2000 bps, received ${best.rawSpreadBps}`,
  );
}

if (
  result.rejectedRows.some((row) => row.reason === 'TVL_BELOW_GATE') === false
) {
  throw new Error('TVL gate regression');
}

if (
  result.rejectedRows.some((row) => row.reason === 'STALE_STATE') === false
) {
  throw new Error('staleness gate regression');
}

console.log('\nRESULT=PASS');
