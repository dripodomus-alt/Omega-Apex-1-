import "dotenv/config";
import fs from "fs";
import path from "path";
import { ethers } from "ethers";

const CHAIN_ID = 137n;
const AAVE_V3_POOL = "0x794a61358D6845594F94dc1DB02A252b5b4814aD";
const ZERO = "0x0000000000000000000000000000000000000000";

const VM_ABI = [
  "function owner() view returns (address)",
  "function aaveV3Pool() view returns (address)",
  "function globalNonce() view returns (uint256)",
];

const OWNABLE_ABI = [
  "function owner() view returns (address)",
];

type Config = Record<string, unknown>;

function readConfig(): Config {
  const configPath = path.join(process.cwd(), "config.json");
  if (!fs.existsSync(configPath)) return {};
  return JSON.parse(fs.readFileSync(configPath, "utf-8"));
}

function firstString(...values: unknown[]): string | undefined {
  return values.find((value): value is string => typeof value === "string" && value.trim().length > 0)?.trim();
}

function normalizeAddress(value: string, label: string): string {
  if (!ethers.isAddress(value)) throw new Error(`INVALID_${label}:${value}`);
  return ethers.getAddress(value);
}

function getRpcUrl(config: Config): string {
  const rpc = firstString(
    process.env.POLYGON_RPC_URL,
    process.env.RPC_URL,
    config.POLYGON_RPC_URL,
    config.POLYGON_RPC,
    "https://polygon-rpc.com",
  );
  if (!rpc) throw new Error("POLYGON_RPC_URL_MISSING");
  return rpc;
}

function getForkRpcUrl(): string {
  const rpc = firstString(process.env.FORK_SIM_RPC_URL);
  if (!rpc) throw new Error("FORK_SIM_RPC_URL_MISSING");
  return rpc;
}

function getSignerAddress(): string {
  const key = firstString(process.env.EXECUTOR_PRIVATE_KEY, process.env.BOT_PRIVATE_KEY, process.env.PRIVATE_KEY);
  if (!key) throw new Error("EXECUTOR_PRIVATE_KEY_MISSING");
  return new ethers.Wallet(key).address;
}

async function requireCode(provider: ethers.Provider, label: string, address: string) {
  const code = await provider.getCode(address);
  if (code === "0x") throw new Error(`${label}_NO_CODE:${address}`);
  console.log(`TARGET_AUDIT|${label}|address=${address}|hasCode=true`);
}

async function requireOwner(provider: ethers.Provider, label: string, address: string, signer: string) {
  const contract = new ethers.Contract(address, OWNABLE_ABI, provider);
  const owner = normalizeAddress(await contract.owner(), `${label}_OWNER`);
  const signerMatches = owner.toLowerCase() === signer.toLowerCase();
  console.log(`OWNER_AUDIT|${label}|owner=${owner}|signer=${signer}|signerMatches=${signerMatches}`);
  if (!signerMatches) throw new Error(`${label}_OWNER_SIGNER_MISMATCH`);
}

async function main() {
  const config = readConfig();
  const provider = new ethers.JsonRpcProvider(getRpcUrl(config), Number(CHAIN_ID), { staticNetwork: true });
  const forkProvider = new ethers.JsonRpcProvider(getForkRpcUrl(), Number(CHAIN_ID), { staticNetwork: true });
  const signer = normalizeAddress(getSignerAddress(), "SIGNER");

  const [network, forkNetwork] = await Promise.all([
    provider.getNetwork(),
    forkProvider.getNetwork(),
  ]);
  if (network.chainId !== CHAIN_ID) throw new Error(`CHAIN_ID_MISMATCH:${network.chainId}`);
  if (forkNetwork.chainId !== CHAIN_ID) throw new Error(`FORK_CHAIN_ID_MISMATCH:${forkNetwork.chainId}`);
  console.log(`CHAIN_AUDIT|main=${network.chainId}|fork=${forkNetwork.chainId}|status=PASS`);

  const c1Target = normalizeAddress(firstString(config.C1_ARB_EXECUTOR_ADDRESS, config.C1_TARGET, process.env.C1_ARB_EXECUTOR_ADDRESS, process.env.C1_TARGET) || "", "C1_TARGET");
  const c2Target = normalizeAddress(firstString(config.C2_ARB_EXECUTOR_ADDRESS, config.C2_TARGET, config.C1_ARB_EXECUTOR_ADDRESS, config.C1_TARGET, process.env.C2_ARB_EXECUTOR_ADDRESS, process.env.C2_TARGET, process.env.C1_ARB_EXECUTOR_ADDRESS, process.env.C1_TARGET) || "", "C2_TARGET");
  const liquidationTarget = normalizeAddress(firstString(config.LIQUIDATION_EXECUTOR_ADDRESS, config.LIQUIDATION_EXECUTOR_CONTRACT, process.env.LIQUIDATION_EXECUTOR_ADDRESS, process.env.LIQUIDATION_EXECUTOR_CONTRACT) || ZERO, "LIQUIDATION_TARGET");

  await requireCode(provider, "C1_TARGET", c1Target);
  await requireCode(provider, "C2_TARGET", c2Target);
  await requireOwner(provider, "C1_TARGET", c1Target, signer);
  await requireOwner(provider, "C2_TARGET", c2Target, signer);

  const vm = new ethers.Contract(c1Target, VM_ABI, provider);
  const [aavePool, globalNonce] = await Promise.all([
    vm.aaveV3Pool(),
    vm.globalNonce(),
  ]);
  const aaveMatches = normalizeAddress(aavePool, "AAVE_POOL").toLowerCase() === AAVE_V3_POOL.toLowerCase();
  console.log(`VM_AUDIT|target=${c1Target}|aaveV3Pool=${aavePool}|aaveMatches=${aaveMatches}|globalNonce=${globalNonce}`);
  if (!aaveMatches) throw new Error("AAVE_POOL_MISMATCH");

  if (liquidationTarget !== ZERO) {
    await requireCode(provider, "LIQUIDATION_TARGET", liquidationTarget);
    await requireOwner(provider, "LIQUIDATION_TARGET", liquidationTarget, signer);
  }

  console.log("CLOUD_READINESS|status=PASS|broadcasted=false|pnlUpdated=false");
}

main().catch((error) => {
  console.error(`CLOUD_READINESS|status=FAIL|error=${error?.message || error}|broadcasted=false|pnlUpdated=false`);
  process.exit(1);
});
