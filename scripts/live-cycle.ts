import 'dotenv/config';
import { ethers } from 'ethers';
import { POLYGON_CHAIN_CONFIG } from '../src/config/chainConfig';

const V2_FACTORY_ABI = ['function getPair(address tokenA, address tokenB) view returns (address pair)'];
const V2_PAIR_ABI = [
  'function token0() view returns (address)',
  'function token1() view returns (address)',
  'function getReserves() view returns (uint112 reserve0, uint112 reserve1, uint32 blockTimestampLast)',
];
const EXECUTOR_ABI = [
  'function executeArbitrage(address[] calldata path, uint256 inputAmount, uint256 minProfitUSD, bytes calldata flashloanData) external returns (uint256 netProfit)',
];

const ZERO_ADDRESS = '0x0000000000000000000000000000000000000000';
const USDC = '0x2791bca1f2de4661ed88a30c99a7a9449aa84174';
const WMATIC = '0x0d500b1d8e8ef31e21c99d1db9a6444d3adf1270';
const INPUT_USDC = BigInt(process.env.APEX_TRUTH_INPUT_USDC_RAW ?? '1000000000');
const MIN_PROFIT_USDC = BigInt(process.env.APEX_TRUTH_MIN_PROFIT_USDC_RAW ?? '1');

type PoolState = {
  venue: string;
  factory: string;
  address: string;
  token0: string;
  token1: string;
  reserve0: bigint;
  reserve1: bigint;
  priceUsdPerUnit: number;
};

const FACTORIES = [
  { venue: 'QuickSwap V2', factory: '0x5757371414417b8c6caad45baef941abc7d3ab32' },
  { venue: 'SushiSwap V2', factory: '0xc35dadb65012ec5796536bd9864ed8773abc74c4' },
];

function argValue(name: string, fallback: string): string {
  const idx = process.argv.indexOf(name);
  return idx >= 0 && process.argv[idx + 1] ? process.argv[idx + 1] : fallback;
}

function resolveRpcUrl(): string {
  return (
    process.env.APEX_TRUTH_RPC_URL ||
    process.env.POLYGON_RPC_URL ||
    process.env.PRIMARY_READ_RPC_URL ||
    POLYGON_CHAIN_CONFIG.rpcEndpoints.chainstackHttp ||
    'https://polygon-bor-rpc.publicnode.com'
  );
}

function safeError(error: unknown): string {
  return error instanceof Error ? error.message.replace(/\s+/g, ' ').slice(0, 260) : String(error);
}

function event(cycle: number, stage: string, status: 'PASS' | 'FAIL' | 'WARN', detail: Record<string, unknown>) {
  console.log(JSON.stringify({ type: 'cycle_event', cycle, stage, status, emittedAt: Date.now(), ...detail }));
}

function reservesFor(pool: PoolState, tokenIn: string) {
  const target = tokenIn.toLowerCase();
  if (pool.token0.toLowerCase() === target) return { reserveIn: pool.reserve0, reserveOut: pool.reserve1 };
  if (pool.token1.toLowerCase() === target) return { reserveIn: pool.reserve1, reserveOut: pool.reserve0 };
  throw new Error(`Token ${tokenIn} is not present in ${pool.venue}`);
}

function amountOutV2(amountIn: bigint, reserveIn: bigint, reserveOut: bigint, feeBps = 30): bigint {
  const amountInWithFee = amountIn * BigInt(10_000 - feeBps);
  return (amountInWithFee * reserveOut) / (reserveIn * 10_000n + amountInWithFee);
}

async function discoverPool(provider: ethers.JsonRpcProvider, item: { venue: string; factory: string }, blockTag: number) {
  const factory = new ethers.Contract(item.factory, V2_FACTORY_ABI, provider);
  const pair = String(await factory.getPair(USDC, WMATIC, { blockTag }));
  if (pair.toLowerCase() === ZERO_ADDRESS) throw new Error(`${item.venue} returned zero pair`);
  const code = await provider.getCode(pair, blockTag);
  if (code === '0x') throw new Error(`${item.venue} pair has no bytecode at ${pair}`);
  return { ...item, address: pair };
}

async function readPoolState(provider: ethers.JsonRpcProvider, pool: { venue: string; factory: string; address: string }, blockTag: number): Promise<PoolState> {
  const contract = new ethers.Contract(pool.address, V2_PAIR_ABI, provider);
  const [token0, token1, reserves] = await Promise.all([
    contract.token0({ blockTag }),
    contract.token1({ blockTag }),
    contract.getReserves({ blockTag }),
  ]);
  const reserve0 = BigInt(reserves.reserve0.toString());
  const reserve1 = BigInt(reserves.reserve1.toString());
  const usdcIs0 = String(token0).toLowerCase() === USDC.toLowerCase();
  const wmaticIs0 = String(token0).toLowerCase() === WMATIC.toLowerCase();
  const usdcReserve = usdcIs0 ? reserve0 : reserve1;
  const wmaticReserve = wmaticIs0 ? reserve0 : reserve1;
  const priceUsdPerUnit = Number(ethers.formatUnits(usdcReserve, 6)) / Number(ethers.formatUnits(wmaticReserve, 18));
  return { ...pool, token0, token1, reserve0, reserve1, priceUsdPerUnit };
}

async function main() {
  const cycle = Number(argValue('--cycle-index', '1'));
  const mode = argValue('--mode', 'proof');
  const rpcUrl = resolveRpcUrl();
  const provider = new ethers.JsonRpcProvider(rpcUrl, 137, { staticNetwork: true });
  const executor = process.env.C1_ARB_EXECUTOR_ADDRESS || process.env.C1_TARGET || POLYGON_CHAIN_CONFIG.c1ArbExecutorAddress;
  const bot = process.env.EXECUTOR_WALLET || process.env.BOT_ADDRESS || POLYGON_CHAIN_CONFIG.botAddress;

  console.log(`LIVE_CYCLE_START|cycle=${cycle}|mode=${mode}|submitMode=PROOF_ONLY`);
  const network = await provider.getNetwork();
  if (network.chainId !== 137n) throw new Error(`Wrong chain: ${network.chainId.toString()}`);

  const blockNumber = await provider.getBlockNumber();
  const block = await provider.getBlock(blockNumber);
  event(cycle, 'RPC_STATE', 'PASS', { blockNumber, blockHash: block?.hash || null });

  const discovered = await Promise.all(FACTORIES.map((item) => discoverPool(provider, item, blockNumber)));
  event(cycle, 'DISCOVERY', 'PASS', { discoveredPools: discovered.length, pools: discovered.map((item) => ({ venue: item.venue, pair: item.address })) });

  const states = await Promise.all(discovered.map((pool) => readPoolState(provider, pool, blockNumber)));
  event(cycle, 'RESERVE_HYDRATION', 'PASS', {
    pools: states.map((item) => ({ venue: item.venue, priceUsdPerUnit: Number(item.priceUsdPerUnit.toFixed(8)) })),
  });

  const candidates = states.flatMap((buyPool) =>
    states
      .filter((sellPool) => sellPool.address.toLowerCase() !== buyPool.address.toLowerCase())
      .map((sellPool) => {
        const buyReserves = reservesFor(buyPool, USDC);
        const buyOut = amountOutV2(INPUT_USDC, buyReserves.reserveIn, buyReserves.reserveOut);
        const sellReserves = reservesFor(sellPool, WMATIC);
        const sellOut = amountOutV2(buyOut, sellReserves.reserveIn, sellReserves.reserveOut);
        return { buyPool, sellPool, buyOut, sellOut, grossDelta: sellOut - INPUT_USDC };
      }),
  ).sort((a, b) => Number(b.grossDelta - a.grossDelta));

  const best = candidates[0];
  const profitable = Boolean(best && best.grossDelta > 0n);
  event(cycle, 'QUOTE_RANKING', profitable ? 'PASS' : 'WARN', best ? {
    buyVenue: best.buyPool.venue,
    sellVenue: best.sellPool.venue,
    midOutWMATIC: ethers.formatUnits(best.buyOut, 18),
    grossDeltaUsdc: ethers.formatUnits(best.grossDelta, 6),
    candidateCount: candidates.length,
  } : { candidateCount: 0 });

  const executorCode = await provider.getCode(executor, blockNumber);
  if (executorCode === '0x') {
    event(cycle, 'EXECUTOR_PREFLIGHT', 'FAIL', { executor, reason: 'NO_BYTECODE_AT_EXECUTOR' });
    console.log(`DISCOVERY_SUMMARY|cycle=${cycle}|block=${blockNumber}|discoveredPools=${discovered.length}|candidateCount=${candidates.length}|verdict=BLOCKED_NO_EXECUTOR_CODE`);
    process.exitCode = 21;
    return;
  }

  const iface = new ethers.Interface(EXECUTOR_ABI);
  const calldata = iface.encodeFunctionData('executeArbitrage', [[USDC, WMATIC, USDC], INPUT_USDC, MIN_PROFIT_USDC, '0x']);
  try {
    const callResult = await provider.call({ from: bot, to: executor, data: calldata, value: 0n, blockTag: blockNumber });
    event(cycle, 'EXECUTOR_ETH_CALL', 'PASS', { executor, from: bot, resultBytes: (callResult.length - 2) / 2 });
    console.log(`DISCOVERY_SUMMARY|cycle=${cycle}|block=${blockNumber}|discoveredPools=${discovered.length}|candidateCount=${candidates.length}|verdict=${profitable ? 'PASS_TO_LIVE_SUBMIT' : 'NO_PROFITABLE_ROUTE'}`);
  } catch (error) {
    event(cycle, 'EXECUTOR_ETH_CALL', 'FAIL', { executor, from: bot, reason: safeError(error) });
    console.log(`DISCOVERY_SUMMARY|cycle=${cycle}|block=${blockNumber}|discoveredPools=${discovered.length}|candidateCount=${candidates.length}|verdict=BLOCKED_ETH_CALL_REVERT`);
    process.exitCode = 22;
  }
}

main().catch((error) => {
  const cycle = Number(argValue('--cycle-index', '1'));
  event(cycle, 'CYCLE_EXCEPTION', 'FAIL', { reason: safeError(error) });
  console.log(`DISCOVERY_SUMMARY|cycle=${cycle}|discoveredPools=0|candidateCount=0|verdict=FAILED_EXCEPTION`);
  process.exitCode = 99;
});
