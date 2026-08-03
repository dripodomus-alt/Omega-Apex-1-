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

interface V2FactoryConfig {
  id: string;
  venue: string;
  factory: string;
}

interface V2DiscoveredPool {
  id: string;
  venue: string;
  factory: string;
  address: string;
}

interface LivePoolState extends V2DiscoveredPool {
  token0: string;
  token1: string;
  reserve0: bigint;
  reserve1: bigint;
  blockTimestampLast: number;
  priceUsdPerUnit: number;
}

interface QuoteLeg {
  pool: LivePoolState;
  tokenIn: string;
  tokenOut: string;
  amountIn: bigint;
  amountOut: bigint;
}

const ZERO_ADDRESS = '0x0000000000000000000000000000000000000000';
const USDC = '0x2791bca1f2de4661ed88a30c99a7a9449aa84174';
const WMATIC = '0x0d500b1d8e8ef31e21c99d1db9a6444d3adf1270';
const BOT = POLYGON_CHAIN_CONFIG.botAddress;
const EXECUTOR = POLYGON_CHAIN_CONFIG.c1ArbExecutorAddress;
const INPUT_USDC = BigInt(process.env.APEX_TRUTH_INPUT_USDC_RAW ?? '1000000000');
const MIN_PROFIT_USDC = BigInt(process.env.APEX_TRUTH_MIN_PROFIT_USDC_RAW ?? '1');

const V2_FACTORIES: V2FactoryConfig[] = [
  { id: 'quickswap_v2', venue: 'QuickSwap V2', factory: '0x5757371414417b8c6caad45baef941abc7d3ab32' },
  { id: 'sushiswap_v2', venue: 'SushiSwap V2', factory: '0xc35dadb65012ec5796536bd9864ed8773abc74c4' },
];

function resolveRpcUrl(): string {
  const fromEnv = process.env.APEX_TRUTH_RPC_URL || process.env.POLYGON_RPC_URL || process.env.PRIMARY_READ_RPC_URL;
  return fromEnv || POLYGON_CHAIN_CONFIG.rpcEndpoints.chainstackHttp || 'https://polygon-bor-rpc.publicnode.com';
}

function safeRpcLabel(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return 'configured-rpc';
  }
}

function amountOutV2(amountIn: bigint, reserveIn: bigint, reserveOut: bigint, feeBps: number): bigint {
  const feeDenom = 10_000n;
  const amountInWithFee = amountIn * BigInt(10_000 - feeBps);
  return (amountInWithFee * reserveOut) / (reserveIn * feeDenom + amountInWithFee);
}

function reservesFor(pool: LivePoolState, tokenIn: string): { reserveIn: bigint; reserveOut: bigint } {
  const inLower = tokenIn.toLowerCase();
  if (pool.token0.toLowerCase() === inLower) return { reserveIn: pool.reserve0, reserveOut: pool.reserve1 };
  if (pool.token1.toLowerCase() === inLower) return { reserveIn: pool.reserve1, reserveOut: pool.reserve0 };
  throw new Error(`Token ${tokenIn} is not in pool ${pool.id}`);
}

async function discoverPool(provider: ethers.JsonRpcProvider, factoryConfig: V2FactoryConfig, blockTag: number): Promise<V2DiscoveredPool> {
  const factory = new ethers.Contract(factoryConfig.factory, V2_FACTORY_ABI, provider);
  let pair = '';
  let lastError: unknown;
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    try {
      pair = String(await factory.getPair(USDC, WMATIC, { blockTag }));
      break;
    } catch (err) {
      lastError = err;
      await new Promise((resolve) => setTimeout(resolve, 250 * attempt));
    }
  }
  if (!pair) {
    const reason = lastError instanceof Error ? lastError.message.replace(/\s+/g, ' ').slice(0, 180) : 'unknown getPair failure';
    throw new Error(`${factoryConfig.venue} block-tagged getPair failed after retries: ${reason}`);
  }
  if (pair.toLowerCase() === ZERO_ADDRESS) {
    throw new Error(`${factoryConfig.venue} returned zero pair for USDC.e/WMATIC`);
  }
  const code = await provider.getCode(pair, blockTag);
  if (code === '0x') {
    throw new Error(`${factoryConfig.venue} pair has no bytecode: ${pair}`);
  }
  return { ...factoryConfig, address: pair };
}

async function readPoolState(provider: ethers.JsonRpcProvider, poolConfig: V2DiscoveredPool, blockTag: number): Promise<LivePoolState> {
  const contract = new ethers.Contract(poolConfig.address, V2_PAIR_ABI, provider);
  const [token0, token1, reserves] = await Promise.all([
    contract.token0({ blockTag }),
    contract.token1({ blockTag }),
    contract.getReserves({ blockTag }),
  ]);

  const reserve0 = BigInt(reserves.reserve0.toString());
  const reserve1 = BigInt(reserves.reserve1.toString());
  const blockTimestampLast = Number(reserves.blockTimestampLast);
  const usdcIs0 = token0.toLowerCase() === USDC.toLowerCase();
  const wmaticIs0 = token0.toLowerCase() === WMATIC.toLowerCase();
  if (!((usdcIs0 && token1.toLowerCase() === WMATIC.toLowerCase()) || (wmaticIs0 && token1.toLowerCase() === USDC.toLowerCase()))) {
    throw new Error(`${poolConfig.id} is not a USDC.e/WMATIC pool at ${poolConfig.address}`);
  }

  const usdcReserve = usdcIs0 ? reserve0 : reserve1;
  const wmaticReserve = wmaticIs0 ? reserve0 : reserve1;
  const priceUsdPerUnit = Number(ethers.formatUnits(usdcReserve, 6)) / Number(ethers.formatUnits(wmaticReserve, 18));

  return { ...poolConfig, token0, token1, reserve0, reserve1, blockTimestampLast, priceUsdPerUnit };
}

function quoteBuy(pool: LivePoolState): QuoteLeg {
  const { reserveIn, reserveOut } = reservesFor(pool, USDC);
  return { pool, tokenIn: USDC, tokenOut: WMATIC, amountIn: INPUT_USDC, amountOut: amountOutV2(INPUT_USDC, reserveIn, reserveOut, 30) };
}

function quoteSell(pool: LivePoolState, amountInWmatic: bigint): QuoteLeg {
  const { reserveIn, reserveOut } = reservesFor(pool, WMATIC);
  return { pool, tokenIn: WMATIC, tokenOut: USDC, amountIn: amountInWmatic, amountOut: amountOutV2(amountInWmatic, reserveIn, reserveOut, 30) };
}

function printPass(name: string, detail: string) {
  console.log(`PASS|${name}|${detail}`);
}

function printFail(name: string, detail: string) {
  console.log(`FAIL|${name}|${detail}`);
}

async function main() {
  const rpcUrl = resolveRpcUrl();
  const provider = new ethers.JsonRpcProvider(rpcUrl, 137, { staticNetwork: true });
  console.log('APEX_OMEGA_LIVE_TRUTH_GATE');
  console.log(`rpcHost=${safeRpcLabel(rpcUrl)}`);
  console.log('submitMode=DISABLED_PROOF_ONLY');

  const network = await provider.getNetwork();
  if (network.chainId !== 137n) {
    printFail('live_discovery_state_read', `wrongChain=${network.chainId.toString()}`);
    process.exitCode = 10;
    return;
  }

  const latestBlock = await provider.getBlockNumber();
  const block = await provider.getBlock(latestBlock);
  if (!block?.hash) {
    printFail('live_discovery_state_read', `missingBlockHash block=${latestBlock}`);
    process.exitCode = 11;
    return;
  }
  printPass('live_discovery_state_read', `chainId=137 block=${latestBlock} blockHash=${block.hash}`);

  const discovered = await Promise.all(V2_FACTORIES.map((factory) => discoverPool(provider, factory, latestBlock)));
  for (const pool of discovered) {
    console.log(`DISCOVERED_POOL|block=${latestBlock}|venue=${pool.venue}|factory=${pool.factory}|pair=${pool.address}`);
  }

  const states = await Promise.all(discovered.map((pool) => readPoolState(provider, pool, latestBlock)));
  for (const state of states) {
    console.log(
      `POOL_STATE|block=${latestBlock}|venue=${state.venue}|pair=USDC.e/WMATIC|priceUsdPerUnit=${state.priceUsdPerUnit.toFixed(8)}|reserve0=${state.reserve0.toString()}|reserve1=${state.reserve1.toString()}`
    );
  }
  printPass('same_block_reserve_hydration', `pools=${states.length} block=${latestBlock}`);

  const candidates = states.flatMap((buyPool) =>
    states
      .filter((sellPool) => sellPool.address.toLowerCase() !== buyPool.address.toLowerCase())
      .map((sellPool) => {
        const buyLeg = quoteBuy(buyPool);
        const sellLeg = quoteSell(sellPool, buyLeg.amountOut);
        const grossDelta = sellLeg.amountOut - INPUT_USDC;
        const buyPrice = Number(ethers.formatUnits(INPUT_USDC, 6)) / Number(ethers.formatUnits(buyLeg.amountOut, 18));
        const sellPrice = Number(ethers.formatUnits(sellLeg.amountOut, 6)) / Number(ethers.formatUnits(buyLeg.amountOut, 18));
        const spreadBps = ((sellPrice / buyPrice) - 1) * 10_000;
        return { buyPool, sellPool, buyLeg, sellLeg, grossDelta, buyPrice, sellPrice, spreadBps };
      })
  ).sort((a, b) => Number(b.grossDelta - a.grossDelta));

  for (const [idx, candidate] of candidates.entries()) {
    console.log(
      `QUOTE_CANDIDATE|rank=${idx + 1}|buy=${candidate.buyPool.venue}|buyUsdPerUnit=${candidate.buyPrice.toFixed(8)}|midOutWMATIC=${ethers.formatUnits(candidate.buyLeg.amountOut, 18)}|sell=${candidate.sellPool.venue}|sellUsdPerUnit=${candidate.sellPrice.toFixed(8)}|usdcOut=${ethers.formatUnits(candidate.sellLeg.amountOut, 6)}|grossDeltaUsdc=${ethers.formatUnits(candidate.grossDelta, 6)}|spreadBps=${candidate.spreadBps.toFixed(4)}`
    );
  }

  const best = candidates[0];
  if (!best) {
    printFail('exact_quote_simulation', 'no two-pool route candidates available');
    console.log('VERDICT=BLOCKED_BEFORE_SUBMIT');
    process.exitCode = 20;
    return;
  }

  if (!(best.buyPrice < best.sellPrice && best.grossDelta > 0n)) {
    printFail('exact_quote_simulation', 'best executable route is not profitable after AMM fee and price impact');
    console.log('VERDICT=BLOCKED_BEFORE_SUBMIT');
    process.exitCode = 20;
    return;
  }
  printPass('exact_quote_simulation', `grossDeltaUsdc=${ethers.formatUnits(best.grossDelta, 6)}`);

  const executorCode = await provider.getCode(EXECUTOR, latestBlock);
  if (executorCode === '0x') {
    printFail('eth_call_against_executor', `noCodeAtExecutor=${EXECUTOR}`);
    console.log('VERDICT=BLOCKED_BEFORE_SUBMIT');
    process.exitCode = 21;
    return;
  }

  const iface = new ethers.Interface(EXECUTOR_ABI);
  const calldata = iface.encodeFunctionData('executeArbitrage', [[USDC, WMATIC, USDC], INPUT_USDC, MIN_PROFIT_USDC, '0x']);

  try {
    const callResult = await provider.call({ from: BOT, to: EXECUTOR, data: calldata, value: 0n }, latestBlock);
    printPass('eth_call_against_executor', `resultBytes=${(callResult.length - 2) / 2}`);
    console.log('VERDICT=PASS_TO_LIVE_SUBMIT');
  } catch (err) {
    const reason = err instanceof Error ? err.message.replace(/\s+/g, ' ').slice(0, 260) : 'unknown eth_call failure';
    printFail('eth_call_against_executor', reason);
    console.log('VERDICT=BLOCKED_BEFORE_SUBMIT');
    process.exitCode = 22;
  }
}

main().catch((err) => {
  const reason = err instanceof Error ? err.message.replace(/\s+/g, ' ').slice(0, 300) : String(err);
  printFail('live_truth_gate_exception', reason);
  console.log('VERDICT=BLOCKED_BEFORE_SUBMIT');
  process.exitCode = 99;
});


