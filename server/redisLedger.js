import Redis from 'ioredis';

// Key constants
const KEYS = {
  OPPORTUNITY_LIST: 'omega:opportunities:active',
  SNAPSHOT_LIST: 'omega:snapshots',
  LOCK_PREFIX: 'omega:lock:',
};

const SNAPSHOT_LIST_MAX_LENGTH = 100;

let redisClient = null;
let redisClientPromise = null;

// In-memory state for fallback when Redis is unavailable
const memoryState = {
  opportunities: new Map(),
  locks: new Map(),
};


/**
 * Initializes and returns a singleton Redis client.
 * If REDIS_URL is not provided or the connection fails, it returns null
 * and the module will fall back to an in-memory ledger.
 */
export async function getRedisClient() {
  if (redisClient) return redisClient;
  if (redisClientPromise) return redisClientPromise;
  if (!process.env.REDIS_URL) {
    console.warn('[redisLedger] REDIS_URL not set. Falling back to in-memory ledger.');
    return null;
  }

  redisClientPromise = (async () => {
    try {
      const client = new Redis(process.env.REDIS_URL, { 
        lazyConnect: true,
        maxRetriesPerRequest: 3,
        connectTimeout: 10000,
      });
      await client.connect();
      console.log('[redisLedger] Successfully connected to Redis.');
      redisClient = client;
      return client;
    } catch (error) {
      console.error('[redisLedger] Redis unavailable, falling back to in-memory ledger:', error instanceof Error ? error.message : String(error));
      redisClient = null; // Ensure client is null on failure
      return null;
    }
  })();

  return redisClientPromise;
}

/**
 * Returns the status of the ledger (Redis or in-memory).
 */
export async function getRedisLedgerStatus() {
  const client = await getRedisClient();
  const mode = client ? 'redis' : 'memory';
  let activeOpportunityCount = 0;

  try {
    if (mode === 'redis') {
      activeOpportunityCount = await client.hlen(KEYS.OPPORTUNITY_LIST);
    } else {
      activeOpportunityCount = memoryState.opportunities.size;
    }
  } catch (e) {
    // Redis might have failed after connect
    console.error(`[redisLedger] Failed to get count from ${mode} ledger:`, e);
  }

  return {
    enabled: Boolean(process.env.REDIS_URL),
    ok: mode === 'redis' ? client.status === 'ready' : true,
    mode,
    activeOpportunityCount,
  };
}

/**
 * Returns the number of currently active opportunities.
 */
export async function getActiveLedgerCount() {
  const status = await getRedisLedgerStatus();
  return status.activeOpportunityCount;
}

/**
 * Publishes a new opportunity snapshot to the ledger.
 * In Redis mode, it pushes to a list and trims it to prevent unbounded growth.
 * @param {object} snapshot - The opportunity snapshot payload.
 */
export async function publishOpportunitySnapshot(snapshot) {
  const client = await getRedisClient();
  const entry = {
    id: `snapshot-${Date.now()}`,
    status: 'SNAPSHOT',
    payload: snapshot,
    createdAt: Date.now(),
  };

  try {
    if (client) {
      await client.lpush(KEYS.SNAPSHOT_LIST, JSON.stringify(entry));
      await client.ltrim(KEYS.SNAPSHOT_LIST, 0, SNAPSHOT_LIST_MAX_LENGTH - 1);
      // Also add to the main opportunity list for real-time processing
      await client.hset(KEYS.OPPORTUNITY_LIST, entry.payload.routeId, JSON.stringify(entry.payload));
    } else {
      // Memory fallback
      memoryState.opportunities.set(entry.payload.routeId, entry.payload);
    }
    return true;
  } catch (e) {
    console.error(`[redisLedger] Failed to publish snapshot to ${client ? 'Redis' : 'memory'}:`, e);
    return false;
  }
}

/**
 * Retrieves all active opportunities from the ledger.
 */
export async function getActiveLedgerOpportunities() {
  const client = await getRedisClient();
  try {
    if (client) {
      const opportunities = await client.hvals(KEYS.OPPORTUNITY_LIST);
      return opportunities.map(JSON.parse);
    } else {
      // Memory fallback
      return Array.from(memoryState.opportunities.values());
    }
  } catch (e) {
    console.error(`[redisLedger] Failed to get opportunities from ${client ? 'Redis' : 'memory'}:`, e);
    return [];
  }
}

/**
 * Attempts to acquire a distributed lock on an opportunity.
 * @param {object} payload - The opportunity payload, must contain a unique `routeId`.
 * @param {number} ttlMs - The lock's time-to-live in milliseconds.
 * @returns {Promise<{ok: boolean, id: string, reason: string}>}
 */
export async function lockOpportunityForExecution(payload, ttlMs = 20_000) {
  const routeId = payload?.routeId || payload?.id;
  if (!routeId) {
    return { ok: false, id: null, reason: 'routeId is missing from payload' };
  }

  const client = await getRedisClient();
  const lockKey = `${KEYS.LOCK_PREFIX}${routeId}`;
  const executorId = `executor-${process.pid}-${Date.now()}`;

  try {
    if (client) {
      const result = await client.set(lockKey, executorId, 'PX', ttlMs, 'NX');
      if (result === 'OK') {
        // Lock acquired, now remove from active opportunities
        await client.hdel(KEYS.OPPORTUNITY_LIST, routeId);
        return { ok: true, id: routeId, reason: 'lock acquired in redis' };
      } else {
        return { ok: false, id: routeId, reason: 'lock already held in redis' };
      }
    } else {
      // Memory fallback
      if (memoryState.locks.has(routeId)) {
        return { ok: false, id: routeId, reason: 'lock already held' };
      }
      memoryState.locks.set(routeId, { executorId, expiresAt: Date.now() + ttlMs });
      memoryState.opportunities.delete(routeId);
      // cleanup expired locks
      setTimeout(() => {
        const lock = memoryState.locks.get(routeId);
        if(lock && lock.executorId === executorId) {
          memoryState.locks.delete(routeId);
        }
      }, ttlMs);
      return { ok: true, id: routeId, reason: 'lock acquired' };
    }
  } catch (e) {
    console.error(`[redisLedger] Error during lock acquisition for ${routeId}:`, e);
    return { ok: false, id: routeId, reason: `internal error: ${e.message}` };
  }
}

/**
 * Releases a previously acquired lock.
 * @param {string} lockId - The `routeId` of the opportunity to release.
 * @param {string} [status] - Optional terminal status for audit visibility.
 * @param {object} [metadata] - Optional status metadata to archive with the release.
 */
export async function releaseOpportunityLock(lockId, status, metadata) {
  if (!lockId) return true;

  const client = await getRedisClient();
  const lockKey = `${KEYS.LOCK_PREFIX}${lockId}`;
  const releaseEntry = status
    ? {
        id: `release-${lockId}-${Date.now()}`,
        routeId: lockId,
        status,
        metadata: metadata ?? {},
        createdAt: Date.now(),
      }
    : null;
  
  try {
    if (client) {
      await client.del(lockKey);
      if (releaseEntry) {
        await client.lpush(KEYS.SNAPSHOT_LIST, JSON.stringify(releaseEntry));
        await client.ltrim(KEYS.SNAPSHOT_LIST, 0, SNAPSHOT_LIST_MAX_LENGTH - 1);
      }
    } else {
      // Memory fallback
      memoryState.locks.delete(lockId);
      if (releaseEntry) {
        memoryState.opportunities.set(releaseEntry.id, releaseEntry);
      }
    }
    return true;
  } catch(e) {
    console.error(`[redisLedger] Failed to release lock for ${lockId}:`, e);
    return false;
  }
}
