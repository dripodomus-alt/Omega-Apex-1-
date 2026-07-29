/**
 * OMEGA V5 — Cloud SQL Data Service (client-side)
 *
 * All Cloud SQL operations are proxied through the Express server at /api/sql/*
 * because browsers cannot open raw TCP connections to PostgreSQL directly.
 * The server requires CLOUD_SQL_HOST / CLOUD_SQL_DATABASE / CLOUD_SQL_USER /
 * CLOUD_SQL_PASSWORD to be set; calls return an error when the pool is
 * unavailable rather than falling back to any local data.
 *
 * Expected Cloud SQL schema:
 *
 *   CREATE TABLE omega_routes (
 *     id          TEXT PRIMARY KEY,
 *     payload     JSONB NOT NULL,
 *     updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
 *   );
 *
 *   CREATE TABLE omega_audit_logs (
 *     id          TEXT PRIMARY KEY,
 *     payload     JSONB NOT NULL,
 *     created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
 *   );
 */

import { ArbitrageRoute, SimulationAuditLog } from '../types';

const BASE = '/api/sql';

// ─── Connectivity ─────────────────────────────────────────────────────────────

export async function pingCloudSql(): Promise<{ connected: boolean; latencyMs?: number; error?: string }> {
  try {
    const res = await fetch(`${BASE}/ping`);
    return res.json();
  } catch (err: any) {
    return { connected: false, error: err.message };
  }
}

// ─── Routes ───────────────────────────────────────────────────────────────────

export async function fetchRoutesFromCloudSql(): Promise<ArbitrageRoute[]> {
  const res = await fetch(`${BASE}/routes`);
  if (!res.ok) throw new Error(`Cloud SQL routes fetch failed: ${res.status}`);
  const { routes } = await res.json();
  return routes as ArbitrageRoute[];
}

export async function syncRouteToCloudSql(route: ArbitrageRoute): Promise<void> {
  const res = await fetch(`${BASE}/routes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(route),
  });
  if (!res.ok) throw new Error(`Cloud SQL route sync failed: ${res.status}`);
}

// ─── Audit Logs ───────────────────────────────────────────────────────────────

export async function fetchAuditLogsFromCloudSql(): Promise<SimulationAuditLog[]> {
  const res = await fetch(`${BASE}/audit-logs`);
  if (!res.ok) throw new Error(`Cloud SQL audit log fetch failed: ${res.status}`);
  const { logs } = await res.json();
  return logs as SimulationAuditLog[];
}

export async function syncAuditLogToCloudSql(log: SimulationAuditLog): Promise<void> {
  const res = await fetch(`${BASE}/audit-logs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(log),
  });
  if (!res.ok) throw new Error(`Cloud SQL audit log sync failed: ${res.status}`);
}
