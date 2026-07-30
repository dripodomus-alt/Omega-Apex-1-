import "dotenv/config";
import fs from "fs";
import path from "path";
import { ethers } from "ethers";

const POLYGON_CHAIN_ID = 137n;
const USDC = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174";
const WETH = "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619";
const QUICKSWAP_FACTORY = "0x5757371414417b8c6caad45baef941abc7d3ab32";
const SUSHISWAP_FACTORY = "0xc35DADB65012eC5796536bD9864eD8773aBc74C4";
const QUICKSWAP_ROUTER = "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff";
const SUSHISWAP_ROUTER = "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506";
const TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef";
const DEFAULT_TEST_HASHES = [
  "0xe686bea881014e7e50db3e378a9999fe49e26a4de6c1dde4b76962e83f4a0c9d",
  "0xdf964b9a77fa7cda958d13f917244eec7f284e62c0fef66b3aafe4aa158c8b6c",
  "0xf6a633c7d5b449dd3dc56183a3cafc130a87e14ae9c2e73ee418b03cf562d1e7",
];
const DEFAULT_FLASHLOAN_SOURCE_AAVE_V3 = 1;

const FACTORY_ABI = ["function getPair(address,address) view returns (address)"];
const PAIR_ABI = [
  "function token0() view returns (address)",
  "function token1() view returns (address)",
  "function getReserves() view returns (uint112 reserve0,uint112 reserve1,uint32 blockTimestampLast)",
];
const ERC20_ABI = [
  "function balanceOf(address) view returns (uint256)",
  "function decimals() view returns (uint8)",
  "function symbol() view returns (string)",
];
const VM_ABI = [
  "function owner() view returns (address)",
  "function globalNonce() view returns (uint256)",
  "function aaveV3Pool() view returns (address)",
  "function executeC1(uint8 flashloanSource, address flashloanAsset, uint256 flashloanAmount, tuple(address profitAsset,uint256 minNetProfit,uint256 nonce,bytes32 merkleRoot,bytes32[] proof,tuple(address venue,address tokenIn,address tokenOut,uint256 amountIn,uint256 minAmountOut,uint256 callValue,bytes payload)[] steps) context) external",
];
const ROUTER_ABI = [
  "function swapExactTokensForTokens(uint256 amountIn,uint256 amountOutMin,address[] path,address to,uint256 deadline) returns (uint256[] amounts)",
];

type Config = Record<string, unknown>;

type PairState = {
  label: string;
  pair: string;
  router: string;
  token0: string;
  token1: string;
  reserve0: bigint;
  reserve1: bigint;
};

type RouteQuote = {
  route: string;
  amountInRaw: bigint;
  wethOut: bigint;
  usdcOut: bigint;
  grossProfitRaw: bigint;
  profitableBeforeGas: boolean;
  first: PairState;
  second: PairState;
};

function readConfig(): Config {
  const configPath = path.join(process.cwd(), "config.json");
  if (!fs.existsSync(configPath)) return {};
  return JSON.parse(fs.readFileSync(configPath, "utf-8"));
}

function firstString(...values: unknown[]): string | undefined {
  return values.find((value): value is string => typeof value === "string" && value.trim().length > 0)?.trim();
}

function getRpcUrl(cfg: Config): string {
  const url = firstString(
    process.env.POLYGON_RPC_URL,
    process.env.POLYGON_RPC,
    process.env.RPC_URL,
    cfg.POLYGON_RPC_URL,
    cfg.DRPC_HTTP,
    cfg.PUBLIC_1RPC,
    cfg.PUBLIC_LLAMA,
    "https://polygon-bor-rpc.publicnode.com",
  );
  if (!url) throw new Error("POLYGON_RPC_URL_REQUIRED");
  if (url.includes("YOUR_")) throw new Error("POLYGON_RPC_URL_PLACEHOLDER");
  return url;
}

function normalizeAddressLoose(value: string): string {
  if (!/^0x[a-fA-F0-9]{40}$/.test(value)) throw new Error(`INVALID_ADDRESS:${value}`);
  return ethers.getAddress(value.toLowerCase());
}

function topicForAddress(address: string): string {
  return `0x${address.toLowerCase().replace(/^0x/, "").padStart(64, "0")}`;
}

function amountOutV2(amountIn: bigint, reserveIn: bigint, reserveOut: bigint, feeBps = 30n): bigint {
  if (amountIn <= 0n || reserveIn <= 0n || reserveOut <= 0n) return 0n;
  const amountInWithFee = amountIn * (10_000n - feeBps);
  return (amountInWithFee * reserveOut) / ((reserveIn * 10_000n) + amountInWithFee);
}

function formatUnits(raw: bigint, decimals: number): string {
  return ethers.formatUnits(raw, decimals);
}

function parseHashes(): string[] {
  const arg = process.argv.find((item) => item.startsWith("--hashes="));
  const raw = firstString(arg?.slice("--hashes=".length), process.env.STRATEGY_PROOF_HASHES);
  const hashes = raw ? raw.split(",").map((item) => item.trim()).filter(Boolean) : DEFAULT_TEST_HASHES;
  return hashes.filter((hash) => /^0x[a-fA-F0-9]{64}$/.test(hash));
}

async function getPairState(provider: ethers.JsonRpcProvider, label: string, factoryAddress: string, router: string): Promise<PairState> {
  const factory = new ethers.Contract(factoryAddress, FACTORY_ABI, provider);
  const pair = await factory.getPair(USDC, WETH);
  const code = await provider.getCode(pair);
  if (code === "0x") throw new Error(`${label}_PAIR_HAS_NO_CODE:${pair}`);
  const pairContract = new ethers.Contract(pair, PAIR_ABI, provider);
  const [token0, token1, reserves] = await Promise.all([
    pairContract.token0(),
    pairContract.token1(),
    pairContract.getReserves(),
  ]);
  return {
    label,
    pair,
    router,
    token0: ethers.getAddress(token0),
    token1: ethers.getAddress(token1),
    reserve0: reserves.reserve0,
    reserve1: reserves.reserve1,
  };
}

function reserveFor(state: PairState, tokenIn: string, tokenOut: string) {
  const inAddress = ethers.getAddress(tokenIn);
  const outAddress = ethers.getAddress(tokenOut);
  if (state.token0 === inAddress && state.token1 === outAddress) {
    return { reserveIn: state.reserve0, reserveOut: state.reserve1 };
  }
  if (state.token1 === inAddress && state.token0 === outAddress) {
    return { reserveIn: state.reserve1, reserveOut: state.reserve0 };
  }
  throw new Error(`${state.label}_TOKEN_MISMATCH`);
}

function quoteTwoLegUsdcRoute(first: PairState, second: PairState, amountUsdc: bigint): RouteQuote {
  const firstReserves = reserveFor(first, USDC, WETH);
  const wethOut = amountOutV2(amountUsdc, firstReserves.reserveIn, firstReserves.reserveOut);
  const secondReserves = reserveFor(second, WETH, USDC);
  const usdcOut = amountOutV2(wethOut, secondReserves.reserveIn, secondReserves.reserveOut);
  const grossProfitRaw = usdcOut - amountUsdc;
  return {
    route: `${first.label}->${second.label}`,
    amountInRaw: amountUsdc,
    wethOut,
    usdcOut,
    grossProfitRaw,
    profitableBeforeGas: grossProfitRaw > 0n,
    first,
    second,
  };
}

function stringifyCallError(error: any): string {
  const nested = error?.error || error?.info?.error || error?.data || error;
  const reason = error?.reason || nested?.reason || nested?.message || error?.shortMessage || error?.message || "CALL_REVERTED";
  return String(reason).replace(/\s+/g, " ").slice(0, 260);
}

function withSlippageFloor(amount: bigint, slippageBps: bigint): bigint {
  return amount * (10_000n - slippageBps) / 10_000n;
}

async function preflightCandidateC1(
  provider: ethers.JsonRpcProvider,
  signerAddress: string | undefined,
  c1TargetValue: unknown,
  quote: RouteQuote,
) {
  if (!signerAddress || typeof c1TargetValue !== "string") {
    console.log("C1_PAYLOAD_PREFLIGHT|skipped=true|reason=SIGNER_OR_C1_TARGET_MISSING|broadcasted=false|pnlUpdated=false");
    return;
  }

  const c1Target = normalizeAddressLoose(c1TargetValue);
  const targetCode = await provider.getCode(c1Target);
  if (targetCode === "0x") {
    console.log(`C1_PAYLOAD_PREFLIGHT|skipped=true|reason=C1_TARGET_HAS_NO_CODE|target=${c1Target}|broadcasted=false|pnlUpdated=false`);
    return;
  }

  const vm = new ethers.Contract(c1Target, VM_ABI, provider);
  const nonce = await vm.globalNonce().catch(() => 0n) as bigint;
  const routerIface = new ethers.Interface(ROUTER_ABI);
  const vmIface = new ethers.Interface(VM_ABI);
  const deadline = Math.floor(Date.now() / 1000) + 300;
  const slippageBps = 50n;
  const minWethOut = withSlippageFloor(quote.wethOut, slippageBps);
  const secondAmountIn = minWethOut;
  const secondReserves = reserveFor(quote.second, WETH, USDC);
  const conservativeUsdcOut = amountOutV2(secondAmountIn, secondReserves.reserveIn, secondReserves.reserveOut);
  const minUsdcOut = withSlippageFloor(conservativeUsdcOut, slippageBps);
  const routeSteps = [
    {
      venue: quote.first.router,
      tokenIn: USDC,
      tokenOut: WETH,
      amountIn: quote.amountInRaw,
      minAmountOut: minWethOut,
      callValue: 0n,
      payload: routerIface.encodeFunctionData("swapExactTokensForTokens", [
        quote.amountInRaw,
        minWethOut,
        [USDC, WETH],
        c1Target,
        deadline,
      ]),
    },
    {
      venue: quote.second.router,
      tokenIn: WETH,
      tokenOut: USDC,
      amountIn: secondAmountIn,
      minAmountOut: minUsdcOut,
      callValue: 0n,
      payload: routerIface.encodeFunctionData("swapExactTokensForTokens", [
        secondAmountIn,
        minUsdcOut,
        [WETH, USDC],
        c1Target,
        deadline,
      ]),
    },
  ];
  const minNetProfit = quote.grossProfitRaw > 0n ? quote.grossProfitRaw : 1n;
  const context = {
    profitAsset: USDC,
    minNetProfit,
    nonce,
    merkleRoot: ethers.ZeroHash,
    proof: [],
    steps: routeSteps,
  };
  const calldata = vmIface.encodeFunctionData("executeC1", [DEFAULT_FLASHLOAN_SOURCE_AAVE_V3, USDC, quote.amountInRaw, context]);
  const calldataHash = ethers.keccak256(calldata);
  try {
    await provider.call({ from: signerAddress, to: c1Target, data: calldata, value: 0 });
    console.log(`C1_PAYLOAD_PREFLIGHT|route=${quote.route}|ok=true|target=${c1Target}|amountIn=${formatUnits(quote.amountInRaw, 6)}|calldataHash=${calldataHash}|minNetProfitRaw=${minNetProfit}|broadcasted=false|pnlUpdated=false`);
  } catch (error) {
    console.log(`C1_PAYLOAD_PREFLIGHT|route=${quote.route}|ok=false|target=${c1Target}|amountIn=${formatUnits(quote.amountInRaw, 6)}|calldataHash=${calldataHash}|minNetProfitRaw=${minNetProfit}|reason=${stringifyCallError(error)}|broadcasted=false|pnlUpdated=false`);
  }
}

async function auditContract(provider: ethers.JsonRpcProvider, label: string, value: unknown, signerAddress?: string) {
  const address = typeof value === "string" ? normalizeAddressLoose(value) : undefined;
  if (!address) return;
  const code = await provider.getCode(address);
  const hasCode = code !== "0x";
  let owner: string | null = null;
  let globalNonce: string | null = null;
  let aaveV3Pool: string | null = null;
  if (hasCode) {
    const contract = new ethers.Contract(address, VM_ABI, provider);
    owner = await contract.owner().catch(() => null);
    globalNonce = await contract.globalNonce().then((value: bigint) => value.toString()).catch(() => null);
    aaveV3Pool = await contract.aaveV3Pool().catch(() => null);
  }
  console.log(`CONTRACT_AUDIT|${label}|address=${address}|hasCode=${hasCode}|owner=${owner ?? "UNREADABLE"}|signerIsOwner=${owner && signerAddress ? owner.toLowerCase() === signerAddress.toLowerCase() : "UNKNOWN"}|aaveV3Pool=${aaveV3Pool ?? "UNREADABLE"}|globalNonce=${globalNonce ?? "UNREADABLE"}`);
}

async function auditReceipt(provider: ethers.JsonRpcProvider, hash: string, profitAsset: string, profitReceiver: string) {
  const [tx, receipt] = await Promise.all([
    provider.getTransaction(hash),
    provider.getTransactionReceipt(hash),
  ]);
  if (!tx || !receipt) {
    console.log(`RECEIPT_AUDIT|hash=${hash}|found=false|provenSuccess=false|pnlUpdated=false`);
    return { statusOne: false, creditedRaw: 0n };
  }
  const receiverTopic = topicForAddress(profitReceiver);
  const creditedRaw = receipt.logs.reduce((sum, log) => {
    if (log.address.toLowerCase() !== profitAsset.toLowerCase()) return sum;
    if ((log.topics[0] || "").toLowerCase() !== TRANSFER_TOPIC) return sum;
    if ((log.topics[2] || "").toLowerCase() !== receiverTopic) return sum;
    return sum + BigInt(log.data);
  }, 0n);
  const statusOne = receipt.status === 1;
  console.log(`RECEIPT_AUDIT|hash=${hash}|status=${receipt.status}|block=${receipt.blockNumber}|to=${tx.to}|gasUsed=${receipt.gasUsed.toString()}|creditedRaw=${creditedRaw.toString()}|provenSuccess=${statusOne && creditedRaw > 0n}|pnlUpdated=false`);
  return { statusOne, creditedRaw };
}

async function main() {
  const cfg = readConfig();
  const rpcUrl = getRpcUrl(cfg);
  const provider = new ethers.JsonRpcProvider(rpcUrl, Number(POLYGON_CHAIN_ID), { staticNetwork: true });
  const network = await provider.getNetwork();
  if (network.chainId !== POLYGON_CHAIN_ID) throw new Error(`CHAIN_ID_MISMATCH:${network.chainId}`);

  const key = firstString(process.env.EXECUTOR_PRIVATE_KEY, process.env.BOT_PRIVATE_KEY, process.env.PRIVATE_KEY);
  const signerAddress = key ? new ethers.Wallet(key).address : undefined;
  const profitReceiver = normalizeAddressLoose(firstString(cfg.BOT_PROFIT_RECEIVER, cfg.PROFIT_RECIPIENT_ADDRESS, process.env.BOT_PROFIT_RECEIVER, process.env.PROFIT_RECIPIENT_ADDRESS, signerAddress) || "");
  const profitAsset = normalizeAddressLoose(firstString(cfg.PROFIT_ASSET, cfg.PROFIT_TOKEN, process.env.PROFIT_ASSET, process.env.PROFIT_TOKEN, USDC) || USDC);
  const profitToken = new ethers.Contract(profitAsset, ERC20_ABI, provider);
  const [profitDecimals, profitBalance] = await Promise.all([
    profitToken.decimals().then((value: bigint) => Number(value)),
    profitToken.balanceOf(profitReceiver) as Promise<bigint>,
  ]);

  console.log(`STRATEGY_PROOF_AUDIT|chainId=${network.chainId}|rpc=${rpcUrl}|signer=${signerAddress ?? "NO_KEY"}|profitReceiver=${profitReceiver}|profitAsset=${profitAsset}|profitBalanceRaw=${profitBalance.toString()}|profitBalance=${formatUnits(profitBalance, profitDecimals)}`);

  await auditContract(provider, "C1_TARGET", firstString(cfg.C1_ARB_EXECUTOR_ADDRESS, cfg.C1_TARGET, cfg.ARB_CONTRACT_ADDRESS), signerAddress);
  await auditContract(provider, "C2_TARGET", firstString(cfg.C2_ARB_EXECUTOR_ADDRESS, cfg.C2_TARGET, cfg.C1_ARB_EXECUTOR_ADDRESS, cfg.C1_TARGET, cfg.ARB_CONTRACT_ADDRESS), signerAddress);
  await auditContract(provider, "LIQUIDATION_TARGET", firstString(cfg.LIQUIDATION_EXECUTOR_ADDRESS, cfg.LIQUIDATION_EXECUTOR_CONTRACT), signerAddress);

  let provenReceiptCount = 0;
  for (const hash of parseHashes()) {
    const receipt = await auditReceipt(provider, hash, profitAsset, profitReceiver);
    if (receipt.statusOne && receipt.creditedRaw > 0n) provenReceiptCount += 1;
  }

  const quick = await getPairState(provider, "QUICKSWAP_V2_USDC_WETH", QUICKSWAP_FACTORY, QUICKSWAP_ROUTER);
  const sushi = await getPairState(provider, "SUSHISWAP_V2_USDC_WETH", SUSHISWAP_FACTORY, SUSHISWAP_ROUTER);
  console.log(`PAIR_AUDIT|${quick.label}|pair=${quick.pair}|router=${quick.router}|token0=${quick.token0}|token1=${quick.token1}|reserve0=${quick.reserve0}|reserve1=${quick.reserve1}`);
  console.log(`PAIR_AUDIT|${sushi.label}|pair=${sushi.pair}|router=${sushi.router}|token0=${sushi.token0}|token1=${sushi.token1}|reserve0=${sushi.reserve0}|reserve1=${sushi.reserve1}`);

  const amounts = [1n, 10n, 100n, 1000n, 5000n, 15000n].map((value) => value * 1_000_000n);
  let bestProfitRaw = -1n << 255n;
  let bestQuote: RouteQuote | null = null;
  for (const amount of amounts) {
    for (const quote of [quoteTwoLegUsdcRoute(quick, sushi, amount), quoteTwoLegUsdcRoute(sushi, quick, amount)]) {
      if (quote.grossProfitRaw > bestProfitRaw) {
        bestProfitRaw = quote.grossProfitRaw;
        bestQuote = quote;
      }
      console.log(`ROUTE_EDGE_AUDIT|route=${quote.route}|amountIn=${formatUnits(quote.amountInRaw, 6)}|amountOut=${formatUnits(quote.usdcOut, 6)}|grossProfit=${formatUnits(quote.grossProfitRaw, 6)}|profitableBeforeGas=${quote.profitableBeforeGas}|pnlUpdated=false`);
    }
  }

  if (bestQuote) {
    await preflightCandidateC1(provider, signerAddress, firstString(cfg.C1_ARB_EXECUTOR_ADDRESS, cfg.C1_TARGET, cfg.ARB_CONTRACT_ADDRESS), bestQuote);
  }

  const serverSource = fs.existsSync(path.join(process.cwd(), "server.ts")) ? fs.readFileSync(path.join(process.cwd(), "server.ts"), "utf-8") : "";
  const transactionDnaNull = serverSource.includes("transactionDna: null");
  const payloadFiles = ["payloads", "signals", path.join("signals", "outgoing")]
    .flatMap((dir) => fs.existsSync(dir) ? fs.readdirSync(dir, { recursive: true }).map((file) => path.join(dir, String(file))) : [])
    .filter((file) => file.endsWith(".json"));
  const executablePayloadReady = !transactionDnaNull || payloadFiles.length > 0;
  const finalStatus = provenReceiptCount > 0
    ? "PROVEN_SUCCESS"
    : bestProfitRaw <= 0n && !executablePayloadReady
      ? "BLOCKED_NO_PROFIT_EDGE_AND_NO_EXECUTABLE_PAYLOAD"
      : bestProfitRaw <= 0n
        ? "BLOCKED_NO_PROFIT_EDGE"
        : "BLOCKED_NO_EXECUTABLE_PAYLOAD";

  console.log(`PROOF_SUMMARY|status=${finalStatus}|provenReceiptCount=${provenReceiptCount}|bestGrossProfitRaw=${bestProfitRaw.toString()}|bestGrossProfitUsdc=${formatUnits(bestProfitRaw, 6)}|transactionDnaNull=${transactionDnaNull}|payloadJsonFiles=${payloadFiles.length}|pnlUpdated=false`);
}

main().catch((error) => {
  console.error(`STRATEGY_PROOF_AUDIT_FAILED|${error?.message || error}`);
  process.exit(1);
});
