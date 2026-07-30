import { createClient, type RedisClientType } from "redis";
import { createHash } from "node:crypto";
import { deflateSync } from "node:zlib";
import { pack } from "msgpackr";

const DEFAULT_REDIS_URL = "redis://127.0.0.1:6379";
const KEY_PREFIX = process.env.REDIS_KEY_PREFIX || "apex:omega";
const SNAPSHOT_TTL_MS = Number(process.env.REDIS_OPPORTUNITY_TTL_MS || 120_000);
const EXECUTION_LOCK_TTL_MS = Number(process.env.REDIS_EXECUTION_LOCK_TTL_MS || 45_000);
const CONNECT_TIMEOUT_MS = Number(process.env.REDIS_CONNECT_TIMEOUT_MS || 600);
const STREAM_MAX_LEN = Number(process.env.REDIS_STREAM_MAX_LEN || 20_000);
const LANE_BATCH_WINDOW_MS = Number(process.env.REDIS_LANE_BATCH_WINDOW_MS || 50);
const LANE_BATCH_MAX_SIZE = Number(process.env.REDIS_LANE_BATCH_MAX_SIZE || 1_000);
const OPPORTUNITY_THRESHOLD_BPS = Number(process.env.REDIS_OPPORTUNITY_THRESHOLD_BPS || 1);
const ENABLE_KEYSPACE_NOTIFICATIONS = process.env.REDIS_ENABLE_KEYSPACE_NOTIFICATIONS === "true";

type LedgerPayload = Record<string, any>;

let clientPromise: Promise<RedisClientType | null> | null = null;
let lastError: string | null = null;
let laneBuffer: LedgerPayload[] = [];
let laneFlushTimer: NodeJS.Timeout | null = null;

function redisEnabled() {
  return process.env.REDIS_ENABLED !== "false";
}

function redisUrl() {
  return process.env.REDIS_URL || process.env.APEX_REDIS_URL || DEFAULT_REDIS_URL;
}

function redisSocketPath() {
  return process.env.REDIS_SOCKET_PATH || process.env.APEX_REDIS_SOCKET_PATH || "";
}

function timeout<T>(promise: Promise<T>, ms: number, label: string): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`${label}_TIMEOUT_${ms}MS`)), ms);
    promise.then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (error) => {
        clearTimeout(timer);
        reject(error);
      },
    );
  });
}

function normalizeForJson(value: any): any {
  if (typeof value === "bigint") return value.toString();
  if (Array.isArray(value)) return value.map(normalizeForJson);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, nested]) => [key, normalizeForJson(nested)]),
    );
  }
  return value;
}

function json(value: any) {
  return JSON.stringify(normalizeForJson(value));
}

function redisStreamFields(value: LedgerPayload) {
  return Object.fromEntries(
    Object.entries(normalizeForJson(value)).map(([key, nested]) => [
      key,
      nested === undefined || nested === null
        ? ""
        : typeof nested === "string"
          ? nested
          : JSON.stringify(nested),
    ]),
  );
}

function parseRedisJson(raw: unknown) {
  return typeof raw === "string" && raw ? JSON.parse(raw) : null;
}

function hashPayload(value: any) {
  return createHash("sha256").update(json(value)).digest("hex");
}

function opportunityKey(id: string) {
  return `${KEY_PREFIX}:opportunity:${id}`;
}

function lockKey(id: string) {
  return `${KEY_PREFIX}:opportunity-lock:${id}`;
}

function activeSetKey() {
  return `${KEY_PREFIX}:opportunities:active`;
}

function laneSetKey() {
  return `${KEY_PREFIX}:lanes:events`;
}

function laneBatchStreamKey() {
  return `${KEY_PREFIX}:lanes:batches`;
}

function opportunityThresholdStreamKey() {
  return `${KEY_PREFIX}:opportunities:thresholds`;
}

function opportunityThresholdKey(id: string) {
  return `${KEY_PREFIX}:opportunity-threshold:${id}`;
}

export function opportunityId(payload: LedgerPayload) {
  const routeFingerprint = [
    payload.routeId,
    payload.payloadKind,
    payload.pair,
    payload.path,
    payload.venues,
    payload.flashloanAsset,
    payload.flashloanProvider,
    payload.pools,
  ].filter((item) => item !== undefined && item !== null && item !== "").join("|");
  return hashPayload(routeFingerprint || payload);
}

export async function getRedisClient(): Promise<RedisClientType | null> {
  if (!redisEnabled()) return null;
  if (clientPromise) return clientPromise;

  clientPromise = (async () => {
    try {
      const client = createClient({
        ...(redisSocketPath()
          ? {}
          : { url: redisUrl() }),
        socket: {
          ...(redisSocketPath() ? { path: redisSocketPath() } : {}),
          connectTimeout: CONNECT_TIMEOUT_MS,
          reconnectStrategy: false,
        },
      });
      client.on("error", (error) => {
        lastError = error.message;
      });
      await timeout(client.connect(), CONNECT_TIMEOUT_MS + 250, "REDIS_CONNECT");
      if (ENABLE_KEYSPACE_NOTIFICATIONS) {
        await client.configSet("notify-keyspace-events", "Kh").catch((error: any) => {
          lastError = `KEYSPACE_NOTIFY_UNAVAILABLE:${error?.message || error}`;
        });
      }
      lastError = null;
      return client as RedisClientType;
    } catch (error: any) {
      lastError = error?.message || "Redis connection failed";
      clientPromise = null;
      return null;
    }
  })();

  return clientPromise;
}

export function getRedisLedgerStatus() {
  return {
    enabled: redisEnabled(),
    connected: Boolean(clientPromise) && !lastError,
    url: redisSocketPath() ? `unix://${redisSocketPath()}` : redisUrl().replace(/\/\/.*@/, "//***@"),
    transport: redisSocketPath() ? "unix_socket" : "tcp",
    keyPrefix: KEY_PREFIX,
    streams: {
      laneEvents: laneSetKey(),
      laneBatches: laneBatchStreamKey(),
      opportunityThresholds: opportunityThresholdStreamKey(),
      batchWindowMs: LANE_BATCH_WINDOW_MS,
      batchMaxSize: LANE_BATCH_MAX_SIZE,
      thresholdBps: OPPORTUNITY_THRESHOLD_BPS,
      codec: "msgpack+deflate",
      streamMaxLen: STREAM_MAX_LEN,
    },
    lastError,
  };
}

function thresholdMoved(previous: any, next: any) {
  if (!previous) return true;
  const previousProfit = Number(previous.netProfitUsd ?? previous.profit_usd ?? 0);
  const nextProfit = Number(next.netProfitUsd ?? next.profit_usd ?? 0);
  const previousAmountOut = Number(previous.amountOut ?? 0);
  const nextAmountOut = Number(next.amountOut ?? 0);
  const previousRank = Number(previous.rank ?? 0);
  const nextRank = Number(next.rank ?? 0);
  if (previousRank && nextRank && previousRank !== nextRank) return true;
  const movedBps = (oldValue: number, newValue: number) => {
    if (!Number.isFinite(oldValue) || !Number.isFinite(newValue)) return 0;
    const basis = Math.max(Math.abs(oldValue), 1);
    return Math.abs(newValue - oldValue) * 10_000 / basis;
  };
  return movedBps(previousProfit, nextProfit) >= OPPORTUNITY_THRESHOLD_BPS ||
    movedBps(previousAmountOut, nextAmountOut) >= OPPORTUNITY_THRESHOLD_BPS;
}

async function emitOpportunityThreshold(client: RedisClientType, id: string, previous: any, next: any, source: string) {
  const event = normalizeForJson({
    redisId: id,
    routeId: next.routeId,
    source,
    path: next.path,
    venues: next.venues,
    rank: next.rank,
    status: next.status,
    netProfitUsd: next.netProfitUsd ?? next.profit_usd,
    previousNetProfitUsd: previous?.netProfitUsd ?? previous?.profit_usd,
    previousRank: previous?.rank,
    at: Date.now(),
  });
  await client.hSet(opportunityThresholdKey(id), { payload: json(event), updatedAt: String(Date.now()) });
  await client.xAdd(opportunityThresholdStreamKey(), "*", redisStreamFields(event));
  await client.xTrim(opportunityThresholdStreamKey(), "MAXLEN", STREAM_MAX_LEN);
}

export async function publishOpportunitySnapshot(
  opportunities: LedgerPayload[],
  source: string,
  ttlMs = SNAPSHOT_TTL_MS,
) {
  const client = await getRedisClient();
  const now = Date.now();
  const currentIds = new Set<string>();
  if (!client) {
    return opportunities.map((payload) => ({ ...payload, redisId: opportunityId(payload), redisStatus: "MEMORY_ONLY" }));
  }

  const visible: LedgerPayload[] = [];
  for (const payload of opportunities) {
    const id = opportunityId(payload);
    currentIds.add(id);
    const isLocked = await client.exists(lockKey(id));
    const existingRaw = await client.hGet(opportunityKey(id), "payload");
    const existing = parseRedisJson(existingRaw);
    const existingStatus = existing?.redisStatus || existing?.executionStatus;
    const preserve =
      isLocked ||
      ["LOCKED_FOR_EXECUTION", "C1_PENDING", "C2_PENDING", "EXECUTING"].includes(existingStatus);
    const record = preserve
      ? { ...existing, redisPreservedDuringScan: true, lastSeenAt: now }
      : {
          ...payload,
          redisId: id,
          redisStatus: "SCANNED_READY",
          source,
          firstSeenAt: existing?.firstSeenAt || now,
          lastSeenAt: now,
          expiresAt: now + ttlMs,
        };
    await client.hSet(opportunityKey(id), { payload: json(record), updatedAt: String(now) });
    await client.pExpire(opportunityKey(id), ttlMs * 3);
    await client.zAdd(activeSetKey(), [{ score: now, value: id }]);
    if (!preserve && thresholdMoved(existing, record)) {
      await emitOpportunityThreshold(client, id, existing, record, source).catch(() => undefined);
    }
    visible.push(record);
  }

  const activeIds = await client.zRange(activeSetKey(), 0, -1);
  for (const id of activeIds) {
    if (currentIds.has(id)) continue;
    const isLocked = await client.exists(lockKey(id));
    const existingRaw = await client.hGet(opportunityKey(id), "payload");
    const existing = parseRedisJson(existingRaw);
    const existingStatus = existing?.redisStatus || existing?.executionStatus;
    const preserve =
      isLocked ||
      ["LOCKED_FOR_EXECUTION", "C1_PENDING", "C2_PENDING", "EXECUTING"].includes(existingStatus);
    if (preserve || existing?.source !== source) continue;
    await client.zRem(activeSetKey(), id);
    await client.del(opportunityKey(id));
  }

  const staleCutoff = now - ttlMs;
  await client.zRemRangeByScore(activeSetKey(), 0, staleCutoff);
  return visible;
}

export async function getActiveLedgerOpportunities(limit = 100) {
  const client = await getRedisClient();
  if (!client) return null;
  const ids = await client.zRange(activeSetKey(), -limit, -1, { REV: true });
  const rows: LedgerPayload[] = [];
  for (const id of ids) {
    const raw = await client.hGet(opportunityKey(id), "payload");
    if (!raw) continue;
    const parsed = parseRedisJson(raw);
    if (parsed) rows.push(parsed);
  }
  return rows.sort((left, right) => {
    const leftRank = Number(left.rank ?? Number.MAX_SAFE_INTEGER);
    const rightRank = Number(right.rank ?? Number.MAX_SAFE_INTEGER);
    if (leftRank !== rightRank) return leftRank - rightRank;
    return Number(right.profit_usd ?? right.netProfitUsd ?? Number.NEGATIVE_INFINITY) -
      Number(left.profit_usd ?? left.netProfitUsd ?? Number.NEGATIVE_INFINITY);
  });
}

export async function getActiveLedgerCount() {
  const client = await getRedisClient();
  if (!client) return null;
  return await client.zCard(activeSetKey());
}

export async function lockOpportunityForExecution(payload: LedgerPayload, ttlMs = EXECUTION_LOCK_TTL_MS) {
  const client = await getRedisClient();
  const id = opportunityId(payload);
  if (!client) return { ok: true, redis: false, id, reason: "REDIS_UNAVAILABLE_MEMORY_LOCK_ONLY" };
  const lockValue = `${process.pid}:${Date.now()}`;
  const result = await client.set(lockKey(id), lockValue, { NX: true, PX: ttlMs });
  if (result !== "OK") return { ok: false, redis: true, id, reason: "ALREADY_LOCKED_OR_IN_FLIGHT" };
  const record = {
    ...payload,
    redisId: id,
    redisStatus: "LOCKED_FOR_EXECUTION",
    lockedAt: Date.now(),
    lockTtlMs: ttlMs,
  };
  await client.hSet(opportunityKey(id), { payload: json(record), updatedAt: String(Date.now()) });
  await client.zAdd(activeSetKey(), [{ score: Date.now(), value: id }]);
  return { ok: true, redis: true, id, reason: "LOCK_ACQUIRED" };
}

export async function releaseOpportunityLock(id: string, status: string, patch: LedgerPayload = {}) {
  const client = await getRedisClient();
  if (!client) return;
  const raw = await client.hGet(opportunityKey(id), "payload");
  const existing = parseRedisJson(raw) || {};
  const record = {
    ...existing,
    ...patch,
    redisStatus: status,
    releasedAt: Date.now(),
  };
  await client.hSet(opportunityKey(id), { payload: json(record), updatedAt: String(Date.now()) });
  await client.del(lockKey(id));
}

export async function recordLaneEvent(event: LedgerPayload) {
  const normalized = normalizeForJson(event);
  laneBuffer.push(normalized);
  if (laneBuffer.length >= LANE_BATCH_MAX_SIZE) {
    await flushLaneEventBatch("max_size");
    return;
  }
  if (!laneFlushTimer) {
    laneFlushTimer = setTimeout(() => {
      void flushLaneEventBatch("timer");
    }, LANE_BATCH_WINDOW_MS);
    laneFlushTimer.unref?.();
  }
}

export async function flushLaneEventBatch(reason = "manual") {
  if (laneFlushTimer) {
    clearTimeout(laneFlushTimer);
    laneFlushTimer = null;
  }
  const batch = laneBuffer;
  laneBuffer = [];
  if (batch.length === 0) return;
  const client = await getRedisClient();
  if (!client) return;
  const encoded = deflateSync(pack(batch));
  await client.xAdd(laneBatchStreamKey(), "*", {
    codec: "msgpack+deflate",
    reason,
    count: String(batch.length),
    pid: String(process.pid),
    at: String(Date.now()),
    payload: encoded,
  });
  await client.xTrim(laneBatchStreamKey(), "MAXLEN", STREAM_MAX_LEN);
}

export async function ensureRedisConsumerGroup(stream: string, group: string, startId = "0") {
  const client = await getRedisClient();
  if (!client) return false;
  await client.xGroupCreate(stream, group, startId, { MKSTREAM: true }).catch((error: any) => {
    if (!String(error?.message || error).includes("BUSYGROUP")) throw error;
  });
  return true;
}
