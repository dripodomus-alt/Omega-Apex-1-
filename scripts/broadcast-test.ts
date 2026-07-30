import "dotenv/config";
import fs from "fs";
import path from "path";
import { ethers } from "ethers";

const ZERO_ADDRESS = ethers.ZeroAddress;
const ZERO_HASH = ethers.ZeroHash;
const DEFAULT_PROFIT_ASSET = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174";
const POLYGON_CHAIN_ID = 137n;
const GAS_RISK_ACK = "I_ACCEPT_GAS_RISK";
const DEFAULT_FLASHLOAN_SOURCE_AAVE_V3 = 1;

const APEX_VM_ABI = [
  "function executeC1(uint8 flashloanSource, address flashloanAsset, uint256 flashloanAmount, tuple(address profitAsset,uint256 minNetProfit,uint256 nonce,bytes32 merkleRoot,bytes32[] proof,tuple(address venue,address tokenIn,address tokenOut,uint256 amountIn,uint256 minAmountOut,uint256 callValue,bytes payload)[] steps) context) external",
  "function executeC2(bytes32 c1InternalId, uint8 flashloanSource, address flashloanAsset, uint256 flashloanAmount, tuple(address profitAsset,uint256 minNetProfit,uint256 nonce,bytes32 merkleRoot,bytes32[] proof,tuple(address venue,address tokenIn,address tokenOut,uint256 amountIn,uint256 minAmountOut,uint256 callValue,bytes payload)[] steps) context) external",
];

const LIQUIDATION_EXECUTOR_ABI = [
  "function executeLiquidation(tuple(address collateralAsset,address debtAsset,address user,uint256 debtToCover,uint256 minProfitBps,uint8 swapProtocol,uint24 swapFee,uint256 minDebtAmountOut,address curvePool,uint256 maxSlippageBps) params) external",
];

type Config = Record<string, unknown>;

type BroadcastCase = {
  key: "c1" | "c2" | "liquidation";
  payloadKind: string;
  canonicalName: string;
  target: string;
  calldata: string;
};

function readConfig(): Config {
  const configPath = path.join(process.cwd(), "config.json");
  if (!fs.existsSync(configPath)) return {};
  return JSON.parse(fs.readFileSync(configPath, "utf-8"));
}

function firstString(...values: unknown[]): string | undefined {
  return values.find((value): value is string => typeof value === "string" && value.trim().length > 0)?.trim();
}

function requireAddress(label: string, value: string | undefined): string {
  if (!value || !ethers.isAddress(value)) throw new Error(`${label}_MISSING_OR_INVALID`);
  return ethers.getAddress(value);
}

function optionalAddress(value: unknown): string | undefined {
  return typeof value === "string" && ethers.isAddress(value) ? ethers.getAddress(value) : undefined;
}

function getPrivateKey(): string {
  const key = firstString(process.env.EXECUTOR_PRIVATE_KEY, process.env.BOT_PRIVATE_KEY, process.env.PRIVATE_KEY);
  if (!key) throw new Error("PRIVATE_KEY_REQUIRED");
  return key;
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
    cfg.PUBLIC_POLYGON_RPC,
    "https://polygon-bor-rpc.publicnode.com",
  );
  if (!url) throw new Error("POLYGON_RPC_URL_REQUIRED");
  if (url.includes("YOUR_")) throw new Error("POLYGON_RPC_URL_PLACEHOLDER");
  return url;
}

function parseCaseSelection(): Set<string> {
  const arg = process.argv.find((value) => value.startsWith("--case="));
  const raw = firstString(arg?.slice("--case=".length), process.env.BROADCAST_TEST_CASE, "c1");
  const selected = raw.split(",").map((value) => value.trim().toLowerCase()).filter(Boolean);
  const allowed = new Set(["c1", "c2", "liquidation", "all"]);
  for (const value of selected) {
    if (!allowed.has(value)) throw new Error(`INVALID_BROADCAST_CASE:${value}`);
  }
  return selected.includes("all") ? new Set(["c1", "c2", "liquidation"]) : new Set(selected);
}

function parseGasLimit(): bigint {
  const raw = firstString(process.env.BROADCAST_TEST_GAS_LIMIT, "1000000");
  const parsed = BigInt(raw);
  if (parsed <= 21_000n) throw new Error("BROADCAST_TEST_GAS_LIMIT_TOO_LOW");
  return parsed;
}

function buildCases(cfg: Config): BroadcastCase[] {
  const profitAsset = requireAddress("PROFIT_ASSET", firstString(cfg.PROFIT_ASSET, cfg.PROFIT_TOKEN, DEFAULT_PROFIT_ASSET));
  const c1Target = requireAddress("C1_TARGET", firstString(cfg.C1_ARB_EXECUTOR_ADDRESS, cfg.C1_TARGET, cfg.ARB_CONTRACT_ADDRESS));
  const c2Target = requireAddress("C2_TARGET", firstString(cfg.C2_ARB_EXECUTOR_ADDRESS, cfg.C2_TARGET, cfg.C1_ARB_EXECUTOR_ADDRESS, cfg.C1_TARGET, cfg.ARB_CONTRACT_ADDRESS));
  const liquidationTarget = requireAddress("LIQUIDATION_EXECUTOR_ADDRESS", firstString(cfg.LIQUIDATION_EXECUTOR_ADDRESS, cfg.LIQUIDATION_EXECUTOR_CONTRACT));

  const vmIface = new ethers.Interface(APEX_VM_ABI);
  const liquidationIface = new ethers.Interface(LIQUIDATION_EXECUTOR_ABI);
  const blankContext = {
    profitAsset,
    minNetProfit: 0n,
    nonce: 0n,
    merkleRoot: ZERO_HASH,
    proof: [],
    steps: [],
  };
  const blankLiquidation = {
    collateralAsset: ZERO_ADDRESS,
    debtAsset: ZERO_ADDRESS,
    user: ZERO_ADDRESS,
    debtToCover: 0n,
    minProfitBps: 0n,
    swapProtocol: 0,
    swapFee: 0,
    minDebtAmountOut: 0n,
    curvePool: ZERO_ADDRESS,
    maxSlippageBps: 0n,
  };

  return [
    {
      key: "c1",
      payloadKind: "FLASHLOAN_INTEGRATED_C1_PAYLOADS",
      canonicalName: "FLASHLOAN INTEGRATED C1 PAYLOADS",
      target: c1Target,
      calldata: vmIface.encodeFunctionData("executeC1", [DEFAULT_FLASHLOAN_SOURCE_AAVE_V3, ZERO_ADDRESS, 0n, blankContext]),
    },
    {
      key: "c2",
      payloadKind: "FLASHLOAN_INTEGRATED_C2_PAYLOADS",
      canonicalName: "FLASHLOAN INTEGRATED C2 PAYLOADS",
      target: c2Target,
      calldata: vmIface.encodeFunctionData("executeC2", [ZERO_HASH, 0, ZERO_ADDRESS, 0n, blankContext]),
    },
    {
      key: "liquidation",
      payloadKind: "FLASHLOAN_INTEGRATED_LIQUIDATIONS",
      canonicalName: "FLASHLOAN INTEGRATED LIQUIDATIONS",
      target: liquidationTarget,
      calldata: liquidationIface.encodeFunctionData("executeLiquidation", [blankLiquidation]),
    },
  ];
}

async function preflightCall(provider: ethers.JsonRpcProvider, test: BroadcastCase, from: string) {
  try {
    await provider.call({ from, to: test.target, data: test.calldata, value: 0 });
    return { ok: true, message: "CALL_OK" };
  } catch (error) {
    const message = error instanceof Error ? error.message.replace(/\s+/g, " ").slice(0, 240) : String(error);
    return { ok: false, message };
  }
}

async function main() {
  if (process.env.BROADCAST_TEST_ACK !== GAS_RISK_ACK) {
    throw new Error("BROADCAST_TEST_ACK_REQUIRED");
  }

  const cfg = readConfig();
  const rpcUrl = getRpcUrl(cfg);
  const provider = new ethers.JsonRpcProvider(rpcUrl, Number(POLYGON_CHAIN_ID), { staticNetwork: true });
  const network = await provider.getNetwork();
  if (network.chainId !== POLYGON_CHAIN_ID) {
    throw new Error(`CHAIN_ID_MISMATCH:${network.chainId.toString()}`);
  }

  const wallet = new ethers.Wallet(getPrivateKey(), provider);
  const executorWallet = optionalAddress(cfg.EXECUTOR_WALLET);
  const profitReceiver = optionalAddress(cfg.BOT_PROFIT_RECEIVER);
  const signerMatchesExecutor = !executorWallet || executorWallet.toLowerCase() === wallet.address.toLowerCase();
  const selected = parseCaseSelection();
  const cases = buildCases(cfg).filter((test) => selected.has(test.key));
  if (cases.length === 0) throw new Error("NO_BROADCAST_CASES_SELECTED");

  const gasLimit = parseGasLimit();
  const feeData = await provider.getFeeData();
  const maxFeePerGas = feeData.maxFeePerGas ?? ethers.parseUnits("80", "gwei");
  const maxPriorityFeePerGas = feeData.maxPriorityFeePerGas ?? ethers.parseUnits("30", "gwei");
  let nonce = await provider.getTransactionCount(wallet.address, "pending");

  console.log(
    `BROADCAST_TEST|ethers=${ethers.version}|chainId=${network.chainId.toString()}|rpc=${rpcUrl}|signer=${wallet.address}|executorWallet=${executorWallet ?? "UNSET"}|signerMatchesExecutor=${signerMatchesExecutor}|profitReceiver=${profitReceiver ?? "UNSET"}|gasLimit=${gasLimit.toString()}|broadcasted=true`,
  );
  if (!signerMatchesExecutor) {
    console.log("BROADCAST_WARNING|SIGNER_DOES_NOT_MATCH_CONFIGURED_EXECUTOR_WALLET");
  }

  for (const test of cases) {
    const callResult = await preflightCall(provider, test, wallet.address);
    console.log(`PREFLIGHT_CALL|${test.payloadKind}|ok=${callResult.ok}|message=${callResult.message}`);

    const txRequest: ethers.TransactionRequest = {
      type: 2,
      chainId: Number(POLYGON_CHAIN_ID),
      to: test.target,
      nonce,
      value: 0,
      data: test.calldata,
      gasLimit,
      maxFeePerGas,
      maxPriorityFeePerGas,
    };
    const response = await wallet.sendTransaction(txRequest);
    const hashLink = `https://polygonscan.com/tx/${response.hash}`;
    const result = {
      payloadKind: test.payloadKind,
      canonicalName: test.canonicalName,
      chainId: network.chainId.toString(),
      target: test.target,
      signer: wallet.address,
      selector: test.calldata.slice(0, 10),
      calldataHash: ethers.keccak256(test.calldata),
      txHash: response.hash,
      hashLink,
      nonce,
      gasLimit: gasLimit.toString(),
      maxFeePerGas: maxFeePerGas.toString(),
      maxPriorityFeePerGas: maxPriorityFeePerGas.toString(),
      preflightCallOk: callResult.ok,
      broadcasted: true,
      pnlUpdated: false,
    };
    console.log(`HASH_PRINTED|${result.payloadKind}|txHash=${result.txHash}|hashLink=${result.hashLink}|calldataHash=${result.calldataHash}|broadcasted=true|pnlUpdated=false`);
    console.log(JSON.stringify(result));
    nonce += 1;
  }
}

main().catch((error) => {
  console.error(`BROADCAST_TEST_FAILED|${error?.message || error}`);
  process.exit(1);
});
