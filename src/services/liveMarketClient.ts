import type {
  MarketEngineResult,
} from '../engine/market/types';

const DEFAULT_MARKET_API_BASE = 'http://localhost:8797';

function marketApiBase(): string {
  const configured = import.meta.env.VITE_APEX_MARKET_API_BASE as string | undefined;
  return (configured?.trim() || DEFAULT_MARKET_API_BASE).replace(/\/+$/, '');
}

export async function fetchMarketSnapshot(
  signal?: AbortSignal,
): Promise<MarketEngineResult> {
  const response = await fetch(
    `${marketApiBase()}/v1/snapshot`,
    {
      method: 'GET',
      headers: {
        Accept: 'application/json',
      },
      cache: 'no-store',
      signal,
    },
  );

  if (!response.ok) {
    const body = await response.text();
    throw new Error(
      `Market snapshot failed: HTTP ${response.status} ${body}`.trim(),
    );
  }

  const payload = await response.json() as Partial<MarketEngineResult>;

  if (
    payload.schemaVersion !== 'apex.market.snapshot.v1' ||
    !Array.isArray(payload.candidates) ||
    typeof payload.latestBlock !== 'number'
  ) {
    throw new Error('Invalid market snapshot payload');
  }

  return payload as MarketEngineResult;
}
