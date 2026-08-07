import 'dotenv/config';
import { ethers } from 'ethers';
import {
  PolygonRuntime,
} from '../src/engine/rpc/polygonRuntime';

const WMATIC =
  '0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270';

const USDC_E =
  '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174';

const ERC20 = new ethers.Interface([
  'function decimals() view returns (uint8)',
  'function symbol() view returns (string)',
  'function totalSupply() view returns (uint256)',
]);

const runtime = new PolygonRuntime({
  httpUrl:
    process.env.ALCHEMY_POLYGON_HTTP_URL,
  wssUrl:
    process.env.ALCHEMY_POLYGON_WSS_URL,
  multicallBatchSize:
    Number(
      process.env.MULTICALL_BATCH_SIZE ??
      128,
    ),
});

try {
  const health = await runtime.health();

  if (!health.ok) {
    throw new Error(
      `Runtime health failed: ${JSON.stringify(health)}`,
    );
  }

  const block =
    health.transport.latestBlock!;

  const started =
    performance.now();

  const reads =
    await runtime.batchRead<unknown>(
      [
        {
          target: WMATIC,
          iface: ERC20,
          functionName: 'decimals',
        },
        {
          target: WMATIC,
          iface: ERC20,
          functionName: 'symbol',
        },
        {
          target: USDC_E,
          iface: ERC20,
          functionName: 'decimals',
        },
        {
          target: USDC_E,
          iface: ERC20,
          functionName: 'symbol',
        },
      ],
      block,
    );

  const elapsedMs =
    performance.now() - started;

  const wmaticMetadata =
    await runtime.enhancedClient
      .getTokenMetadata(WMATIC);

  const usdcMetadata =
    await runtime.enhancedClient
      .getTokenMetadata(USDC_E);

  const subscriptions =
    await runtime.subscriptionManager();

  let observedHead:
    number | null = null;

  const unsubscribe =
    subscriptions.subscribeNewHeads(
      (event) => {
        observedHead =
          event.blockNumber;
      },
    );

  await new Promise<void>(
    (resolve) => {
      setTimeout(resolve, 3_000);
    },
  );

  unsubscribe();

  console.log(
    JSON.stringify(
      {
        test:
          'APEX_ALCHEMY_POLYGON_RUNTIME',
        chainId:
          health.transport.chainId,
        latestBlock:
          block,
        observedSubscriptionHead:
          observedHead,
        readTransport:
          'ALCHEMY_HTTP',
        subscriptionTransport:
          'ALCHEMY_WSS',
        fallback:
          'PUBLICNODE',
        multicall3:
          health.multicallAddress,
        multicallBatchSize:
          health.multicallBatchSize,
        batchReadElapsedMs:
          Number(
            elapsedMs.toFixed(3),
          ),
        multicallReads:
          reads.map((row) => ({
            success: row.success,
            value:
              typeof row.value ===
              'bigint'
                ? row.value.toString()
                : String(
                    row.value ?? '',
                  ),
            error:
              row.error ?? null,
          })),
        enhancedApi: {
          wmaticMetadata,
          usdcMetadata,
        },
        result:
          reads.every(
            (row) => row.success,
          )
            ? 'PASS'
            : 'FAIL',
      },
      null,
      2,
    ),
  );
} finally {
  await runtime.destroy();
}
