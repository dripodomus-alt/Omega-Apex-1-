import 'dotenv/config';
import express from 'express';
import {
  runMarketEngine,
  usdToX18,
  type MarketIntakeEnvelope,
  type MarketEngineResult,
} from '../src/engine/market/marketEngine';
import {
  PolygonRuntime,
} from '../src/engine/rpc/polygonRuntime';

const PORT = Number(process.env.MARKET_API_PORT ?? 8797);
const HOST = process.env.MARKET_API_HOST ?? '0.0.0.0';

const MIN_POOL_TVL_USD = Number(
  process.env.MIN_POOL_TVL_USD ?? 50_000,
);

const STATE_TTL_BLOCKS = Number(
  process.env.MARKET_STATE_TTL_BLOCKS ?? 4,
);

const MIN_RAW_SPREAD_BPS = BigInt(
  process.env.MIN_RAW_SPREAD_BPS ?? '1',
);

const MAX_CANDIDATES = Number(
  process.env.MARKET_MAX_CANDIDATES ?? 500,
);

const INTAKE_TOKEN =
  process.env.MARKET_INTAKE_TOKEN?.trim() ?? '';

const runtime = new PolygonRuntime({
  httpUrl: process.env.ALCHEMY_POLYGON_HTTP_URL,
  wssUrl: process.env.ALCHEMY_POLYGON_WSS_URL,
  fallbackHttpUrl:
    process.env.POLYGON_FALLBACK_HTTP_URL,
  fallbackWssUrl:
    process.env.POLYGON_FALLBACK_WSS_URL,
  multicallBatchSize:
    Number(process.env.MULTICALL_BATCH_SIZE ?? 128),
});

let latestIntake: MarketIntakeEnvelope | null = null;
let latestSnapshot: MarketEngineResult | null = null;
let latestHead = 0;
let unsubscribeHeads: (() => void) | null = null;

const app = express();

app.disable('x-powered-by');
app.use(express.json({ limit: '20mb' }));

function requireIntakeAuth(
  req: express.Request,
  res: express.Response,
  next: express.NextFunction,
): void {
  if (!INTAKE_TOKEN) {
    next();
    return;
  }

  if (
    (req.header('authorization') ?? '') !==
    `Bearer ${INTAKE_TOKEN}`
  ) {
    res.status(401).json({
      error: 'UNAUTHORIZED',
    });
    return;
  }

  next();
}

function rebuildSnapshot(
  intake: MarketIntakeEnvelope,
): MarketEngineResult {
  return runMarketEngine(
    intake.quotes,
    {
      chainId: 137,
      minPoolTvlUsdX18:
        usdToX18(MIN_POOL_TVL_USD),
      stateTtlBlocks:
        STATE_TTL_BLOCKS,
      minRawSpreadBps:
        MIN_RAW_SPREAD_BPS,
      latestBlock:
        intake.latestBlock,
      maxCandidates:
        MAX_CANDIDATES,
    },
    intake.source,
  );
}

async function ensureSubscriptions(): Promise<void> {
  if (unsubscribeHeads) return;

  const manager =
    await runtime.subscriptionManager();

  unsubscribeHeads =
    manager.subscribeNewHeads((event) => {
      latestHead = Math.max(
        latestHead,
        event.blockNumber,
      );
    });
}

app.get('/healthz', async (_req, res) => {
  const health = await runtime.health();

  res
    .status(health.ok ? 200 : 503)
    .json({
      service:
        'apex-omega-market-api',
      chainId: 137,
      runtime: health,
      latestSubscribedHead:
        latestHead || null,
      intakeLoaded:
        latestIntake !== null,
      candidateCount:
        latestSnapshot?.candidateCount ?? 0,
    });
});

app.post(
  '/v1/intake',
  requireIntakeAuth,
  async (req, res) => {
    const body =
      req.body as Partial<MarketIntakeEnvelope>;

    if (
      body.schemaVersion !==
      'apex.market.intake.v1'
    ) {
      res.status(400).json({
        error: 'INVALID_SCHEMA',
      });
      return;
    }

    if (
      body.source !== 'LIVE_RPC' &&
      body.source !== 'LIVE_SCANNER' &&
      body.source !== 'SIMULATION'
    ) {
      res.status(400).json({
        error: 'INVALID_SOURCE',
      });
      return;
    }

    if (
      !Number.isInteger(body.latestBlock) ||
      Number(body.latestBlock) <= 0
    ) {
      res.status(400).json({
        error: 'INVALID_LATEST_BLOCK',
      });
      return;
    }

    if (!Array.isArray(body.quotes)) {
      res.status(400).json({
        error: 'QUOTES_REQUIRED',
      });
      return;
    }

    const health = await runtime.health();

    if (!health.ok) {
      res.status(503).json({
        error: 'POLYGON_RUNTIME_FAILED',
        health,
      });
      return;
    }

    const observedHead =
      latestHead ||
      health.transport.latestBlock ||
      0;

    if (
      body.source !== 'SIMULATION' &&
      Number(body.latestBlock) >
        observedHead + 1
    ) {
      res.status(409).json({
        error:
          'INTAKE_BLOCK_AHEAD_OF_RUNTIME',
        intakeBlock:
          Number(body.latestBlock),
        runtimeBlock:
          observedHead,
      });
      return;
    }

    const intake: MarketIntakeEnvelope = {
      schemaVersion:
        'apex.market.intake.v1',
      source: body.source,
      latestBlock:
        Number(body.latestBlock),
      observedAtMs:
        typeof body.observedAtMs === 'number'
          ? body.observedAtMs
          : Date.now(),
      quotes: body.quotes,
    };

    latestIntake = intake;
    latestSnapshot =
      rebuildSnapshot(intake);

    res.json({
      accepted: true,
      latestBlock:
        intake.latestBlock,
      inputRows:
        intake.quotes.length,
      eligibleRows:
        latestSnapshot.eligibleRows,
      rejectedRows:
        latestSnapshot.rejectedRows.length,
      comparableMarkets:
        latestSnapshot.comparableMarkets,
      candidateCount:
        latestSnapshot.candidateCount,
      generatedAtMs:
        latestSnapshot.generatedAtMs,
      runtime: {
        readTransport:
          'ALCHEMY_HTTP',
        subscriptionTransport:
          'ALCHEMY_WSS',
        fallback:
          'PUBLICNODE',
        multicall:
          true,
        enhancedApis:
          true,
      },
    });
  },
);

app.get('/v1/snapshot', (_req, res) => {
  if (!latestSnapshot) {
    res.status(503).json({
      error: 'NO_MARKET_SNAPSHOT',
    });
    return;
  }

  res.setHeader(
    'Cache-Control',
    'no-store, max-age=0',
  );

  res.json({
    ...latestSnapshot,
    latestSubscribedHead:
      latestHead || null,
    runtime: {
      readTransport:
        'ALCHEMY_HTTP',
      subscriptionTransport:
        'ALCHEMY_WSS',
      fallback:
        'PUBLICNODE',
      multicall:
        true,
      enhancedApis:
        true,
    },
  });
});

app.get(
  '/v1/alchemy/token-metadata/:address',
  async (req, res) => {
    try {
      const result =
        await runtime.enhancedClient
          .getTokenMetadata(
            req.params.address,
          );

      res.json(result);
    } catch (error) {
      res.status(502).json({
        error:
          error instanceof Error
            ? error.message
            : String(error),
      });
    }
  },
);

app.post(
  '/v1/alchemy/token-balances',
  async (req, res) => {
    try {
      const body = req.body as {
        owner?: string;
        tokenAddresses?: string[];
      };

      if (
        !body.owner ||
        !Array.isArray(body.tokenAddresses)
      ) {
        res.status(400).json({
          error:
            'owner and tokenAddresses[] required',
        });
        return;
      }

      const result =
        await runtime.enhancedClient
          .getTokenBalances(
            body.owner,
            body.tokenAddresses,
          );

      res.json(result);
    } catch (error) {
      res.status(502).json({
        error:
          error instanceof Error
            ? error.message
            : String(error),
      });
    }
  },
);

app.post(
  '/v1/alchemy/asset-transfers',
  async (req, res) => {
    try {
      const result =
        await runtime.enhancedClient
          .getAssetTransfers(req.body);

      res.json(result);
    } catch (error) {
      res.status(502).json({
        error:
          error instanceof Error
            ? error.message
            : String(error),
      });
    }
  },
);

app.get(
  '/v1/alchemy/block-receipts/:blockHex',
  async (req, res) => {
    try {
      const result =
        await runtime.enhancedClient
          .getTransactionReceiptsByBlockNumber(
            req.params.blockHex,
          );

      res.json(result);
    } catch (error) {
      res.status(502).json({
        error:
          error instanceof Error
            ? error.message
            : String(error),
      });
    }
  },
);

const server = app.listen(
  PORT,
  HOST,
  async () => {
    const health = await runtime.health();

    if (!health.ok) {
      console.error(
        JSON.stringify({
          service:
            'apex-omega-market-api',
          status: 'FAILED',
          health,
        }),
      );

      server.close(() => {
        process.exitCode = 1;
      });
      return;
    }

    await ensureSubscriptions();

    latestHead =
      health.transport.latestBlock ?? 0;

    console.log(
      JSON.stringify({
        service:
          'apex-omega-market-api',
        status: 'READY',
        chainId: 137,
        readTransport:
          'ALCHEMY_HTTP',
        subscriptionTransport:
          'ALCHEMY_WSS',
        fallback:
          'PUBLICNODE_HTTP_WSS',
        multicall3:
          health.multicallAddress,
        multicallBatchSize:
          health.multicallBatchSize,
        enhancedApiReady:
          health.enhancedApiReady,
        subscriptionsReady:
          health.subscriptionsReady,
        latestBlock:
          health.transport.latestBlock,
      }),
    );
  },
);

async function shutdown(): Promise<void> {
  unsubscribeHeads?.();
  unsubscribeHeads = null;

  await runtime.destroy();

  server.close();
}

process.once('SIGINT', () => {
  void shutdown();
});

process.once('SIGTERM', () => {
  void shutdown();
});
