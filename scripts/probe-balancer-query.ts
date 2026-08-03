import dotenv from 'dotenv';
import { ethers } from 'ethers';
import { POLYGON_CHAIN_CONFIG } from '../src/config/chainConfig';

dotenv.config();

const BALANCER_VAULT = '0xBA12222222228d8Ba445958a75a0704d566BF2C8';
const DEFAULT_POOL_ID = '0x0297e37f1873d2dab4487aa67cd56b58e2f27875000100000000000000000002';
const DEFAULT_SENDER = '0xaD3eF84259cFACB5D77a70911f85d39D2DBB49c6';
const GIVEN_IN = 0;
const RPC_TIMEOUT_MS = Number(process.env.BALANCER_PROBE_TIMEOUT_MS || 4_000);

const vaultIface = new ethers.Interface([
  'function getPoolTokens(bytes32 poolId) view returns (address[] tokens,uint256[] balances,uint256 lastChangeBlock)',
  'function queryBatchSwap(uint8 kind, tuple(bytes32 poolId,uint256 assetInIndex,uint256 assetOutIndex,uint256 amount,bytes userData)[] swaps, address[] assets, tuple(address sender,bool fromInternalBalance,address recipient,bool toInternalBalance) funds) returns (int256[] assetDeltas)',
]);

function rpcCandidates(): string[] {
  const scalarEnv = [
    process.env.PRIMARY_READ_RPC_URL,
    process.env.EXACT_CALL_RPC_URL,
    process.env.CHAINSTACK_URL,
    process.env.DISCOVERY_RPC_URL,
    process.env.RPC_URL,
    process.env.POLYGON_RPC_URL,
    process.env.POLYGON_RPC,
    process.env.POLYGON_RPC2,
    process.env.HTTP_URL_2,
    process.env.BROADCAST_RPC_URL,
    process.env.VITE_POLYGON_RPC_URL,
  ].filter(Boolean) as string[];
  const listEnv = [
    process.env.RPC_ROTATION_HTTP_URLS,
    process.env.BROADCAST_RPC_FALLBACK_URLS,
    process.env.DODO_RPC_EXTRA_HTTP_URLS,
  ]
    .filter(Boolean)
    .flatMap((value) => String(value).split(',').map((item) => item.trim()).filter(Boolean));
  const limit = Number(process.env.BALANCER_PROBE_RPC_LIMIT || 8);
  return [...scalarEnv, ...listEnv, ...Object.values(POLYGON_CHAIN_CONFIG.rpcEndpoints)]
    .filter((url) => /^https?:\/\//i.test(url))
    .filter((url, idx, all) => all.indexOf(url) === idx)
    .slice(0, limit);
}

function hostLabel(url: string): string {
  try { return new URL(url).host; } catch { return 'unknown-rpc-host'; }
}

async function rpc(url: string, method: string, params: unknown[]) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), RPC_TIMEOUT_MS);
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
      body: JSON.stringify({ jsonrpc: '2.0', id: Date.now(), method, params }),
    });
    if (!response.ok) throw new Error(`HTTP_${response.status}`);
    const json = await response.json() as { result?: unknown; error?: { message?: string } };
    if (json.error) throw new Error(json.error.message || JSON.stringify(json.error));
    return json.result;
  } finally {
    clearTimeout(timer);
  }
}

async function main() {
  const poolId = process.env.BALANCER_POOL_ID || DEFAULT_POOL_ID;
  if (!ethers.isHexString(poolId, 32)) throw new Error('BALANCER_POOL_ID must be bytes32');

  let lastError = '';
  for (const url of rpcCandidates()) {
    try {
      const chainId = await rpc(url, 'eth_chainId', []);
      if (chainId !== '0x89') throw new Error(`chainId=${String(chainId)}`);
      const blockHex = await rpc(url, 'eth_blockNumber', []) as string;
      const block = Number(BigInt(blockHex));
      const tokenData = await rpc(url, 'eth_call', [{
        to: BALANCER_VAULT,
        data: vaultIface.encodeFunctionData('getPoolTokens', [poolId]),
      }, blockHex]) as string;
      const [tokens, balances, lastChangeBlock] = vaultIface.decodeFunctionResult('getPoolTokens', tokenData) as unknown as [string[], bigint[], bigint];
      if (tokens.length < 2) throw new Error('pool has fewer than 2 tokens');
      const amountIn = balances[0] > 1_000_000n ? balances[0] / 10_000n : 1n;
      const swaps = [{ poolId, assetInIndex: 0, assetOutIndex: 1, amount: amountIn, userData: '0x' }];
      const funds = { sender: DEFAULT_SENDER, fromInternalBalance: false, recipient: DEFAULT_SENDER, toInternalBalance: false };
      const quoteData = await rpc(url, 'eth_call', [{
        to: BALANCER_VAULT,
        data: vaultIface.encodeFunctionData('queryBatchSwap', [GIVEN_IN, swaps, [tokens[0], tokens[1]], funds]),
      }, blockHex]) as string;
      const [deltas] = vaultIface.decodeFunctionResult('queryBatchSwap', quoteData) as unknown as [bigint[]];
      const amountOut = -(deltas[1] ?? 0n);
      if (amountOut <= 0n) throw new Error('non-positive output from queryBatchSwap');
      console.log('BALANCER_QUERY_PROBE=PASS');
      console.log(`rpcHost=${hostLabel(url)} block=${block} poolId=${poolId}`);
      console.log(`tokenIn=${tokens[0]} tokenOut=${tokens[1]} amountInRaw=${amountIn.toString()} amountOutRaw=${amountOut.toString()} lastChangeBlock=${lastChangeBlock.toString()}`);
      return;
    } catch (err) {
      lastError = `${hostLabel(url)}:${err instanceof Error ? err.message : String(err)}`;
    }
  }
  console.error(`BALANCER_QUERY_PROBE=FAIL reason=${lastError}`);
  process.exitCode = 1;
}

main().catch((err) => {
  console.error(`BALANCER_QUERY_PROBE=FAIL reason=${err instanceof Error ? err.message : String(err)}`);
  process.exitCode = 1;
});