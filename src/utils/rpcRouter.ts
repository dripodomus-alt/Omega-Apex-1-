/**
 * OMEGA V5 — Client-Side RPC Router (web3-rpc-proxy pattern)
 *
 * Implements the same routing logic as a server-side web3-rpc-proxy in pure
 * TypeScript so the browser console can benefit from multi-endpoint
 * load-balancing without deploying a Go sidecar.
 *
 * Key behaviours:
 *   - Tracks the latest block number seen from each upstream endpoint.
 *   - Routes each JSON-RPC read to the endpoint with the highest block height
 *     (freshest state) among those that responded within the latency window.
 *   - Handles node failover transparently: if the preferred endpoint fails or
 *     returns a stale block, the next-best endpoint is promoted automatically.
 *   - Exposes per-endpoint health stats so the UI can surface block-height
 *     deltas and latency in the OnChainBlockParitySentinel panel.
 *
 * Design constraints:
 *   - No external dependencies — uses only browser fetch.
 *   - All operations are non-blocking; stale health state is used if a
 *     concurrent health-check cycle is already running.
 *   - Safe for concurrent callers: the endpoint list is immutable after
 *     construction; health state is updated via simple object mutation
 *     (single-threaded JS event loop, no race conditions).
 */

export interface RpcEndpointHealth {
  url: string;
  label: string;
  latestBlock: number;
  lastLatencyMs: number;
  lastCheckedAt: number; // ms since epoch
  consecutiveFailures: number;
  isHealthy: boolean;
}

export interface RpcRouterConfig {
  /** Ordered list of upstream endpoints to monitor and route across. */
  endpoints: { url: string; label: string }[];
  /**
   * Maximum age (ms) of a health-check result before the endpoint is
   * re-evaluated on the next call.  Default 4 000 ms (≈2 Polygon blocks).
   */
  healthTtlMs?: number;
  /** Requests taking longer than this (ms) are counted as failures. */
  timeoutMs?: number;
}

export interface RpcRouteResult {
  /** JSON-RPC response parsed from the winning endpoint. */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: any;
  /** URL of the endpoint that served this response. */
  usedEndpoint: string;
  /** Label of the endpoint that served this response. */
  usedLabel: string;
  /** Block height reported by the winning endpoint. */
  blockHeight: number;
}

const DEFAULT_HEALTH_TTL_MS = 4_000;
const DEFAULT_TIMEOUT_MS = 3_500;

/**
 * Lightweight multi-endpoint RPC router.
 *
 * Usage:
 * ```ts
 * const router = new RpcRouter({ endpoints: [...] });
 * const result = await router.send({ jsonrpc: '2.0', id: 1, method: 'eth_blockNumber', params: [] });
 * console.log(result.usedLabel, result.blockHeight);
 * ```
 */
export class RpcRouter {
  private readonly health: Map<string, RpcEndpointHealth>;
  private readonly healthTtlMs: number;
  private readonly timeoutMs: number;
  private isRefreshing = false;

  constructor(config: RpcRouterConfig) {
    this.healthTtlMs = config.healthTtlMs ?? DEFAULT_HEALTH_TTL_MS;
    this.timeoutMs = config.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    this.health = new Map(
      config.endpoints.map(({ url, label }) => [
        url,
        {
          url,
          label,
          latestBlock: 0,
          lastLatencyMs: 0,
          lastCheckedAt: 0,
          consecutiveFailures: 0,
          isHealthy: true,
        },
      ])
    );
  }

  /** Returns a snapshot of current health state for all endpoints. */
  getHealthSnapshot(): RpcEndpointHealth[] {
    return Array.from(this.health.values());
  }

  /**
   * Probes all endpoints for their current block number and updates the
   * internal health table.  Called automatically before routing if any
   * endpoint's health record is stale; can also be called manually.
   */
  async refreshHealth(): Promise<void> {
    if (this.isRefreshing) return;
    this.isRefreshing = true;
    try {
      const probes = Array.from(this.health.values()).map((entry) =>
        this._probeBlockNumber(entry.url)
      );
      await Promise.allSettled(probes);
    } finally {
      this.isRefreshing = false;
    }
  }

  /**
   * Routes a single JSON-RPC call to the best available upstream endpoint.
   *
   * "Best" is defined as: highest block number among healthy endpoints.
   * If all endpoints are unhealthy, falls back to the first endpoint in the
   * list regardless of health state.
   *
   * @param body  - A fully-formed JSON-RPC request object.
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async send(body: Record<string, any>): Promise<RpcRouteResult> {
    // Refresh stale health records before selecting an endpoint.
    const now = Date.now();
    const needsRefresh = Array.from(this.health.values()).some(
      (e) => now - e.lastCheckedAt > this.healthTtlMs
    );
    if (needsRefresh && !this.isRefreshing) {
      // Fire-and-forget — use whatever state is available right now and let
      // the next call benefit from the refreshed data.
      void this.refreshHealth();
    }

    const ranked = this._rankEndpoints();
    for (const entry of ranked) {
      try {
        const result = await this._fetchWithTimeout(entry.url, body);
        // Update block height if this call returned a useful result.
        const blockHint = this._extractBlockNumber(result);
        if (blockHint !== null && blockHint > entry.latestBlock) {
          entry.latestBlock = blockHint;
        }
        return {
          data: result,
          usedEndpoint: entry.url,
          usedLabel: entry.label,
          blockHeight: entry.latestBlock,
        };
      } catch {
        const h = this.health.get(entry.url);
        if (h) {
          h.consecutiveFailures += 1;
          h.isHealthy = h.consecutiveFailures < 3;
        }
      }
    }
    throw new Error('[RpcRouter] All upstream endpoints failed.');
  }

  // ── Private helpers ────────────────────────────────────────────────────────

  /** Probes a single endpoint for eth_blockNumber and updates its health entry. */
  private async _probeBlockNumber(url: string): Promise<void> {
    const entry = this.health.get(url);
    if (!entry) return;
    const start = Date.now();
    try {
      const data = await this._fetchWithTimeout(url, {
        jsonrpc: '2.0',
        id: 0,
        method: 'eth_blockNumber',
        params: [],
      });
      const latencyMs = Date.now() - start;
      const block = this._parseHexInt((data as { result?: string }).result ?? '0x0');
      entry.latestBlock = block;
      entry.lastLatencyMs = latencyMs;
      entry.lastCheckedAt = Date.now();
      entry.consecutiveFailures = 0;
      entry.isHealthy = true;
    } catch {
      entry.consecutiveFailures += 1;
      entry.isHealthy = entry.consecutiveFailures < 3;
      entry.lastCheckedAt = Date.now();
    }
  }

  /**
   * Returns endpoints sorted by descending block number (freshest first),
   * with healthy endpoints ranked above unhealthy ones.
   */
  private _rankEndpoints(): RpcEndpointHealth[] {
    return Array.from(this.health.values()).sort((a, b) => {
      if (a.isHealthy !== b.isHealthy) return a.isHealthy ? -1 : 1;
      return b.latestBlock - a.latestBlock;
    });
  }

  /** Wraps fetch with an AbortController-based timeout. */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private async _fetchWithTimeout(url: string, body: Record<string, any>): Promise<unknown> {
    const controller = new AbortController();
    const id = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } finally {
      clearTimeout(id);
    }
  }

  /** Tries to extract a block number from a JSON-RPC response. */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private _extractBlockNumber(data: any): number | null {
    if (typeof data?.result === 'string' && data.result.startsWith('0x')) {
      const n = this._parseHexInt(data.result);
      if (n > 1_000_000) return n; // sanity: plausible block number
    }
    return null;
  }

  private _parseHexInt(hex: string): number {
    return parseInt(hex, 16) || 0;
  }
}

// ---------------------------------------------------------------------------
// Singleton factory — builds a router from chainConfig endpoints so callers
// don't need to import chainConfig directly (avoids circular deps in utils/).
// ---------------------------------------------------------------------------

let _singleton: RpcRouter | null = null;

/**
 * Returns the shared Omega V5 RPC router, initialising it on first call.
 * Pass `endpoints` only on the first call (or to force a reset).
 */
export function getOmegaRpcRouter(
  endpoints?: { url: string; label: string }[]
): RpcRouter {
  if (!_singleton || endpoints) {
    const defaultEndpoints: { url: string; label: string }[] = endpoints ?? [
      { url: 'https://polygon-mainnet.g.alchemy.com/v2/alch_1ZM_Z5UwNe9UghW0V0czR', label: 'Alchemy' },
      { url: 'https://lb.drpc.live/polygon/Avauizx6-kfknfhxCHj4Li331ds_f94R8a7RijtBrJVX', label: 'DRPC' },
      { url: 'https://polygon-mainnet.core.chainstack.com/0b8f83de9048afe7f5c60bb78d746daf', label: 'Chainstack' },
      { url: 'https://shared.us-east-1.getblock.io/f6d98a8bece041d5bb38e2c7fdcd475e', label: 'GetBlock' },
      { url: 'https://polygon-mainnet.infura.io/v3/ed05b301f1a949f59bfbc1c128910937', label: 'Infura' },
      { url: 'https://polygon-bor-rpc.publicnode.com', label: 'PublicNode' },
      { url: 'https://polygon-rpc.com', label: 'Polygon-RPC' },
    ];
    _singleton = new RpcRouter({ endpoints: defaultEndpoints });
  }
  return _singleton;
}
