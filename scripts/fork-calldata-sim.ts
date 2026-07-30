import "dotenv/config";
import { ethers } from "ethers";
import {
  buildV2SwapCalldata,
  quoteV2Cpmm,
  simulateExactCalldataOnFork,
} from "../server/engine/routeAdapters.js";

const CHAIN_ID = 137n;
const USDC = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174";
const WETH = "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619";
const QUICKSWAP_FACTORY = "0x5757371414417b8c6caad45baef941abc7d3ab32";
const QUICKSWAP_ROUTER = "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff";
const AAVE_V3_POOL = "0x794a61358D6845594F94dc1DB02A252b5b4814aD";

const FACTORY_ABI = ["function getPair(address,address) view returns (address)"];
const PAIR_ABI = [
  "function token0() view returns (address)",
  "function token1() view returns (address)",
  "function getReserves() view returns (uint112 reserve0,uint112 reserve1,uint32 blockTimestampLast)",
];
const ERC20_ABI = [
  "function balanceOf(address account) view returns (uint256)",
  "function approve(address spender,uint256 amount) returns (bool)",
  "function allowance(address owner,address spender) view returns (uint256)",
];

function requireUrl(value: string | undefined, key: string): string {
  if (!value || value.includes("YOUR_")) throw new Error(`${key}_MISSING`);
  return value;
}

function same(left: string, right: string): boolean {
  return ethers.getAddress(left) === ethers.getAddress(right);
}

function maskUrl(url: string): string {
  return url.replace(/(https?:\/\/[^/]+\/).+/, "$1***MASKED***");
}

async function rpc(provider: ethers.JsonRpcProvider, method: string, params: unknown[]) {
  return await provider.send(method, params);
}

async function main() {
  const forkRpcUrl = requireUrl(process.env.FORK_SIM_RPC_URL, "FORK_SIM_RPC_URL");
  const provider = new ethers.JsonRpcProvider(forkRpcUrl, Number(CHAIN_ID), { staticNetwork: true });
  const network = await provider.getNetwork();
  if (network.chainId !== CHAIN_ID) throw new Error(`FORK_CHAIN_ID_MISMATCH:${network.chainId}`);

  const factory = new ethers.Contract(QUICKSWAP_FACTORY, FACTORY_ABI, provider);
  const pairAddress = await factory.getPair(USDC, WETH);
  if (await provider.getCode(pairAddress) === "0x") throw new Error(`PAIR_HAS_NO_CODE:${pairAddress}`);

  const pair = new ethers.Contract(pairAddress, PAIR_ABI, provider);
  const [token0, token1, reserves] = await Promise.all([
    pair.token0(),
    pair.token1(),
    pair.getReserves(),
  ]);
  const reserveIn = same(token0, USDC) ? BigInt(reserves.reserve0) : BigInt(reserves.reserve1);
  const reserveOut = same(token0, WETH) ? BigInt(reserves.reserve0) : BigInt(reserves.reserve1);
  if (reserveIn <= 0n || reserveOut <= 0n) throw new Error("PAIR_ZERO_RESERVES");

  const amountIn = 1_000_000n;
  const quotedOut = quoteV2Cpmm(amountIn, reserveIn, reserveOut, 30);
  const minOut = quotedOut * 9_900n / 10_000n;
  const deadline = Math.floor(Date.now() / 1000) + 600;
  const calldata = buildV2SwapCalldata(amountIn, minOut, [USDC, WETH], AAVE_V3_POOL, deadline);
  const calldataHash = ethers.keccak256(calldata);

  const usdc = new ethers.Contract(USDC, ERC20_ABI, provider);
  const holderBalance = await usdc.balanceOf(AAVE_V3_POOL) as bigint;
  if (holderBalance < amountIn) throw new Error(`USDC_HOLDER_BALANCE_TOO_LOW:${holderBalance}`);

  await rpc(provider, "anvil_impersonateAccount", [AAVE_V3_POOL]);
  await rpc(provider, "anvil_setBalance", [AAVE_V3_POOL, "0x3635C9ADC5DEA00000"]);
  const holderSigner = await provider.getSigner(AAVE_V3_POOL);
  const usdcWithHolder = usdc.connect(holderSigner) as ethers.Contract;
  const approveTx = await usdcWithHolder.approve(QUICKSWAP_ROUTER, amountIn);
  await approveTx.wait();
  const allowance = await usdc.allowance(AAVE_V3_POOL, QUICKSWAP_ROUTER) as bigint;
  if (allowance < amountIn) throw new Error(`FORK_APPROVAL_FAILED:${allowance}`);

  const sim = await simulateExactCalldataOnFork({
    to: QUICKSWAP_ROUTER,
    from: AAVE_V3_POOL,
    data: calldata,
    value: 0n,
    forkRpcUrl,
  });

  console.log(`FORK_SIM_CONFIG|configured=${Boolean(process.env.FORK_SIM_RPC_URL)}|url=${maskUrl(forkRpcUrl)}|chainId=${network.chainId}`);
  console.log(`FORK_CALLDATA_DNA|adapter=V2_CPMM|target=${QUICKSWAP_ROUTER}|from=${AAVE_V3_POOL}|pair=${pairAddress}|amountIn=${amountIn}|quotedOut=${quotedOut}|minOut=${minOut}|calldataHash=${calldataHash}`);
  console.log(`FORK_CALLDATA_SIM|ok=${sim.ok}|returnData=${sim.returnData ?? "0x"}|error=${sim.error ?? "NONE"}|broadcasted=false|pnlUpdated=false`);
  if (!sim.ok) throw new Error(`FORK_CALLDATA_SIM_FAILED:${sim.error}`);
}

main().catch((error) => {
  console.error(`FORK_CALLDATA_PROOF_FAILED|${error?.message || error}`);
  process.exit(1);
});
