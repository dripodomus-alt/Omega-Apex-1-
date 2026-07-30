import "dotenv/config";
import fs from "fs";
import path from "path";
import { ethers } from "ethers";

const ZERO_ADDRESS = ethers.ZeroAddress;
const ZERO_HASH = ethers.ZeroHash;
const DEFAULT_PROFIT_ASSET = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174";
const DEFAULT_FLASHLOAN_SOURCE_AAVE_V3 = 1;

const APEX_VM_ABI = [
  "function executeC1(uint8 flashloanSource, address flashloanAsset, uint256 flashloanAmount, tuple(address profitAsset,uint256 minNetProfit,uint256 nonce,bytes32 merkleRoot,bytes32[] proof,tuple(address venue,address tokenIn,address tokenOut,uint256 amountIn,uint256 minAmountOut,uint256 callValue,bytes payload)[] steps) context) external",
  "function executeC2(bytes32 c1InternalId, uint8 flashloanSource, address flashloanAsset, uint256 flashloanAmount, tuple(address profitAsset,uint256 minNetProfit,uint256 nonce,bytes32 merkleRoot,bytes32[] proof,tuple(address venue,address tokenIn,address tokenOut,uint256 amountIn,uint256 minAmountOut,uint256 callValue,bytes payload)[] steps) context) external",
];

const LIQUIDATION_EXECUTOR_ABI = [
  "function executeLiquidation(tuple(address collateralAsset,address debtAsset,address user,uint256 debtToCover,uint256 minProfitBps,uint8 swapProtocol,uint24 swapFee,uint256 minDebtAmountOut,address curvePool,uint256 maxSlippageBps) params) external",
];

type Config = Record<string, string | boolean | number | undefined>;

type TestCase = {
  canonicalName: string;
  payloadKind: string;
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
  if (!value || !ethers.isAddress(value)) {
    throw new Error(`${label}_MISSING_OR_INVALID`);
  }
  return ethers.getAddress(value);
}

function getRpcUrl(cfg: Config): string {
  const rpcUrl = firstString(
    process.env.CONTRACT_SYNC_RPC_URL,
    process.env.POLYGON_RPC_URL,
    process.env.POLYGON_RPC,
    process.env.PUBLIC_POLYGON_RPC,
    cfg.POLYGON_RPC_URL,
    cfg.POLYGON_RPC,
    cfg.PUBLIC_POLYGON_RPC,
  );
  if (!rpcUrl) throw new Error("CONTRACT_SYNC_RPC_URL_MISSING");
  return rpcUrl;
}

function stringifyRpcError(error: any): string {
  const nested = error?.error || error?.info?.error || error?.data || error;
  const reason = error?.reason || nested?.reason || nested?.message || error?.shortMessage || error?.message;
  const data = nested?.data || error?.data || error?.info?.error?.data;
  return JSON.stringify({ reason: reason || "RPC_CALL_REVERTED_OR_FAILED", data: data || null });
}

async function runEthCall(provider: ethers.JsonRpcProvider, from: string | undefined, test: TestCase) {
  const payloadHash = ethers.keccak256(test.calldata);
  const request: ethers.TransactionRequest = {
    to: test.target,
    data: test.calldata,
    value: 0,
  };
  if (from && ethers.isAddress(from)) request.from = ethers.getAddress(from);

  const code = await provider.getCode(test.target);
  const hasCode = code !== "0x";
  let response = "";
  let responseHash = "";
  let rpcStatus: "RESPONSE" | "REVERT_OR_REJECT" = "RESPONSE";

  try {
    response = await provider.call(request);
    responseHash = ethers.keccak256(response === "0x" ? "0x" : response);
  } catch (error: any) {
    response = stringifyRpcError(error);
    responseHash = ethers.id(response);
    rpcStatus = "REVERT_OR_REJECT";
  }

  return {
    payloadKind: test.payloadKind,
    canonicalName: test.canonicalName,
    target: test.target,
    targetHasCode: hasCode,
    selector: test.calldata.slice(0, 10),
    calldataBytes: (test.calldata.length - 2) / 2,
    payloadHash,
    hashType: "CALLDATA_KECCAK256_NOT_TX_HASH",
    rpcStatus,
    response,
    responseHash,
    broadcasted: false,
    signed: false,
    pnlUpdated: false,
  };
}

async function main() {
  const cfg = readConfig();
  const rpcUrl = getRpcUrl(cfg);
  const provider = new ethers.JsonRpcProvider(rpcUrl, 137);
  const from = firstString(cfg.EXECUTOR_WALLET, cfg.BOT_WALLET_ADDRESS, cfg.BOT_ADDRESS, cfg.BOT_PROFIT_RECEIVER, process.env.EXECUTOR_WALLET, process.env.BOT_WALLET_ADDRESS, process.env.BOT_ADDRESS, process.env.BOT_PROFIT_RECEIVER);
  const profitAsset = requireAddress("PROFIT_ASSET", firstString(cfg.PROFIT_ASSET, cfg.PROFIT_TOKEN, process.env.PROFIT_ASSET, process.env.PROFIT_TOKEN, DEFAULT_PROFIT_ASSET));

  const c1Target = requireAddress("C1_ARB_EXECUTOR_ADDRESS", firstString(cfg.C1_ARB_EXECUTOR_ADDRESS, cfg.C1_TARGET, cfg.ARB_CONTRACT_ADDRESS, process.env.C1_ARB_EXECUTOR_ADDRESS, process.env.C1_TARGET, process.env.ARB_CONTRACT_ADDRESS));
  const c2Target = requireAddress("C2_ARB_EXECUTOR_ADDRESS", firstString(cfg.C2_ARB_EXECUTOR_ADDRESS, cfg.C2_TARGET, cfg.C1_ARB_EXECUTOR_ADDRESS, cfg.C1_TARGET, cfg.ARB_CONTRACT_ADDRESS, process.env.C2_ARB_EXECUTOR_ADDRESS, process.env.C2_TARGET, process.env.C1_ARB_EXECUTOR_ADDRESS, process.env.C1_TARGET, process.env.ARB_CONTRACT_ADDRESS));
  const liquidationTarget = requireAddress("LIQUIDATION_EXECUTOR_ADDRESS", firstString(cfg.LIQUIDATION_EXECUTOR_ADDRESS, cfg.LIQUIDATION_EXECUTOR_CONTRACT, process.env.LIQUIDATION_EXECUTOR_ADDRESS, process.env.LIQUIDATION_EXECUTOR_CONTRACT));

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

  const tests: TestCase[] = [
    {
      payloadKind: "FLASHLOAN_INTEGRATED_C1_PAYLOADS",
      canonicalName: "FLASHLOAN INTEGRATED C1 PAYLOADS",
      target: c1Target,
      calldata: vmIface.encodeFunctionData("executeC1", [DEFAULT_FLASHLOAN_SOURCE_AAVE_V3, ZERO_ADDRESS, 0n, blankContext]),
    },
    {
      payloadKind: "FLASHLOAN_INTEGRATED_C2_PAYLOADS",
      canonicalName: "FLASHLOAN INTEGRATED C2 PAYLOADS",
      target: c2Target,
      calldata: vmIface.encodeFunctionData("executeC2", [ZERO_HASH, 0, ZERO_ADDRESS, 0n, blankContext]),
    },
    {
      payloadKind: "FLASHLOAN_INTEGRATED_LIQUIDATIONS",
      canonicalName: "FLASHLOAN INTEGRATED LIQUIDATIONS",
      target: liquidationTarget,
      calldata: liquidationIface.encodeFunctionData("executeLiquidation", [blankLiquidation]),
    },
  ];

  console.log(`CONTRACT_SYNC_TEST|rpc=${rpcUrl}|from=${from || "RPC_DEFAULT"}`);
  for (const test of tests) {
    const result = await runEthCall(provider, from, test);
    console.log(`HASH_PRINTED|${result.payloadKind}|${result.payloadHash}|selector=${result.selector}|target=${result.target}|status=${result.rpcStatus}|responseHash=${result.responseHash}`);
    console.log(JSON.stringify(result));
  }
}

main().catch((error) => {
  console.error(`CONTRACT_SYNC_TEST_FAILED|${error?.message || error}`);
  process.exit(1);
});

