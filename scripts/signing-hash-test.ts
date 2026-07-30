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

type Config = Record<string, unknown>;

type SigningCase = {
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

function getSigningWallet() {
  const key = firstString(process.env.EXECUTOR_PRIVATE_KEY, process.env.BOT_PRIVATE_KEY, process.env.PRIVATE_KEY);
  if (key) {
    return { wallet: new ethers.Wallet(key), source: "ENV_PRIVATE_KEY" };
  }
  return { wallet: ethers.Wallet.createRandom(), source: "EPHEMERAL_TEST_WALLET_NO_ENV_KEY" };
}

function buildCases(cfg: Config): SigningCase[] {
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
}

async function signCase(wallet: ethers.Wallet | ethers.HDNodeWallet, test: SigningCase, nonce: number) {
  const unsignedTx: ethers.TransactionRequest = {
    type: 2,
    chainId: 137,
    to: test.target,
    nonce,
    value: 0,
    data: test.calldata,
    gasLimit: 1_000_000n,
    maxPriorityFeePerGas: 30_000_000_000n,
    maxFeePerGas: 80_000_000_000n,
  };
  const signedRawTx = await wallet.signTransaction(unsignedTx);
  const parsed = ethers.Transaction.from(signedRawTx);
  const rawHash = ethers.keccak256(signedRawTx);
  const parsedHash = parsed.hash;
  const fromMatches = parsed.from?.toLowerCase() === wallet.address.toLowerCase();
  const hashMatches = rawHash === parsedHash;

  return {
    payloadKind: test.payloadKind,
    canonicalName: test.canonicalName,
    chainId: parsed.chainId.toString(),
    target: test.target,
    signer: wallet.address,
    selector: test.calldata.slice(0, 10),
    calldataHash: ethers.keccak256(test.calldata),
    signedRawTxHash: rawHash,
    parsedTxHash: parsedHash,
    hashMatches,
    fromMatches,
    signedRawTxBytes: (signedRawTx.length - 2) / 2,
    broadcasted: false,
    pnlUpdated: false,
  };
}

async function main() {
  const cfg = readConfig();
  const { wallet, source } = getSigningWallet();
  const cases = buildCases(cfg);
  console.log(`SIGNING_TEST|ethers=${ethers.version}|chainId=137|signer=${wallet.address}|source=${source}|broadcasted=false`);

  for (let i = 0; i < cases.length; i += 1) {
    const result = await signCase(wallet, cases[i], i);
    console.log(`HASH_PRINTED|${result.payloadKind}|calldataHash=${result.calldataHash}|signedTxHash=${result.signedRawTxHash}|parsedTxHash=${result.parsedTxHash}|match=${result.hashMatches}|fromMatch=${result.fromMatches}`);
    console.log(JSON.stringify(result));
    if (!result.hashMatches || !result.fromMatches || result.chainId !== "137") {
      throw new Error(`SIGNING_HASH_VALIDATION_FAILED:${result.payloadKind}`);
    }
  }
}

main().catch((error) => {
  console.error(`SIGNING_TEST_FAILED|${error?.message || error}`);
  process.exit(1);
});
