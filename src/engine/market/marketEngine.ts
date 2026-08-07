import type {
  ExecutableVenueQuote,
  MarketEngineConfig,
  MarketEngineResult,
  MarketSource,
} from './types';
import { comparableMarketKey, filterEligibleQuotes } from './eligibility';
import { rankDistinctRoutes } from './rankDistinctRoutes';

export function runMarketEngine(
  input: ExecutableVenueQuote[],
  config: MarketEngineConfig,
  source: MarketSource,
): MarketEngineResult {
  const { eligible, rejected } = filterEligibleQuotes(input, config);

  const comparableMarkets = new Set(
    eligible.map(comparableMarketKey),
  ).size;

  const candidates = rankDistinctRoutes(eligible, config);

  return {
    schemaVersion: 'apex.market.snapshot.v1',
    source,
    generatedAtMs: Date.now(),
    latestBlock: config.latestBlock,
    inputRows: input.length,
    eligibleRows: eligible.length,
    rejectedRows: rejected,
    comparableMarkets,
    candidateCount: candidates.length,
    candidates,
  };
}

export * from './types';
export * from './fixedPoint';
export * from './eligibility';
export * from './rankDistinctRoutes';
