const memoryState = {
  opportunities: [],
  snapshots: [],
  locks: new Map(),
};

let redisClientPromise = null;

function createMemoryOpportunity(entry) {
  return {
    id: entry?.id || `opportunity-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    routeId: entry?.routeId || entry?.id || null,
    status: entry?.status || 'ACTIVE',
    payloadKind: entry?.payloadKind || 'MEMORY_LEDGER',
    createdAt: entry?.createdAt || Date.now(),
    payload: entry?.payload || null,
  };
}

export async function getActiveLedgerCount() {
  return memoryState.opportunities.length;
}

export async function getActiveLedgerOpportunities() {
  return memoryState.opportunities.map((opportunity) => ({ ...opportunity }));
}

export async function getRedisClient() {
  if (redisClientPromise) return redisClientPromise;
  if (!process.env.REDIS_URL) return null;

  redisClientPromise = (async () => {
    try {
      const Redis = (await import('ioredis')).default;
      const client = new Redis(process.env.REDIS_URL, { lazyConnect: true });
      await client.connect();
      return client;
    } catch (error) {
      console.warn('[redisLedger] Redis unavailable, falling back to memory ledger:', error instanceof Error ? error.message : String(error));
      return null;
    }
  })();

  return redisClientPromise;
}

export async function getRedisLedgerStatus() {
  const client = await getRedisClient();
  return {
    enabled: Boolean(process.env.REDIS_URL),
    ok: true,
    mode: client ? 'redis' : 'memory',
    activeOpportunityCount: memoryState.opportunities.length,
  };
}

export async function lockOpportunityForExecution(payload, _ttlMs = 20_000) {
  const routeId = payload?.routeId || payload?.id || payload?.payloadKind || 'default';
  if (memoryState.locks.has(routeId)) {
    return { ok: false, id: routeId, reason: 'lock already held' };
  }

  const entry = createMemoryOpportunity({ ...payload, id: routeId, status: 'LOCKED', payload });
  memoryState.locks.set(routeId, entry);
  memoryState.opportunities.push(entry);
  return { ok: true, id: routeId, reason: 'lock acquired' };
}

export async function publishOpportunitySnapshot(snapshot) {
  const entry = createMemoryOpportunity({ id: `snapshot-${Date.now()}`, status: 'SNAPSHOT', payload: snapshot });
  memoryState.snapshots.push(entry);
  memoryState.opportunities.push(entry);
  return true;
}

export async function releaseOpportunityLock(lockId, status = 'RELEASED', details = {}) {
  if (!lockId) return true;
  const existing = memoryState.locks.get(lockId);
  if (existing) {
    memoryState.locks.delete(lockId);
  }

  memoryState.opportunities.push(createMemoryOpportunity({
    id: `${lockId}:${status}`,
    routeId: lockId,
    status,
    payload: details,
  }));
  return true;
}
