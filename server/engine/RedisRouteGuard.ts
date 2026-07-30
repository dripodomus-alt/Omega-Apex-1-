/**
 * APEX OMEGA: REDIS ROUTE GUARD
 * ==============================
 * Distributed lock + in-flight tracking that prevents multiple PM2 worker
 * processes or overlapping async execution cycles from racing to execute
 * the same arbitrage route.
 *
 * Three protected scenarios
 * ─────────────────────────
 * 1. PM2 cluster / multiple processes
 *    Each process calls tryAcquireLock() before broadcasting a C1/C2 payload.
 *    Only the first caller gets the lock; others receive `false` and skip.
 *
 * 2. Async execution dispatch (fire-and-forget)
 *    The lock is held from broadcast time until the settlement is confirmed or
 *    the TTL expires, so the next discovery cycle cannot re-queue the same
 *    route while its transaction is still pending in the mempool.
 *
 * 3. Parallelized token-pair discovery
 *    SystemBootstrap.runMultipleCycles() calls isLocked() before promoting a
 *    discovered route to "selected", filtering out any route already claimed
 *    by another worker.
 *
 * Graceful no-op mode
 * ───────────────────
 * When REDIS_URL is not set (single-process deployments), the guard
 * initialises in no-op mode: every method succeeds immediately without
 * contacting Redis, so existing behaviour is fully preserved.
 */

import Redis from "ioredis";

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

export interface RouteStep {
  venue: string;
  tokenIn: string;
  tokenOut: string;
}

export interface ArbitrageRouteSummary {
  tokenIn: string;
  tokenOut: string;
  legs: RouteStep[];
}

// ─────────────────────────────────────────────────────────────────────────────
// Key builders
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Deterministic Redis key for a C1/C2 execution payload.
 * Keyed on the flashloan asset address + the ordered sequence of
 * (venue, tokenIn, tokenOut) for every execution step.
 */
export function routeKeyFromC1Payload(
  flashloanAsset: string,
  steps: RouteStep[]
): string {
  const asset = flashloanAsset.toLowerCase();
  const stepParts = steps.map(
    (s) =>
      `${(s.venue ?? "").toLowerCase()}:${(s.tokenIn ?? "").toLowerCase()}:${(s.tokenOut ?? "").toLowerCase()}`
  );
  return `arb:lock:${asset}:${stepParts.join(":")}`;
}

/**
 * Deterministic Redis key for a discovered ArbitrageRoute.
 * Keyed on tokenIn/tokenOut + ordered leg (venueId, tokenIn, tokenOut).
 */
export function routeKeyFromArbitrageRoute(
  route: ArbitrageRouteSummary
): string {
  const parts = route.legs.map(
    (l) =>
      `${(l.venue ?? "").toLowerCase()}:${(l.tokenIn ?? "").toLowerCase()}:${(l.tokenOut ?? "").toLowerCase()}`
  );
  return `arb:lock:${route.tokenIn.toLowerCase()}:${route.tokenOut.toLowerCase()}:${parts.join(":")}`;
}

/**
 * Deterministic Redis key for a C2 settlement keyed on its c1InternalId.
 * Prevents a second process from issuing duplicate C2 for the same C1.
 */
export function routeKeyFromC1InternalId(c1InternalId: string): string {
  return `arb:c2:lock:${c1InternalId.toLowerCase()}`;
}

/**
 * Deterministic Redis key for a liquidation.
 * Keyed on (targetContract, user, debtAsset, collateralAsset).
 */
export function routeKeyFromLiquidation(
  targetContract: string,
  user: string,
  debtAsset: string,
  collateralAsset: string
): string {
  return [
    "arb:liq:lock",
    targetContract.toLowerCase(),
    user.toLowerCase(),
    debtAsset.toLowerCase(),
    collateralAsset.toLowerCase(),
  ].join(":");
}

// ─────────────────────────────────────────────────────────────────────────────
// RedisRouteGuard class
// ─────────────────────────────────────────────────────────────────────────────

export class RedisRouteGuard {
  private redis: Redis | null = null;
  private readonly noop: boolean;

  /**
   * @param redisUrl - Full Redis connection URL (e.g. redis://:password@host:6379).
   *                   Pass undefined / empty string to run in no-op mode.
   * @param defaultLockTtlSeconds - Default lock TTL; caller may override per-call.
   */
  constructor(
    redisUrl: string | undefined,
    private readonly defaultLockTtlSeconds: number = 30
  ) {
    if (!redisUrl) {
      this.noop = true;
      console.info(
        "[RedisRouteGuard] REDIS_URL not set – running in no-op mode (single-process safe)"
      );
      return;
    }

    this.noop = false;
    this.redis = new Redis(redisUrl, {
      enableOfflineQueue: false,
      connectTimeout: 3000,
      maxRetriesPerRequest: 2,
      lazyConnect: false,
    });

    this.redis.on("connect", () =>
      console.info("[RedisRouteGuard] Connected to Redis")
    );
    this.redis.on("error", (err) =>
      console.error("[RedisRouteGuard] Redis error:", err.message)
    );
  }

  // ── Core lock primitives ────────────────────────────────────────────────────

  /**
   * Attempt to acquire an exclusive lock for `key`.
   *
   * Uses Redis SET NX EX (atomic set-if-not-exists with expiry) so that only
   * one process wins when multiple workers race simultaneously.
   *
   * @returns `true` if the lock was acquired, `false` if already held.
   */
  async tryAcquireLock(
    key: string,
    ttlSeconds: number = this.defaultLockTtlSeconds
  ): Promise<boolean> {
    if (this.noop || !this.redis) return true;
    try {
      const result = await this.redis.set(
        key,
        "1", // value is arbitrary; lock semantics rely on key existence only
        "EX",
        ttlSeconds,
        "NX"
      );
      return result === "OK";
    } catch (err: any) {
      console.warn(
        `[RedisRouteGuard] tryAcquireLock failed for ${key}: ${err?.message}`
      );
      // Fail-open: allow execution rather than blocking the engine on Redis errors
      return true;
    }
  }

  /**
   * Release a lock acquired by this process.
   * Safe to call even if the key has already expired.
   */
  async releaseLock(key: string): Promise<void> {
    if (this.noop || !this.redis) return;
    try {
      await this.redis.del(key);
    } catch (err: any) {
      console.warn(
        `[RedisRouteGuard] releaseLock failed for ${key}: ${err?.message}`
      );
    }
  }

  /**
   * Returns `true` if a lock for `key` is currently held by any process.
   * Used by the discovery engine to filter out already-claimed routes
   * before computing them as candidates.
   */
  async isLocked(key: string): Promise<boolean> {
    if (this.noop || !this.redis) return false;
    try {
      const exists = await this.redis.exists(key);
      return exists === 1;
    } catch (err: any) {
      console.warn(
        `[RedisRouteGuard] isLocked check failed for ${key}: ${err?.message}`
      );
      // Fail-open: do not suppress routes on Redis read errors
      return false;
    }
  }

  // ── Convenience helpers ─────────────────────────────────────────────────────

  /**
   * Acquire a C1 execution lock from a payload's execution context steps.
   * Steps should be the `context.steps` array from the C1 broadcast request.
   */
  async acquireC1Lock(
    flashloanAsset: string,
    steps: RouteStep[],
    ttlSeconds?: number
  ): Promise<{ acquired: boolean; key: string }> {
    const key = routeKeyFromC1Payload(flashloanAsset, steps);
    const acquired = await this.tryAcquireLock(key, ttlSeconds);
    return { acquired, key };
  }

  /**
   * Acquire a C2 settlement lock from a c1InternalId.
   * Prevents duplicate C2 broadcasts for the same C1 across worker processes.
   */
  async acquireC2Lock(
    c1InternalId: string,
    ttlSeconds?: number
  ): Promise<{ acquired: boolean; key: string }> {
    const key = routeKeyFromC1InternalId(c1InternalId);
    const acquired = await this.tryAcquireLock(key, ttlSeconds);
    return { acquired, key };
  }

  /**
   * Acquire a liquidation lock.
   * Prevents two workers from liquidating the same unhealthy position.
   */
  async acquireLiquidationLock(
    targetContract: string,
    user: string,
    debtAsset: string,
    collateralAsset: string,
    ttlSeconds?: number
  ): Promise<{ acquired: boolean; key: string }> {
    const key = routeKeyFromLiquidation(
      targetContract,
      user,
      debtAsset,
      collateralAsset
    );
    const acquired = await this.tryAcquireLock(key, ttlSeconds);
    return { acquired, key };
  }

  // ── Lifecycle ────────────────────────────────────────────────────────────────

  /** Returns true if running in no-op (Redis-less) mode. */
  isNoOp(): boolean {
    return this.noop;
  }

  /** Gracefully disconnect from Redis. Call during server shutdown. */
  async close(): Promise<void> {
    if (this.redis) {
      await this.redis.quit().catch(() => this.redis?.disconnect());
      this.redis = null;
    }
  }
}

export default RedisRouteGuard;
