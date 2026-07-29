/**
 * OMEGA V5 — Redis Data Service (client-side)
 *
 * All Redis operations are proxied through the Express server at /api/redis/*
 * because browsers cannot open raw TCP connections to Redis directly.
 * The server requires REDIS_URL to be set; calls return an error object when
 * the connection is unavailable rather than falling back to any local cache.
 */

import { ArbitrageRoute, SimulationAuditLog } from '../types';

const BASE = '/api/redis';

// ─── Connectivity ─────────────────────────────────────────────────────────────

export async function pingRedis(): Promise<{ connected: boolean; latencyMs?: number; error?: string }> {
  try {
    const res = await fetch(`${BASE}/ping`);
    return res.json();
  } catch (err: any) {
    return { connected: false, error: err.message };
  }
}

// ─── Routes ───────────────────────────────────────────────────────────────────

export async function fetchRoutesFromRedis(): Promise<ArbitrageRoute[]> {
  const res = await fetch(`${BASE}/routes`);
  if (!res.ok) throw new Error(`Redis routes fetch failed: ${res.status}`);
  const { routes } = await res.json();
  return routes as ArbitrageRoute[];
}

export async function syncRouteToRedis(route: ArbitrageRoute): Promise<void> {
  const res = await fetch(`${BASE}/routes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(route),
  });
  if (!res.ok) throw new Error(`Redis route sync failed: ${res.status}`);
}

// ─── Audit Logs ───────────────────────────────────────────────────────────────

export async function fetchAuditLogsFromRedis(): Promise<SimulationAuditLog[]> {
  const res = await fetch(`${BASE}/audit-logs`);
  if (!res.ok) throw new Error(`Redis audit log fetch failed: ${res.status}`);
  const { logs } = await res.json();
  return logs as SimulationAuditLog[];
}

export async function syncAuditLogToRedis(log: SimulationAuditLog): Promise<void> {
  const res = await fetch(`${BASE}/audit-logs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(log),
  });
  if (!res.ok) throw new Error(`Redis audit log sync failed: ${res.status}`);
}
