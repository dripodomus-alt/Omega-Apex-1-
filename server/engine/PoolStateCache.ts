/**
 * APEX OMEGA: NORMALIZED POOL STATE CACHE
 * =======================================
 * Persists executable pool-edge state after discovery has read live chain data.
 * DiscoveryCache answers which pools exist. PoolStateCache answers what each
 * route edge looked like at a specific block after venue-specific normalization.
 */

import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import type { InvariantKind, PoolEdge } from "./routeAdapters.js";
import { getRedisClient } from "../redisLedger.js";

type CacheableEdge = PoolEdge & {
  venueName?: string;
  router?: string;
  tokenInSymbol?: string;
  tokenOutSymbol?: string;
  tokenInPriceUsd?: number;
  tokenOutPriceUsd?: number;
  extra?: {
    v3Fee?: number;
    sqrtPriceX96?: string;
    tick?: number;
    tickSpacing?: number;
    liquidity?: string;
    curveIndexType?: "int128" | "uint256";
    balancerWeightIn?: bigint;
    balancerWeightOut?: bigint;
    balancerSwapFeeBps?: bigint;
  };
};

export type PoolStateSnapshot = {
  cacheKey: string;
  chainId: 137;
  blockNumber: number;
  poolAddress: string;
  poolId?: string;
  dexId: string;
  venueName?: string;
  invariant: InvariantKind;
  tokenIn: string;
  tokenOut: string;
  tokenInSymbol?: string;
  tokenOutSymbol?: string;
  tokenInDecimals: number;
  tokenOutDecimals: number;
  tokenInPriceUsd?: number;
  tokenOutPriceUsd?: number;
  tokenInIndex?: number;
  tokenOutIndex?: number;
  reserveIn: string;
  reserveOut: string;
  tvlUsd: number;
  feeBps: number;
  stateBlock: number;
  quoteAdapter: string;
  calldataAdapter: string;
  executorTarget: string;
  router?: string;
  v3Fee?: number;
  sqrtPriceX96?: string;
  tick?: number;
  tickSpacing?: number;
  liquidity?: string;
  curveIndexType?: "int128" | "uint256";
  balancerWeightIn?: string;
  balancerWeightOut?: string;
  balancerSwapFeeBps?: string;
  lastSeenAt: string;
};

export type PoolStateCacheData = Record<string, PoolStateSnapshot>;

export class PoolStateCache {
  private data: PoolStateCacheData;
  private dirty = false;
  private updated = 0;
  private readonly enabled: boolean;
  private readonly cachePath: string;

  constructor() {
    this.enabled = process.env.POOL_STATE_CACHE_ENABLED !== "false";
    this.cachePath =
      process.env.POOL_STATE_CACHE_PATH ||
      join(process.cwd(), ".cache", "pool-state-cache.json");
    this.data = this.enabled ? this.load() : {};
  }

  upsertEdge(edge: CacheableEdge, blockNumber = edge.stateBlock): void {
    if (!this.enabled) return;
    if (edge.reserveIn <= 0n || edge.reserveOut <= 0n) return;

    const cacheKey = this.cacheKey(edge);
    const snapshot: PoolStateSnapshot = {
      cacheKey,
      chainId: edge.chainId,
      blockNumber,
      poolAddress: edge.poolAddress,
      poolId: edge.poolId,
      dexId: edge.dexId,
      venueName: edge.venueName,
      invariant: edge.invariant,
      tokenIn: edge.tokenIn,
      tokenOut: edge.tokenOut,
      tokenInSymbol: edge.tokenInSymbol,
      tokenOutSymbol: edge.tokenOutSymbol,
      tokenInDecimals: edge.tokenInDecimals,
      tokenOutDecimals: edge.tokenOutDecimals,
      tokenInPriceUsd: edge.tokenInPriceUsd,
      tokenOutPriceUsd: edge.tokenOutPriceUsd,
      tokenInIndex: edge.tokenInIndex,
      tokenOutIndex: edge.tokenOutIndex,
      reserveIn: edge.reserveIn.toString(),
      reserveOut: edge.reserveOut.toString(),
      tvlUsd: Number.isFinite(edge.tvlUsd) ? edge.tvlUsd : 0,
      feeBps: edge.feeBps,
      stateBlock: edge.stateBlock,
      quoteAdapter: edge.quoteAdapter,
      calldataAdapter: edge.calldataAdapter,
      executorTarget: edge.executorTarget,
      router: edge.router,
      v3Fee: edge.extra?.v3Fee,
      sqrtPriceX96: edge.extra?.sqrtPriceX96,
      tick: edge.extra?.tick,
      tickSpacing: edge.extra?.tickSpacing,
      liquidity: edge.extra?.liquidity,
      curveIndexType: edge.extra?.curveIndexType,
      balancerWeightIn: edge.extra?.balancerWeightIn?.toString(),
      balancerWeightOut: edge.extra?.balancerWeightOut?.toString(),
      balancerSwapFeeBps: edge.extra?.balancerSwapFeeBps?.toString(),
      lastSeenAt: new Date().toISOString(),
    };

    this.data[cacheKey] = snapshot;
    this.dirty = true;
    this.updated += 1;
  }

  get(cacheKey: string): PoolStateSnapshot | undefined {
    return this.data[cacheKey];
  }

  hydrateEdge(edge: PoolEdge, maxAgeBlocks: number, currentBlock: number): boolean {
    if (!this.enabled) return false;
    const snapshot = this.data[this.cacheKey(edge)];
    if (!snapshot) return false;
    if (currentBlock - snapshot.stateBlock > maxAgeBlocks) return false;
    edge.reserveIn = BigInt(snapshot.reserveIn);
    edge.reserveOut = BigInt(snapshot.reserveOut);
    edge.tvlUsd = snapshot.tvlUsd;
    edge.stateBlock = snapshot.stateBlock;
    return true;
  }

  save(): void {
    if (!this.enabled || !this.dirty) return;
    try {
      mkdirSync(dirname(this.cachePath), { recursive: true });
      writeFileSync(this.cachePath, JSON.stringify(this.data, null, 2), "utf8");
    } catch (err: any) {
      console.warn(`POOL_STATE_CACHE_SAVE_WARN|path=${this.cachePath}|error=${err?.message ?? err}`);
    }
  }

  async publishToRedis(stateHash: string, latestBlock: number): Promise<void> {
    if (!this.enabled) return;
    const client = await getRedisClient();
    if (!client) return;

    const keyPrefix = process.env.REDIS_KEY_PREFIX || "apex:omega";
    const ttlMs = Number(process.env.REDIS_POOL_STATE_TTL_MS || 120_000);
    const streamMaxLen = Number(process.env.REDIS_STREAM_MAX_LEN || 20_000);
    const now = Date.now();
    const stats = this.stats();
    const summary = {
      chainId: 137,
      latestBlock,
      stateHash,
      cachePath: this.cachePath,
      entries: stats.entries,
      updated: stats.updated,
      latestStateBlock: stats.latestBlock,
      byDex: stats.byDex,
      byInvariant: stats.byInvariant,
      updatedAt: now,
    };

    await client.hSet(`${keyPrefix}:super-state:latest`, {
      payload: JSON.stringify(summary),
      stateHash,
      updatedAt: String(now),
    });
    await client.pExpire(`${keyPrefix}:super-state:latest`, ttlMs * 3);
    await client.xAdd(`${keyPrefix}:super-state:events`, "*", this.redisFields(summary));
    await client.xTrim(`${keyPrefix}:super-state:events`, "MAXLEN", streamMaxLen);

    for (const snapshot of Object.values(this.data)) {
      await client.hSet(`${keyPrefix}:pool-state:${snapshot.cacheKey}`, {
        payload: JSON.stringify(snapshot),
        stateHash,
        updatedAt: String(now),
      });
      await client.pExpire(`${keyPrefix}:pool-state:${snapshot.cacheKey}`, ttlMs * 3);
      await client.zAdd(`${keyPrefix}:pool-state:active`, [{ score: snapshot.stateBlock, value: snapshot.cacheKey }]);
    }
  }

  stats() {
    const byDex: Record<string, number> = {};
    const byInvariant: Record<string, number> = {};
    let latestBlock = 0;
    for (const snapshot of Object.values(this.data)) {
      byDex[snapshot.dexId] = (byDex[snapshot.dexId] || 0) + 1;
      byInvariant[snapshot.invariant] = (byInvariant[snapshot.invariant] || 0) + 1;
      latestBlock = Math.max(latestBlock, snapshot.stateBlock);
    }
    return {
      enabled: this.enabled,
      path: this.cachePath,
      entries: Object.keys(this.data).length,
      updated: this.updated,
      latestBlock,
      byDex,
      byInvariant,
    };
  }

  private cacheKey(edge: Pick<PoolEdge, "dexId" | "poolAddress" | "tokenIn" | "tokenOut" | "invariant" | "feeBps" | "tokenInIndex" | "tokenOutIndex">): string {
    return [
      edge.dexId,
      edge.poolAddress,
      edge.tokenIn,
      edge.tokenOut,
      edge.invariant,
      edge.feeBps,
      edge.tokenInIndex ?? "",
      edge.tokenOutIndex ?? "",
    ].join(":").toLowerCase();
  }

  private load(): PoolStateCacheData {
    try {
      return JSON.parse(readFileSync(this.cachePath, "utf8")) as PoolStateCacheData;
    } catch {
      return {};
    }
  }

  private redisFields(value: Record<string, any>) {
    return Object.fromEntries(
      Object.entries(value).map(([key, nested]) => [
        key,
        nested === undefined || nested === null
          ? ""
          : typeof nested === "string"
            ? nested
            : JSON.stringify(nested),
      ]),
    );
  }
}
