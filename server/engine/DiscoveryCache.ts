/**
 * APEX OMEGA: INCREMENTAL DISCOVERY CACHE
 * ========================================
 * Persists discovered pool addresses to disk so that subsequent live-cycle
 * runs only need to scan incremental blocks rather than the full lookback
 * window on every invocation.  This is the primary fix for the 301-second
 * live-cycle timeout: once the initial full scan has populated the cache the
 * subsequent runs skip the expensive eth_getLogs range and only fetch current
 * on-chain state (reserves / liquidity) for already-known pools.
 *
 * Cache file location (in order of precedence):
 *   1. DISCOVERY_CACHE_PATH env var
 *   2. process.cwd()/.apex-discovery-cache.json
 *
 * Cache invalidation:
 *   An entry is fully rescanned when the gap between the stored
 *   lastScannedBlock and the current latest block exceeds MAX_CACHE_AGE_BLOCKS
 *   (default 200000 blocks, ~48 hours on Polygon).  Set via env var
 *   DISCOVERY_CACHE_MAX_AGE_BLOCKS.
 */

import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface DiscoveryCacheEntry {
  /** The highest block number that has been fully scanned for this source. */
  lastScannedBlock: number;
  /**
   * Discovered pool addresses.
   * - V2 / Algebra: checksummed pair/pool addresses.
   * - V3: "address:fee" (e.g. "0xABC...123:500").
   * - Balancer: "poolId:poolAddress" (e.g. "0x...00:0xABC...123").
   */
  pools: string[];
}

export type DiscoveryCacheData = Record<string, DiscoveryCacheEntry>;

// ---------------------------------------------------------------------------
// DiscoveryCache class
// ---------------------------------------------------------------------------

export class DiscoveryCache {
  private data: DiscoveryCacheData;
  private readonly cachePath: string;
  private readonly maxCacheAgeBlocks: number;

  constructor() {
    this.cachePath =
      process.env.DISCOVERY_CACHE_PATH ||
      join(process.cwd(), ".apex-discovery-cache.json");
    this.maxCacheAgeBlocks = Number(
      process.env.DISCOVERY_CACHE_MAX_AGE_BLOCKS || "200000",
    );
    this.data = this._load();
  }

  // -------------------------------------------------------------------------
  // Public API
  // -------------------------------------------------------------------------

  /**
   * Returns the fromBlock to use for an incremental eth_getLogs scan.
   *
   * If no cache entry exists for the key, or the cache is older than
   * maxCacheAgeBlocks, returns `max(0, latestBlock - lookbackBlocks)` (full
   * rescan from the configured lookback window).
   *
   * Otherwise returns `lastScannedBlock + 1` so only new blocks are scanned.
   */
  getIncrementalFromBlock(
    key: string,
    latestBlock: number,
    lookbackBlocks: number,
  ): number {
    const entry = this.data[key];
    if (!entry) return Math.max(0, latestBlock - lookbackBlocks);
    if (latestBlock - entry.lastScannedBlock > this.maxCacheAgeBlocks) {
      return Math.max(0, latestBlock - lookbackBlocks);
    }
    return Math.max(0, entry.lastScannedBlock + 1);
  }

  /**
   * Returns the previously discovered pools for the given cache key.
   * Returns an empty array when the key has no entry.
   */
  getCachedPools(key: string): string[] {
    return this.data[key]?.pools ?? [];
  }

  /**
   * Merges newPools into the existing entry for key and updates
   * lastScannedBlock.  Deduplication is performed on the merged set.
   */
  updateEntry(key: string, lastScannedBlock: number, newPools: string[]): void {
    const existing = this.data[key]?.pools ?? [];
    const merged = new Set<string>([...existing, ...newPools]);
    this.data[key] = {
      lastScannedBlock,
      pools: Array.from(merged),
    };
  }

  /**
   * Persists the current cache state to disk.  Failures are non-fatal; a
   * warning is emitted but execution continues.
   */
  save(): void {
    try {
      mkdirSync(dirname(this.cachePath), { recursive: true });
      writeFileSync(this.cachePath, JSON.stringify(this.data, null, 2), "utf8");
    } catch (err: any) {
      console.warn(
        `DISCOVERY_CACHE_SAVE_WARN|path=${this.cachePath}|error=${err?.message ?? err}`,
      );
    }
  }

  // -------------------------------------------------------------------------
  // Private helpers
  // -------------------------------------------------------------------------

  private _load(): DiscoveryCacheData {
    try {
      const raw = readFileSync(this.cachePath, "utf8");
      return JSON.parse(raw) as DiscoveryCacheData;
    } catch {
      return {};
    }
  }
}
