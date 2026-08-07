import type {
  ExecutableVenueQuote,
  MarketEngineConfig,
  QuoteRejectReason,
  QuoteRejection,
} from './types';
import { asBigInt } from './fixedPoint';

export interface EligibilityResult {
  eligible: ExecutableVenueQuote[];
  rejected: QuoteRejection[];
}

export function normalizeAddress(value: string): string {
  return value.trim().toLowerCase();
}

export function executionDestinationId(quote: ExecutableVenueQuote): string {
  return quote.destinationId.trim().toLowerCase();
}

export function physicalPoolId(quote: ExecutableVenueQuote): string {
  return quote.poolId.trim().toLowerCase();
}

export function comparableMarketKey(quote: ExecutableVenueQuote): string {
  return [
    quote.chainId,
    normalizeAddress(quote.baseAsset.address),
    normalizeAddress(quote.quoteAsset.address),
    quote.amountInRaw,
    quote.quoteBasis,
  ].join('|');
}

function reject(
  quote: ExecutableVenueQuote,
  reason: QuoteRejectReason,
  detail: string,
): QuoteRejection {
  return {
    reason,
    destinationId: quote.destinationId,
    poolId: quote.poolId,
    detail,
  };
}

export function validateQuote(
  quote: ExecutableVenueQuote,
  config: MarketEngineConfig,
): QuoteRejection | null {
  if (quote.chainId !== config.chainId) {
    return reject(quote, 'WRONG_CHAIN', `expected=${config.chainId} actual=${quote.chainId}`);
  }

  if (!quote.executable) {
    return reject(quote, 'NOT_EXECUTABLE', 'quote is not marked executable');
  }

  if (
    !quote.baseAsset.address.trim() ||
    !quote.quoteAsset.address.trim() ||
    quote.baseAsset.decimals < 0 ||
    quote.quoteAsset.decimals < 0
  ) {
    return reject(quote, 'INVALID_ASSET', 'missing asset address or invalid decimals');
  }

  let tvlUsdX18: bigint;
  let buy: bigint;
  let sell: bigint;
  let amountIn: bigint;

  try {
    tvlUsdX18 = asBigInt(quote.tvlUsdX18, 'tvlUsdX18');
    buy = asBigInt(quote.buyPriceX18, 'buyPriceX18');
    sell = asBigInt(quote.sellPriceX18, 'sellPriceX18');
    amountIn = asBigInt(quote.amountInRaw, 'amountInRaw');
  } catch (error) {
    return reject(
      quote,
      'INVALID_PRICE',
      error instanceof Error ? error.message : String(error),
    );
  }

  if (tvlUsdX18 < config.minPoolTvlUsdX18) {
    return reject(
      quote,
      'TVL_BELOW_GATE',
      `tvlX18=${tvlUsdX18} minX18=${config.minPoolTvlUsdX18}`,
    );
  }

  if (
    !Number.isInteger(quote.blockNumber) ||
    quote.blockNumber <= 0 ||
    quote.blockNumber > config.latestBlock + 1 ||
    config.latestBlock - quote.blockNumber > config.stateTtlBlocks
  ) {
    return reject(
      quote,
      'STALE_STATE',
      `quoteBlock=${quote.blockNumber} latestBlock=${config.latestBlock} ttlBlocks=${config.stateTtlBlocks}`,
    );
  }

  if (buy <= 0n || sell <= 0n) {
    return reject(quote, 'INVALID_PRICE', 'buy and sell prices must be > 0');
  }

  if (amountIn <= 0n) {
    return reject(quote, 'INVALID_AMOUNT', 'amountInRaw must be > 0');
  }

  if (!executionDestinationId(quote)) {
    return reject(quote, 'INVALID_DESTINATION', 'destinationId is empty');
  }

  if (!physicalPoolId(quote)) {
    return reject(quote, 'INVALID_POOL', 'poolId is empty');
  }

  if (!Number.isFinite(quote.feeBps) || quote.feeBps < 0 || quote.feeBps > 10_000) {
    return reject(quote, 'INVALID_FEE', `invalid feeBps=${quote.feeBps}`);
  }

  return null;
}

export function filterEligibleQuotes(
  quotes: ExecutableVenueQuote[],
  config: MarketEngineConfig,
): EligibilityResult {
  const eligible: ExecutableVenueQuote[] = [];
  const rejected: QuoteRejection[] = [];

  for (const quote of quotes) {
    const failure = validateQuote(quote, config);
    if (failure) {
      rejected.push(failure);
      continue;
    }
    eligible.push(quote);
  }

  return { eligible, rejected };
}
