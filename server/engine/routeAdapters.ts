import { ethers } from "ethers";
import { InvariantMath } from "./invariants.js";

export type InvariantKind =
  | "V2_CPMM"
  | "V3_CONCENTRATED_LIQUIDITY"
  | "ALGEBRA_CONCENTRATED_LIQUIDITY"
  | "CURVE_STABLE_SWAP"
  | "BALANCER_WEIGHTED"
  | "STABLE_SWAP";

export type RouteAdapterCapability = {
  poolType: InvariantKind;
  discoverySource: string;
  stateReader: string;
  quoteAdapter: string;
  calldataAdapter: string;
  forkSimulation: string;
  preSendRevalidation: string;
  adapterPresent: boolean;
  executable: boolean;
  rejectionReason?: string;
};

export type TokenNode = {
  chainId: 137;
  address: string;
  symbol: string;
  decimals: number;
  priceUsd?: number;
};

export type PoolEdge = {
  chainId: 137;
  dexId: string;
  poolAddress: string;
  poolId?: string;
  tokenIn: string;
  tokenOut: string;
  tokenInIndex?: number;
  tokenOutIndex?: number;
  tokenInDecimals: number;
  tokenOutDecimals: number;
  invariant: InvariantKind;
  feeBps: number;
  reserveIn: bigint;
  reserveOut: bigint;
  tvlUsd: number;
  stateBlock: number;
  quoteAdapter: string;
  calldataAdapter: string;
  executorTarget: string;
};

export const ERC20_METADATA_ABI = [
  "function decimals() view returns (uint8)",
  "function symbol() view returns (string)",
];

export const UNISWAP_V2_FACTORY_ABI = [
  "event PairCreated(address indexed token0, address indexed token1, address pair, uint256)",
];

export const UNISWAP_V2_PAIR_ABI = [
  "function token0() view returns (address)",
  "function token1() view returns (address)",
  "function getReserves() view returns (uint112 reserve0,uint112 reserve1,uint32 blockTimestampLast)",
];

export const UNISWAP_V2_ROUTER_ABI = [
  "function swapExactTokensForTokens(uint256 amountIn,uint256 amountOutMin,address[] path,address to,uint256 deadline) returns (uint256[] amounts)",
];

export const UNISWAP_V3_FACTORY_ABI = [
  "event PoolCreated(address indexed token0,address indexed token1,uint24 indexed fee,int24 tickSpacing,address pool)",
];

export const UNISWAP_V3_POOL_ABI = [
  "function token0() view returns (address)",
  "function token1() view returns (address)",
  "function fee() view returns (uint24)",
  "function liquidity() view returns (uint128)",
  "function slot0() view returns (uint160 sqrtPriceX96,int24 tick,uint16 observationIndex,uint16 observationCardinality,uint16 observationCardinalityNext,uint8 feeProtocol,bool unlocked)",
];

export const UNISWAP_V3_QUOTER_ABI = [
  "function quoteExactInputSingle(address tokenIn,address tokenOut,uint24 fee,uint256 amountIn,uint160 sqrtPriceLimitX96) returns (uint256 amountOut)",
];

export const UNISWAP_V3_SWAP_ROUTER_ABI = [
  "function exactInputSingle((address tokenIn,address tokenOut,uint24 fee,address recipient,uint256 deadline,uint256 amountIn,uint256 amountOutMinimum,uint160 sqrtPriceLimitX96)) payable returns (uint256 amountOut)",
];

export const ALGEBRA_POOL_ABI = [
  "function token0() view returns (address)",
  "function token1() view returns (address)",
  "function liquidity() view returns (uint128)",
  "function globalState() view returns (uint160 price,int24 tick,uint16 fee,uint16 timepointIndex,uint8 communityFeeToken0,uint8 communityFeeToken1,bool unlocked)",
];

export const ALGEBRA_FACTORY_ABI = [
  "event Pool(address indexed token0,address indexed token1,address pool)",
  "function poolByPair(address tokenA,address tokenB) view returns (address pool)",
];

export const ALGEBRA_QUOTER_ABI = [
  "function quoteExactInputSingle(address tokenIn,address tokenOut,uint256 amountIn,uint160 limitSqrtPrice) returns (uint256 amountOut,uint16 fee)",
];

export const ALGEBRA_SWAP_ROUTER_ABI = [
  "function exactInputSingle((address tokenIn,address tokenOut,address recipient,uint256 deadline,uint256 amountIn,uint256 amountOutMinimum,uint160 limitSqrtPrice)) payable returns (uint256 amountOut)",
];

export const BALANCER_VAULT_ABI = [
  "event PoolRegistered(bytes32 indexed poolId,address indexed poolAddress,uint8 specialization)",
  "function getPoolTokens(bytes32 poolId) view returns (address[] tokens,uint256[] balances,uint256 lastChangeBlock)",
  "function queryBatchSwap(uint8 kind,(bytes32 poolId,uint256 assetInIndex,uint256 assetOutIndex,uint256 amount,bytes userData)[] swaps,address[] assets,(address sender,bool fromInternalBalance,address recipient,bool toInternalBalance) funds) returns (int256[] assetDeltas)",
  "function swap((bytes32 poolId,uint8 kind,address assetIn,address assetOut,uint256 amount,bytes userData),(address sender,bool fromInternalBalance,address recipient,bool toInternalBalance),uint256 limit,uint256 deadline) payable returns (uint256 amountCalculated)",
];

export const BALANCER_WEIGHTED_POOL_ABI = [
  "function getNormalizedWeights() view returns (uint256[])",
  "function getSwapFeePercentage() view returns (uint256)",
];

export const CURVE_ADDRESS_PROVIDER_ABI = [
  "function get_registry() view returns (address)",
  "function get_address(uint256 id) view returns (address)",
];

export const CURVE_REGISTRY_ABI = [
  "function pool_count() view returns (uint256)",
  "function pool_list(uint256 index) view returns (address)",
  "function get_coins(address pool) view returns (address[8])",
  "function get_balances(address pool) view returns (uint256[8])",
];

export const CURVE_POOL_QUOTE_ABI = [
  "function get_dy(int128 i,int128 j,uint256 dx) view returns (uint256)",
  "function get_dy(uint256 i,uint256 j,uint256 dx) view returns (uint256)",
];

export const CURVE_ROUTER_ABI = [
  "function exchange(address pool,address tokenIn,address tokenOut,uint256 amountIn,uint256 minAmountOut,address receiver) returns (uint256 amountOut)",
];

export const STABLE_SWAP_POOL_ABI = [
  "function balances(uint256 i) view returns (uint256)",
  "function get_dy(int128 i,int128 j,uint256 dx) view returns (uint256)",
  "function exchange(int128 i,int128 j,uint256 dx,uint256 min_dy) returns (uint256)",
];

export const ROUTE_ADAPTER_TARGETS = {
  uniswapV3Quoter: process.env.UNISWAP_V3_QUOTER || "0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6",
  uniswapV3Router: process.env.UNISWAP_V3_ROUTER || "0xE592427A0AEce92De3Edee1F18E0157C05861564",
  algebraFactory: process.env.ALGEBRA_FACTORY || process.env.QUICKSWAP_V3_FACTORY || "0x411b0fAcC3489691f28ad58c47006AF5E3Ab3A28",
  algebraQuoter: process.env.ALGEBRA_QUOTER || process.env.QUICKSWAP_V3_QUOTER || "0xa15F0D7377B2A0C0c10db057f641beD21028FC89",
  algebraRouter: process.env.ALGEBRA_ROUTER || process.env.QUICKSWAP_V3_ROUTER || "0xf5b509bB0909a69B1c207E495f687a596C168E12",
  curveRouter: process.env.CURVE_ROUTER || "0x1d8b86e3D88cDb2d34688e87E72F388Cb541B7C8",
  balancerVault: process.env.BALANCER_VAULT || "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
};

const forkProviderCache = new Map<string, ethers.JsonRpcProvider>();

function getForkProvider(forkRpcUrl: string): ethers.JsonRpcProvider {
  const cached = forkProviderCache.get(forkRpcUrl);
  if (cached) return cached;
  const provider = new ethers.JsonRpcProvider(forkRpcUrl, 137, { staticNetwork: true });
  forkProviderCache.set(forkRpcUrl, provider);
  return provider;
}

function hasForkSimulator(): boolean {
  return Boolean(process.env.FORK_SIM_RPC_URL);
}

function requiredAddressPresent(address: string): boolean {
  return typeof address === "string" && /^0x[a-fA-F0-9]{40}$/.test(address);
}

function sameAddress(left: string, right: string): boolean {
  return ethers.getAddress(left) === ethers.getAddress(right);
}

function containsBothTokens(token0: string, token1: string, edge: PoolEdge): boolean {
  return (sameAddress(token0, edge.tokenIn) && sameAddress(token1, edge.tokenOut))
    || (sameAddress(token0, edge.tokenOut) && sameAddress(token1, edge.tokenIn));
}

function tupleValue(result: any, key: string, index: number) {
  return result?.[key] ?? result?.[index];
}

async function resolveCurveRegistry(provider: ethers.Provider): Promise<string> {
  if (process.env.CURVE_REGISTRY && requiredAddressPresent(process.env.CURVE_REGISTRY)) {
    return ethers.getAddress(process.env.CURVE_REGISTRY);
  }
  const addressProvider = process.env.CURVE_ADDRESS_PROVIDER || "0x0000000022D53366457F9d5E68Ec105046FC4383";
  const providerContract = new ethers.Contract(addressProvider, CURVE_ADDRESS_PROVIDER_ABI, provider);
  return ethers.getAddress(await providerContract.get_registry());
}

export const routeAdapterCapabilities: RouteAdapterCapability[] = [
  {
    poolType: "V2_CPMM",
    discoverySource: "V2 PairCreated events",
    stateReader: "token0/token1/getReserves",
    quoteAdapter: "InvariantMath.getAmountOutConstantProduct",
    calldataAdapter: "UniswapV2Router.swapExactTokensForTokens",
    forkSimulation: "simulateExactCalldataOnFork",
    preSendRevalidation: "revalidateV2Reserves",
    adapterPresent: true,
    executable: hasForkSimulator(),
    rejectionReason: hasForkSimulator() ? undefined : "FORK_SIM_RPC_URL_MISSING",
  },
  {
    poolType: "V3_CONCENTRATED_LIQUIDITY",
    discoverySource: "V3 PoolCreated events",
    stateReader: "slot0/liquidity/fee",
    quoteAdapter: "quoteV3ExactInputSingle",
    calldataAdapter: "SwapRouter.exactInput/exactInputSingle",
    forkSimulation: "simulateExactCalldataOnFork",
    preSendRevalidation: "revalidateV3Slot0Liquidity",
    adapterPresent: true,
    executable: hasForkSimulator() && requiredAddressPresent(ROUTE_ADAPTER_TARGETS.uniswapV3Quoter) && requiredAddressPresent(ROUTE_ADAPTER_TARGETS.uniswapV3Router),
    rejectionReason: hasForkSimulator() ? undefined : "FORK_SIM_RPC_URL_MISSING",
  },
  {
    poolType: "ALGEBRA_CONCENTRATED_LIQUIDITY",
    discoverySource: "Algebra pool events",
    stateReader: "globalState/liquidity",
    quoteAdapter: "quoteAlgebraExactInputSingle",
    calldataAdapter: "AlgebraRouter.exactInput",
    forkSimulation: "simulateExactCalldataOnFork",
    preSendRevalidation: "revalidateAlgebraGlobalStateLiquidity",
    adapterPresent: true,
    executable: hasForkSimulator() && requiredAddressPresent(ROUTE_ADAPTER_TARGETS.algebraQuoter) && requiredAddressPresent(ROUTE_ADAPTER_TARGETS.algebraRouter),
    rejectionReason: !requiredAddressPresent(ROUTE_ADAPTER_TARGETS.algebraQuoter) ? "ALGEBRA_QUOTER_ADDRESS_MISSING" : hasForkSimulator() ? undefined : "FORK_SIM_RPC_URL_MISSING",
  },
  {
    poolType: "CURVE_STABLE_SWAP",
    discoverySource: "Curve Address Provider / Registry / Factory Registry",
    stateReader: "get_coins/get_balances/pool-specific A",
    quoteAdapter: "quoteCurveGetDy",
    calldataAdapter: "Curve exchange/exchange_underlying adapter",
    forkSimulation: "simulateExactCalldataOnFork",
    preSendRevalidation: "revalidateCurveBalances",
    adapterPresent: true,
    executable: hasForkSimulator() && requiredAddressPresent(ROUTE_ADAPTER_TARGETS.curveRouter),
    rejectionReason: hasForkSimulator() ? undefined : "FORK_SIM_RPC_URL_MISSING",
  },
  {
    poolType: "BALANCER_WEIGHTED",
    discoverySource: "Balancer Vault PoolRegistered events",
    stateReader: "Vault.getPoolTokens + getNormalizedWeights + getSwapFeePercentage",
    quoteAdapter: "InvariantMath.getAmountOutBalancerWeighted",
    calldataAdapter: "Vault.swap SingleSwap adapter",
    forkSimulation: "simulateExactCalldataOnFork",
    preSendRevalidation: "revalidateBalancerPoolTokensWeights",
    adapterPresent: true,
    executable: hasForkSimulator() && requiredAddressPresent(ROUTE_ADAPTER_TARGETS.balancerVault),
    rejectionReason: hasForkSimulator() ? undefined : "FORK_SIM_RPC_URL_MISSING",
  },
  {
    poolType: "STABLE_SWAP",
    discoverySource: "Stable factory events / registry",
    stateReader: "pool balances/amplification",
    quoteAdapter: "quoteStableSwapGetDy",
    calldataAdapter: "pool-specific swap adapter",
    forkSimulation: "simulateExactCalldataOnFork",
    preSendRevalidation: "revalidateStableSwapBalances",
    adapterPresent: true,
    executable: hasForkSimulator(),
    rejectionReason: hasForkSimulator() ? undefined : "FORK_SIM_RPC_URL_MISSING",
  },
];

export function quoteV2Cpmm(amountIn: bigint, reserveIn: bigint, reserveOut: bigint, feeBps: number): bigint {
  return InvariantMath.getAmountOutConstantProduct(amountIn, {
    reserveIn,
    reserveOut,
    feeBps: BigInt(feeBps),
  });
}

export function buildV2SwapCalldata(amountIn: bigint, minAmountOut: bigint, path: string[], receiver: string, deadline: number): string {
  const iface = new ethers.Interface(UNISWAP_V2_ROUTER_ABI);
  return iface.encodeFunctionData("swapExactTokensForTokens", [
    amountIn,
    minAmountOut,
    path.map((address) => ethers.getAddress(address)),
    ethers.getAddress(receiver),
    deadline,
  ]);
}

export async function quoteV3ExactInputSingle(provider: ethers.Provider, params: {
  quoter?: string;
  tokenIn: string;
  tokenOut: string;
  fee: number;
  amountIn: bigint;
  sqrtPriceLimitX96?: bigint;
}): Promise<bigint> {
  const quoter = params.quoter || ROUTE_ADAPTER_TARGETS.uniswapV3Quoter;
  if (!requiredAddressPresent(quoter)) throw new Error("V3_QUOTER_ADDRESS_MISSING");
  const contract = new ethers.Contract(quoter, UNISWAP_V3_QUOTER_ABI, provider);
  return await contract.quoteExactInputSingle.staticCall(
    ethers.getAddress(params.tokenIn),
    ethers.getAddress(params.tokenOut),
    params.fee,
    params.amountIn,
    params.sqrtPriceLimitX96 || 0n,
  );
}

export function buildV3ExactInputSingleCalldata(params: {
  tokenIn: string;
  tokenOut: string;
  fee: number;
  receiver: string;
  deadline: number;
  amountIn: bigint;
  minAmountOut: bigint;
  sqrtPriceLimitX96?: bigint;
}): string {
  const iface = new ethers.Interface(UNISWAP_V3_SWAP_ROUTER_ABI);
  return iface.encodeFunctionData("exactInputSingle", [{
    tokenIn: ethers.getAddress(params.tokenIn),
    tokenOut: ethers.getAddress(params.tokenOut),
    fee: params.fee,
    recipient: ethers.getAddress(params.receiver),
    deadline: params.deadline,
    amountIn: params.amountIn,
    amountOutMinimum: params.minAmountOut,
    sqrtPriceLimitX96: params.sqrtPriceLimitX96 || 0n,
  }]);
}

export async function quoteAlgebraExactInputSingle(provider: ethers.Provider, params: {
  quoter?: string;
  tokenIn: string;
  tokenOut: string;
  amountIn: bigint;
  limitSqrtPrice?: bigint;
}): Promise<bigint> {
  const quoter = params.quoter || ROUTE_ADAPTER_TARGETS.algebraQuoter;
  if (!requiredAddressPresent(quoter)) throw new Error("ALGEBRA_QUOTER_ADDRESS_MISSING");
  const contract = new ethers.Contract(quoter, ALGEBRA_QUOTER_ABI, provider);
  const result = await contract.quoteExactInputSingle.staticCall(
    ethers.getAddress(params.tokenIn),
    ethers.getAddress(params.tokenOut),
    params.amountIn,
    params.limitSqrtPrice || 0n,
  );
  return Array.isArray(result) ? result[0] : result;
}

export function buildAlgebraExactInputSingleCalldata(params: {
  tokenIn: string;
  tokenOut: string;
  receiver: string;
  deadline: number;
  amountIn: bigint;
  minAmountOut: bigint;
  limitSqrtPrice?: bigint;
}): string {
  const iface = new ethers.Interface(ALGEBRA_SWAP_ROUTER_ABI);
  return iface.encodeFunctionData("exactInputSingle", [{
    tokenIn: ethers.getAddress(params.tokenIn),
    tokenOut: ethers.getAddress(params.tokenOut),
    recipient: ethers.getAddress(params.receiver),
    deadline: params.deadline,
    amountIn: params.amountIn,
    amountOutMinimum: params.minAmountOut,
    limitSqrtPrice: params.limitSqrtPrice || 0n,
  }]);
}

export async function quoteCurveGetDy(provider: ethers.Provider, params: {
  pool: string;
  i: number;
  j: number;
  amountIn: bigint;
  indexType?: "int128" | "uint256";
}): Promise<bigint> {
  const signature = params.indexType === "uint256"
    ? "function get_dy(uint256 i,uint256 j,uint256 dx) view returns (uint256)"
    : "function get_dy(int128 i,int128 j,uint256 dx) view returns (uint256)";
  const contract = new ethers.Contract(params.pool, [signature], provider);
  return await contract.get_dy(params.i, params.j, params.amountIn);
}

export function buildCurveRouterExchangeCalldata(params: {
  pool: string;
  tokenIn: string;
  tokenOut: string;
  amountIn: bigint;
  minAmountOut: bigint;
  receiver: string;
}): string {
  const iface = new ethers.Interface(CURVE_ROUTER_ABI);
  return iface.encodeFunctionData("exchange", [
    ethers.getAddress(params.pool),
    ethers.getAddress(params.tokenIn),
    ethers.getAddress(params.tokenOut),
    params.amountIn,
    params.minAmountOut,
    ethers.getAddress(params.receiver),
  ]);
}

export function quoteBalancerWeighted(amountIn: bigint, params: {
  balanceIn: bigint;
  balanceOut: bigint;
  weightIn: bigint;
  weightOut: bigint;
  swapFeeBps: bigint;
}): bigint {
  return InvariantMath.getAmountOutBalancerWeighted(amountIn, params);
}

export function buildBalancerSingleSwapCalldata(params: {
  poolId: string;
  tokenIn: string;
  tokenOut: string;
  amountIn: bigint;
  minAmountOut: bigint;
  sender: string;
  receiver: string;
  deadline: number;
}): string {
  const iface = new ethers.Interface(BALANCER_VAULT_ABI);
  return iface.encodeFunctionData("swap", [
    {
      poolId: params.poolId,
      kind: 0,
      assetIn: ethers.getAddress(params.tokenIn),
      assetOut: ethers.getAddress(params.tokenOut),
      amount: params.amountIn,
      userData: "0x",
    },
    {
      sender: ethers.getAddress(params.sender),
      fromInternalBalance: false,
      recipient: ethers.getAddress(params.receiver),
      toInternalBalance: false,
    },
    params.minAmountOut,
    params.deadline,
  ]);
}

export async function quoteStableSwapGetDy(provider: ethers.Provider, params: {
  pool: string;
  i: number;
  j: number;
  amountIn: bigint;
}): Promise<bigint> {
  const contract = new ethers.Contract(params.pool, STABLE_SWAP_POOL_ABI, provider);
  return await contract.get_dy(params.i, params.j, params.amountIn);
}

export function buildStableSwapExchangeCalldata(params: {
  i: number;
  j: number;
  amountIn: bigint;
  minAmountOut: bigint;
}): string {
  const iface = new ethers.Interface(STABLE_SWAP_POOL_ABI);
  return iface.encodeFunctionData("exchange", [
    params.i,
    params.j,
    params.amountIn,
    params.minAmountOut,
  ]);
}

export async function simulateExactCalldataOnFork(params: {
  to: string;
  from: string;
  data: string;
  value?: bigint;
  forkRpcUrl?: string;
}): Promise<{ ok: boolean; returnData?: string; error?: string }> {
  const forkRpcUrl = params.forkRpcUrl || process.env.FORK_SIM_RPC_URL;
  if (!forkRpcUrl) return { ok: false, error: "FORK_SIM_RPC_URL_MISSING" };
  const provider = getForkProvider(forkRpcUrl);
  try {
    const result = await provider.call({
      to: ethers.getAddress(params.to),
      from: ethers.getAddress(params.from),
      data: params.data,
      value: params.value || 0n,
    });
    return { ok: true, returnData: result };
  } catch (error: any) {
    return { ok: false, error: error?.reason || error?.shortMessage || error?.message || "FORK_SIMULATION_FAILED" };
  }
}

async function revalidateV2Reserves(provider: ethers.Provider, edge: PoolEdge): Promise<{ ok: boolean; error?: string }> {
  const pair = new ethers.Contract(edge.poolAddress, UNISWAP_V2_PAIR_ABI, provider);
  const [token0, token1, reserves] = await Promise.all([
    pair.token0(),
    pair.token1(),
    pair.getReserves(),
  ]);
  if (!containsBothTokens(token0, token1, edge)) return { ok: false, error: "V2_PAIR_TOKEN_MISMATCH" };
  const reserveIn = sameAddress(token0, edge.tokenIn) ? BigInt(reserves.reserve0) : BigInt(reserves.reserve1);
  const reserveOut = sameAddress(token0, edge.tokenOut) ? BigInt(reserves.reserve0) : BigInt(reserves.reserve1);
  if (reserveIn <= 0n || reserveOut <= 0n) return { ok: false, error: "V2_ZERO_LIVE_RESERVES" };
  return { ok: true };
}

async function revalidateV3Slot0Liquidity(provider: ethers.Provider, edge: PoolEdge): Promise<{ ok: boolean; error?: string }> {
  const pool = new ethers.Contract(edge.poolAddress, UNISWAP_V3_POOL_ABI, provider);
  const [token0, token1, fee, liquidity, slot0] = await Promise.all([
    pool.token0(),
    pool.token1(),
    pool.fee(),
    pool.liquidity(),
    pool.slot0(),
  ]);
  if (!containsBothTokens(token0, token1, edge)) return { ok: false, error: "V3_POOL_TOKEN_MISMATCH" };
  if (Math.max(1, Math.floor(Number(fee) / 100)) !== edge.feeBps && edge.feeBps > 0) return { ok: false, error: "V3_FEE_MISMATCH" };
  if (BigInt(liquidity) <= 0n) return { ok: false, error: "V3_ZERO_LIQUIDITY" };
  if (BigInt(tupleValue(slot0, "sqrtPriceX96", 0)) <= 0n || Boolean(tupleValue(slot0, "unlocked", 6)) === false) return { ok: false, error: "V3_INVALID_SLOT0" };
  return { ok: true };
}

async function revalidateAlgebraGlobalStateLiquidity(provider: ethers.Provider, edge: PoolEdge): Promise<{ ok: boolean; error?: string }> {
  const pool = new ethers.Contract(edge.poolAddress, ALGEBRA_POOL_ABI, provider);
  const [token0, token1, liquidity, globalState] = await Promise.all([
    pool.token0(),
    pool.token1(),
    pool.liquidity(),
    pool.globalState(),
  ]);
  if (!containsBothTokens(token0, token1, edge)) return { ok: false, error: "ALGEBRA_POOL_TOKEN_MISMATCH" };
  if (BigInt(liquidity) <= 0n) return { ok: false, error: "ALGEBRA_ZERO_LIQUIDITY" };
  if (BigInt(tupleValue(globalState, "price", 0)) <= 0n || Boolean(tupleValue(globalState, "unlocked", 6)) === false) return { ok: false, error: "ALGEBRA_INVALID_GLOBAL_STATE" };
  return { ok: true };
}

async function revalidateCurveBalances(provider: ethers.Provider, edge: PoolEdge): Promise<{ ok: boolean; error?: string }> {
  if (edge.tokenInIndex === undefined || edge.tokenOutIndex === undefined) {
    return { ok: false, error: "CURVE_TOKEN_INDEX_MISSING" };
  }
  const registryAddress = await resolveCurveRegistry(provider);
  const registry = new ethers.Contract(registryAddress, CURVE_REGISTRY_ABI, provider);
  const [coins, balances] = await Promise.all([
    registry.get_coins(edge.poolAddress),
    registry.get_balances(edge.poolAddress),
  ]);
  const coinIn = coins[edge.tokenInIndex];
  const coinOut = coins[edge.tokenOutIndex];
  if (!sameAddress(coinIn, edge.tokenIn) || !sameAddress(coinOut, edge.tokenOut)) {
    return { ok: false, error: "CURVE_REGISTRY_TOKEN_MISMATCH" };
  }
  if (BigInt(balances[edge.tokenInIndex]) <= 0n || BigInt(balances[edge.tokenOutIndex]) <= 0n) {
    return { ok: false, error: "CURVE_ZERO_LIVE_BALANCE" };
  }
  return { ok: true };
}

async function revalidateBalancerPoolTokensWeights(provider: ethers.Provider, edge: PoolEdge): Promise<{ ok: boolean; error?: string }> {
  if (!edge.poolId) return { ok: false, error: "BALANCER_POOL_ID_MISSING" };
  const vault = new ethers.Contract(ROUTE_ADAPTER_TARGETS.balancerVault, BALANCER_VAULT_ABI, provider);
  const weightedPool = new ethers.Contract(edge.poolAddress, BALANCER_WEIGHTED_POOL_ABI, provider);
  const [poolTokens, weights] = await Promise.all([
    vault.getPoolTokens(edge.poolId),
    weightedPool.getNormalizedWeights(),
  ]);
  const tokens = Array.from(poolTokens.tokens as string[]);
  const balances = Array.from(poolTokens.balances as bigint[]);
  const inIndex = tokens.findIndex((token) => sameAddress(token, edge.tokenIn));
  const outIndex = tokens.findIndex((token) => sameAddress(token, edge.tokenOut));
  if (inIndex < 0 || outIndex < 0) return { ok: false, error: "BALANCER_TOKEN_MISSING" };
  if (BigInt(balances[inIndex]) <= 0n || BigInt(balances[outIndex]) <= 0n) return { ok: false, error: "BALANCER_ZERO_LIVE_BALANCE" };
  if (BigInt(weights[inIndex]) <= 0n || BigInt(weights[outIndex]) <= 0n) return { ok: false, error: "BALANCER_WEIGHT_MISSING" };
  return { ok: true };
}

async function revalidateStableSwapBalances(provider: ethers.Provider, edge: PoolEdge): Promise<{ ok: boolean; error?: string }> {
  if (edge.tokenInIndex === undefined || edge.tokenOutIndex === undefined) {
    return { ok: false, error: "STABLE_SWAP_TOKEN_INDEX_MISSING" };
  }
  const pool = new ethers.Contract(edge.poolAddress, STABLE_SWAP_POOL_ABI, provider);
  const [balanceIn, balanceOut] = await Promise.all([
    pool.balances(edge.tokenInIndex),
    pool.balances(edge.tokenOutIndex),
  ]);
  if (BigInt(balanceIn) <= 0n || BigInt(balanceOut) <= 0n) return { ok: false, error: "STABLE_SWAP_ZERO_LIVE_BALANCE" };
  return { ok: true };
}

export async function preSendRevalidate(
  provider: ethers.Provider,
  edge: PoolEdge,
  maxStateAgeBlocks = 2,
  knownCurrentBlock?: number,
): Promise<{ ok: boolean; error?: string; currentBlock?: number; stateRefreshed?: boolean }> {
  const currentBlock = knownCurrentBlock ?? await provider.getBlockNumber();
  const stateRefreshed = currentBlock - edge.stateBlock > maxStateAgeBlocks;
  if (edge.reserveIn <= 0n || edge.reserveOut <= 0n) {
    return { ok: false, error: "POOL_ZERO_LIQUIDITY", currentBlock };
  }
  if (!edge.calldataAdapter || !edge.quoteAdapter) {
    return { ok: false, error: "POOL_ADAPTER_MISSING", currentBlock };
  }
  const adapter = routeAdapterCapabilities.find((item) => item.poolType === edge.invariant);
  if (!adapter?.adapterPresent) return { ok: false, error: "POOL_ADAPTER_UNSUPPORTED", currentBlock };
  try {
    const result = edge.invariant === "V2_CPMM"
      ? await revalidateV2Reserves(provider, edge)
      : edge.invariant === "V3_CONCENTRATED_LIQUIDITY"
        ? await revalidateV3Slot0Liquidity(provider, edge)
        : edge.invariant === "ALGEBRA_CONCENTRATED_LIQUIDITY"
          ? await revalidateAlgebraGlobalStateLiquidity(provider, edge)
          : edge.invariant === "CURVE_STABLE_SWAP"
            ? await revalidateCurveBalances(provider, edge)
            : edge.invariant === "BALANCER_WEIGHTED"
              ? await revalidateBalancerPoolTokensWeights(provider, edge)
              : await revalidateStableSwapBalances(provider, edge);
    return result.ok ? { ok: true, currentBlock, stateRefreshed } : { ...result, currentBlock };
  } catch (error: any) {
    return { ok: false, error: error?.reason || error?.shortMessage || error?.message || "PRE_SEND_REVALIDATION_FAILED", currentBlock };
  }
}

export function hardRejectUnsupportedAdapter(poolType: InvariantKind): void {
  const adapter = routeAdapterCapabilities.find((item) => item.poolType === poolType);
  if (!adapter || !adapter.adapterPresent || !adapter.executable) {
    throw new Error(adapter?.rejectionReason || `UNSUPPORTED_POOL_TYPE:${poolType}`);
  }
}
