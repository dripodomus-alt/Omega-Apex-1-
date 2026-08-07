import { ethers } from 'ethers';
import {
  POLYGON_PUBLICNODE_WSS,
  PolygonWssTransport,
} from '../src/engine/rpc/polygonTransport';
import {
  MULTICALL3_ADDRESS,
  Multicall3Client,
} from '../src/engine/rpc/multicall3';

const WMATIC =
  '0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270';

const USDC_E =
  '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174';

const ERC20_IFACE = new ethers.Interface([
  'function decimals() view returns (uint8)',
  'function symbol() view returns (string)',
  'function totalSupply() view returns (uint256)',
]);

async function main(): Promise<void> {
  const transport = new PolygonWssTransport({
    wssUrl: POLYGON_PUBLICNODE_WSS,
    chainId: 137,
  });

  try {
    const provider = await transport.connect();
    const health = await transport.health();

    if (!health.ok || health.chainId !== 137) {
      throw new Error(
        `Polygon WSS health failed: ${JSON.stringify(health)}`,
      );
    }

    const multicall = new Multicall3Client(
      provider,
      MULTICALL3_ADDRESS,
    );

    await multicall.assertDeployed();

    const requests = [
      {
        target: WMATIC,
        iface: ERC20_IFACE,
        functionName: 'decimals',
      },
      {
        target: WMATIC,
        iface: ERC20_IFACE,
        functionName: 'symbol',
      },
      {
        target: USDC_E,
        iface: ERC20_IFACE,
        functionName: 'decimals',
      },
      {
        target: USDC_E,
        iface: ERC20_IFACE,
        functionName: 'symbol',
      },
    ];

    const startedAt = performance.now();

    const results = await multicall.readMany<unknown>(
      requests,
      {
        batchSize: 128,
        blockTag: health.latestBlock,
      },
    );

    const elapsedMs = performance.now() - startedAt;

    console.log('APEX_POLYGON_WSS_MULTICALL_PROBE');
    console.log(
      JSON.stringify(
        {
          endpoint: health.endpoint,
          chainId: health.chainId,
          latestBlock: health.latestBlock,
          multicall3: MULTICALL3_ADDRESS,
          callsSubmitted: requests.length,
          rpcRoundTripMode: 'MULTICALL3_AGGREGATE3',
          elapsedMs: Number(elapsedMs.toFixed(3)),
          results: results.map((row, index) => ({
            target: requests[index].target,
            functionName: requests[index].functionName,
            success: row.success,
            value:
              typeof row.value === 'bigint'
                ? row.value.toString()
                : String(row.value ?? ''),
            error: row.error ?? null,
          })),
        },
        null,
        2,
      ),
    );

    if (results.some((row) => !row.success)) {
      throw new Error(
        'One or more Multicall3 probe calls failed',
      );
    }

    console.log('RESULT=PASS');
  } finally {
    await transport.destroy();
  }
}

await main();
