import 'dotenv/config';
import express from 'express';
import path from 'path';
import { GoogleGenAI } from '@google/genai';
import { createServer as createViteServer } from 'vite';
import Redis from 'ioredis';
import { Pool } from 'pg';
import { runBootAudit } from './src/utils/bootAudit';

// ─── Redis client (lazy — only created when env vars are present) ─────────────

let redisClient: Redis | null = null;

function getRedisClient(): Redis | null {
  if (redisClient) return redisClient;
  const url = process.env.REDIS_URL;
  if (!url) return null;
  redisClient = new Redis(url, { lazyConnect: true, connectTimeout: 5000, maxRetriesPerRequest: 1 });
  redisClient.on('error', () => { /* suppress uncaught errors — handled per-request */ });
  return redisClient;
}

// ─── Cloud SQL (PostgreSQL) pool (lazy) ───────────────────────────────────────

let pgPool: Pool | null = null;

function getPgPool(): Pool | null {
  if (pgPool) return pgPool;
  const host     = process.env.CLOUD_SQL_HOST;
  // On Cloud Run with Cloud SQL Auth Proxy, CLOUD_SQL_SOCKET overrides host/port
  const socket   = process.env.CLOUD_SQL_SOCKET;
  const port     = parseInt(process.env.CLOUD_SQL_PORT || '5432', 10);
  const database = process.env.CLOUD_SQL_DATABASE;
  const user     = process.env.CLOUD_SQL_USER;
  const password = process.env.CLOUD_SQL_PASSWORD;
  if (!database || !user || !password || (!host && !socket)) return null;
  pgPool = socket
    ? new Pool({ host: socket, database, user, password, ssl: false, connectionTimeoutMillis: 5000, max: 5 })
    : new Pool({ host, port, database, user, password, ssl: { rejectUnauthorized: false }, connectionTimeoutMillis: 5000, max: 5 });
  return pgPool;
}

async function startServer() {
  // ── Boot-time audit: validates env, wallets, contracts before serving ──────
  runBootAudit();

  const app  = express();
  // Cloud Run injects PORT; fall back to 3000 for local dev
  const PORT = parseInt(process.env.PORT || '3000', 10);

  // 1 MB body cap — prevents oversized-payload attacks
  app.use(express.json({ limit: '1mb' }));

  // Health Endpoint
  app.get('/api/health', (req, res) => {
    res.json({
      status: 'ok',
      engine: 'OMEGA-FINALLY-RICH-V5',
      chainId: 137,
      network: 'Polygon PoS',
      executor: process.env.C1_ARB_EXECUTOR_ADDRESS || 'not-configured',
      fundingVault: '0xBA12222222228d8Ba445958a75a0704d566BF2C8',
      rustEngineStatus: 'OPTIMIZED_RELEASE_COMPILED',
      redisStream: 'omega:audit:simulations',
      timestamp: new Date().toISOString(),
    });
  });

  // ─── Redis Endpoints ──────────────────────────────────────────────────────

  /** Ping Redis and return latency */
  app.get('/api/redis/ping', async (req, res) => {
    const redis = getRedisClient();
    if (!redis) {
      return res.status(503).json({ connected: false, error: 'REDIS_URL not configured' });
    }
    const t0 = Date.now();
    try {
      await redis.ping();
      res.json({ connected: true, latencyMs: Date.now() - t0 });
    } catch (err: any) {
      res.status(503).json({ connected: false, error: err.message });
    }
  });

  /** Read routes from Redis hash OMEGA:routes */
  app.get('/api/redis/routes', async (req, res) => {
    const redis = getRedisClient();
    if (!redis) return res.status(503).json({ error: 'REDIS_URL not configured' });
    try {
      const raw = await redis.hgetall('OMEGA:routes');
      const routes = Object.values(raw || {}).map((v) => JSON.parse(v));
      res.json({ routes });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  /** Write a route to Redis hash OMEGA:routes */
  app.post('/api/redis/routes', async (req, res) => {
    const redis = getRedisClient();
    if (!redis) return res.status(503).json({ error: 'REDIS_URL not configured' });
    const route = req.body;
    if (!route?.id) return res.status(400).json({ error: 'route.id required' });
    try {
      await redis.hset('OMEGA:routes', route.id, JSON.stringify(route));
      res.json({ ok: true });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  /** Read audit logs from Redis stream omega:audit:simulations (last 500) */
  app.get('/api/redis/audit-logs', async (req, res) => {
    const redis = getRedisClient();
    if (!redis) return res.status(503).json({ error: 'REDIS_URL not configured' });
    try {
      const entries = await redis.xrevrange('omega:audit:simulations', '+', '-', 'COUNT', 500);
      const logs = entries.map(([id, fields]) => {
        const obj: Record<string, string> = {};
        for (let i = 0; i < fields.length; i += 2) obj[fields[i]] = fields[i + 1];
        return { _streamId: id, ...JSON.parse(obj.payload || '{}') };
      });
      res.json({ logs });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  /** Append an audit log to Redis stream */
  app.post('/api/redis/audit-logs', async (req, res) => {
    const redis = getRedisClient();
    if (!redis) return res.status(503).json({ error: 'REDIS_URL not configured' });
    const log = req.body;
    if (!log?.id) return res.status(400).json({ error: 'log.id required' });
    try {
      const streamId = await redis.xadd('omega:audit:simulations', '*', 'payload', JSON.stringify(log));
      res.json({ ok: true, streamId });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  // ─── Cloud SQL Endpoints ──────────────────────────────────────────────────

  /** Ping Cloud SQL */
  app.get('/api/sql/ping', async (req, res) => {
    const pool = getPgPool();
    if (!pool) {
      return res.status(503).json({ connected: false, error: 'CLOUD_SQL_* env vars not configured' });
    }
    const t0 = Date.now();
    try {
      await pool.query('SELECT 1');
      res.json({ connected: true, latencyMs: Date.now() - t0 });
    } catch (err: any) {
      res.status(503).json({ connected: false, error: err.message });
    }
  });

  /** Read routes from Cloud SQL table omega_routes */
  app.get('/api/sql/routes', async (req, res) => {
    const pool = getPgPool();
    if (!pool) return res.status(503).json({ error: 'CLOUD_SQL_* env vars not configured' });
    try {
      const { rows } = await pool.query(
        'SELECT payload FROM omega_routes ORDER BY updated_at DESC LIMIT 500'
      );
      const routes = rows.map((r) => r.payload);
      res.json({ routes });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  /** Upsert a route into Cloud SQL */
  app.post('/api/sql/routes', async (req, res) => {
    const pool = getPgPool();
    if (!pool) return res.status(503).json({ error: 'CLOUD_SQL_* env vars not configured' });
    const route = req.body;
    if (!route?.id) return res.status(400).json({ error: 'route.id required' });
    try {
      await pool.query(
        `INSERT INTO omega_routes (id, payload, updated_at)
         VALUES ($1, $2, NOW())
         ON CONFLICT (id) DO UPDATE SET payload = EXCLUDED.payload, updated_at = NOW()`,
        [route.id, route]
      );
      res.json({ ok: true });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  /** Read audit logs from Cloud SQL table omega_audit_logs */
  app.get('/api/sql/audit-logs', async (req, res) => {
    const pool = getPgPool();
    if (!pool) return res.status(503).json({ error: 'CLOUD_SQL_* env vars not configured' });
    try {
      const { rows } = await pool.query(
        'SELECT payload FROM omega_audit_logs ORDER BY created_at DESC LIMIT 500'
      );
      const logs = rows.map((r) => r.payload);
      res.json({ logs });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  /** Insert an audit log into Cloud SQL */
  app.post('/api/sql/audit-logs', async (req, res) => {
    const pool = getPgPool();
    if (!pool) return res.status(503).json({ error: 'CLOUD_SQL_* env vars not configured' });
    const log = req.body;
    if (!log?.id) return res.status(400).json({ error: 'log.id required' });
    try {
      await pool.query(
        `INSERT INTO omega_audit_logs (id, payload, created_at)
         VALUES ($1, $2, NOW())
         ON CONFLICT (id) DO NOTHING`,
        [log.id, log]
      );
      res.json({ ok: true });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  // Gemini Route Analysis Endpoint
  app.post('/api/gemini/analyze-route', async (req, res) => {
    try {
      const apiKey = process.env.GEMINI_API_KEY;
      if (!apiKey) {
        return res.status(500).json({ error: 'GEMINI_API_KEY environment variable is missing.' });
      }

      const { routeData, customPrompt } = req.body;

      const ai = new GoogleGenAI({
        apiKey,
        httpOptions: {
          headers: {
            'User-Agent': 'aistudio-build',
          },
        },
      });

      const systemInstruction = `You are OMEGA V5 Quantum MEV Analyst, an expert on Polygon PoS (Chain 137) DEX arbitrage, UniSwap V3 sqrtPriceX96 virtual reserve math, Aave V3 liquidations, Balancer V3 transient storage flashloans, VQC quantum surplus ranking, and low-latency Redis/SQL audit streams.
Provide high-density, action-oriented, technical analysis.
Output clear JSON structure containing:
- analysisSummary: concise string
- riskLevel: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
- keyRiskFactors: array of strings
- executionOptimization: string
- suggestedSlippageBps: number
- sqlAuditQuery: string
- quantumAlphaScoreRecommendation: number`;

      const prompt = customPrompt
        ? `User Question: ${customPrompt}\nRoute Data: ${JSON.stringify(routeData)}`
        : `Analyze this Polygon PoS Arbitrage Route for maximum execution safety and profit optimization:
${JSON.stringify(routeData, null, 2)}`;

      const response = await ai.models.generateContent({
        model: 'gemini-3.6-flash',
        contents: prompt,
        config: {
          systemInstruction,
          responseMimeType: 'application/json',
          temperature: 0.2,
        },
      });

      const responseText = response.text || '{}';
      const parsedData = JSON.parse(responseText);

      res.json({
        success: true,
        data: parsedData,
      });
    } catch (error: any) {
      console.error('Error in Gemini analysis route:', error);
      res.status(500).json({
        success: false,
        error: error.message || 'Failed to generate route analysis via Gemini.',
      });
    }
  });

  // Vite middleware for development vs static production serving
  if (process.env.NODE_ENV !== 'production') {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), 'dist');
    app.use(express.static(distPath));
    app.get('*', (req, res) => {
      res.sendFile(path.join(distPath, 'index.html'));
    });
  }

  const server = app.listen(PORT, '0.0.0.0', () => {
    console.log(`OMEGA V5 Engine Server listening on http://0.0.0.0:${PORT}`);
  });

  // ── Graceful shutdown (Cloud Run sends SIGTERM before stopping the instance) ─
  function shutdown(signal: string) {
    console.log(`[${signal}] Graceful shutdown initiated…`);
    server.close(async () => {
      try {
        if (redisClient) await redisClient.quit();
        if (pgPool)      await pgPool.end();
      } catch (_) { /* best-effort */ }
      console.log('[shutdown] All connections closed. Exiting.');
      process.exit(0);
    });
    // Force-exit after 10 s if connections don't drain
    setTimeout(() => { console.error('[shutdown] Drain timeout — forcing exit'); process.exit(1); }, 10_000).unref();
  }

  process.on('SIGTERM', () => shutdown('SIGTERM'));
  process.on('SIGINT',  () => shutdown('SIGINT'));
}

startServer();
