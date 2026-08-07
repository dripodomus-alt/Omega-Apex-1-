import { createHash } from 'node:crypto';
import type {
  ExecutableVenueQuote,
  MarketEngineConfig,
  RankedRouteCandidate,
} from './types';
import { asBigInt, spreadBps } from './fixedPoint';
import {
  comparableMarketKey,
  executionDestinationId,
  physicalPoolId,
} from './eligibility';

function sameExecutionDestination(
  a: ExecutableVenueQuote,
  b: ExecutableVenueQuote,
): boolean {
  return executionDestinationId(a) === executionDestinationId(b);
}

function samePhysicalPool(
  a: ExecutableVenueQuote,
  b: ExecutableVenueQuote,
): boolean {
  return physicalPoolId(a) === physicalPoolId(b);
}

function stableCandidateHash(
  comparableKey: string,
  buy: ExecutableVenueQuote,
  sell: ExecutableVenueQuote,
): string {
  const payload = [
    comparableKey,
    executionDestinationId(buy),
    physicalPoolId(buy),
    buy.blockNumber,
    buy.stateHash ?? '',
    executionDestinationId(sell),
    physicalPoolId(sell),
    sell.blockNumber,
    sell.stateHash ?? '',
    buy.amountInRaw,
  ].join('|');

  return `0x${createHash('sha256').update(payload).digest('hex')}`;
}

export function rankDistinctRoutes(
  eligibleQuotes: ExecutableVenueQuote[],
  config: MarketEngineConfig,
): RankedRouteCandidate[] {
  const grouped = new Map<string, ExecutableVenueQuote[]>();

  for (const quote of eligibleQuotes) {
    const key = comparableMarketKey(quote);
    const group = grouped.get(key) ?? [];
    group.push(quote);
    grouped.set(key, group);
  }

  const candidates: RankedRouteCandidate[] = [];

  for (const [key, quotes] of grouped.entries()) {
    const uniqueDestinations = new Set(quotes.map(executionDestinationId));
    if (uniqueDestinations.size < 2) {
      continue;
    }

    // Full Cartesian search over legal distinct destinations.
    // This prevents loss of valid routes when one pool is simultaneously
    // the absolute cheapest buy and absolute highest sell.
    for (const buy of quotes) {
      const buyPrice = asBigInt(buy.buyPriceX18, 'buyPriceX18');

      for (const sell of quotes) {
        if (buy === sell) continue;
        if (sameExecutionDestination(buy, sell)) continue;
        if (samePhysicalPool(buy, sell)) continue;

        const sellPrice = asBigInt(sell.sellPriceX18, 'sellPriceX18');

        if (buyPrice >= sellPrice) continue;

        const edgeBps = spreadBps(buyPrice, sellPrice);
        if (edgeBps < config.minRawSpreadBps) continue;

        candidates.push({
          schemaVersion: 'apex.market.candidate.v1',
          comparableKey: key,
          buy,
          sell,
          buyPriceX18: buyPrice.toString(),
          sellPriceX18: sellPrice.toString(),
          rawSpreadX18: (sellPrice - buyPrice).toString(),
          rawSpreadBps: edgeBps.toString(),
          buyBlock: buy.blockNumber,
          sellBlock: sell.blockNumber,
          candidateHash: stableCandidateHash(key, buy, sell),
          rank: 0,
        });
      }
    }
  }

  candidates.sort((a, b) => {
    const spreadA = BigInt(a.rawSpreadBps);
    const spreadB = BigInt(b.rawSpreadBps);

    if (spreadA !== spreadB) {
      return spreadA > spreadB ? -1 : 1;
    }

    const buyA = BigInt(a.buyPriceX18);
    const buyB = BigInt(b.buyPriceX18);

    if (buyA !== buyB) {
      return buyA < buyB ? -1 : 1;
    }

    return a.candidateHash.localeCompare(b.candidateHash);
  });

  const maxCandidates = Math.max(1, config.maxCandidates ?? 500);

  return candidates
    .slice(0, maxCandidates)
    .map((candidate, index) => ({
      ...candidate,
      rank: index + 1,
    }));
}
