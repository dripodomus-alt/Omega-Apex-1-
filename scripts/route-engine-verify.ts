import "dotenv/config";
import { ethers } from "ethers";
import {
  ALGEBRA_FACTORY_ABI,
  BALANCER_VAULT_ABI,
  CURVE_ADDRESS_PROVIDER_ABI,
  routeAdapterCapabilities,
  ROUTE_ADAPTER_TARGETS,
  UNISWAP_V2_FACTORY_ABI,
  UNISWAP_V3_FACTORY_ABI,
} from "../server/engine/routeAdapters.js";

const FACTORY_ADDRESSES = {
  quickswapV2: "0x5757371414417b8c6caad45baef941abc7d3ab32",
  sushiswapV2: "0xc35DADB65012eC5796536bD9864eD8773aBc74C4",
  uniswapV3: "0x1F98431c8aD98523631AE4a59f267346ea31F984",
  algebraFactory: ROUTE_ADAPTER_TARGETS.algebraFactory,
  balancerVault: "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
  curveAddressProvider: process.env.CURVE_ADDRESS_PROVIDER || "0x0000000022D53366457F9d5E68Ec105046FC4383",
};

function getRpcUrl() {
  return process.env.POLYGON_RPC_URL || process.env.POLYGON_RPC || process.env.RPC_URL || "https://polygon-bor-rpc.publicnode.com";
}

async function codeStatus(provider: ethers.JsonRpcProvider, label: string, address: string, abi: string[]) {
  const code = await provider.getCode(address).catch(() => "0x");
  const hasCode = code !== "0x";
  let eventAbiPresent = false;
  let recentLogQueryOk = false;
  if (hasCode) {
    try {
      const iface = new ethers.Interface(abi);
      const event = iface.fragments.find((fragment): fragment is ethers.EventFragment => fragment.type === "event");
      if (event) {
        eventAbiPresent = true;
        const topic = event.topicHash;
        const latest = await provider.getBlockNumber();
        await provider.getLogs({ address, topics: topic ? [topic] : [], fromBlock: Math.max(0, latest - 20), toBlock: latest });
        recentLogQueryOk = true;
      }
    } catch {
      recentLogQueryOk = false;
    }
  }
  console.log(`DISCOVERY_SOURCE_AUDIT|${label}|address=${address}|hasCode=${hasCode}|eventAbiPresent=${eventAbiPresent}|recentLogQueryOk=${recentLogQueryOk}`);
  return hasCode;
}

async function curveProviderStatus(provider: ethers.JsonRpcProvider, address: string) {
  const code = await provider.getCode(address).catch(() => "0x");
  const hasCode = code !== "0x";
  let registry = "UNREADABLE";
  let registryHasCode = false;
  if (hasCode) {
    try {
      const contract = new ethers.Contract(address, CURVE_ADDRESS_PROVIDER_ABI, provider);
      registry = await contract.get_registry();
      registryHasCode = await provider.getCode(registry).then((code) => code !== "0x").catch(() => false);
    } catch {
      registry = "UNREADABLE";
    }
  }
  console.log(`DISCOVERY_SOURCE_AUDIT|CURVE_ADDRESS_PROVIDER|address=${address}|hasCode=${hasCode}|registry=${registry}|registryHasCode=${registryHasCode}`);
}

async function main() {
  const provider = new ethers.JsonRpcProvider(getRpcUrl(), 137, { staticNetwork: true });
  const network = await provider.getNetwork();
  if (network.chainId !== 137n) throw new Error(`CHAIN_ID_MISMATCH:${network.chainId}`);

  console.log(`ROUTE_ENGINE_VERIFY|chainId=${network.chainId}|rpc=${getRpcUrl()}|forkSimConfigured=${Boolean(process.env.FORK_SIM_RPC_URL)}|mockDataAllowed=false`);
  await codeStatus(provider, "QUICKSWAP_V2_PAIR_CREATED", FACTORY_ADDRESSES.quickswapV2, UNISWAP_V2_FACTORY_ABI);
  await codeStatus(provider, "SUSHISWAP_V2_PAIR_CREATED", FACTORY_ADDRESSES.sushiswapV2, UNISWAP_V2_FACTORY_ABI);
  await codeStatus(provider, "UNISWAP_V3_POOL_CREATED", FACTORY_ADDRESSES.uniswapV3, UNISWAP_V3_FACTORY_ABI);
  await codeStatus(provider, "QUICKSWAP_ALGEBRA_POOL", FACTORY_ADDRESSES.algebraFactory, ALGEBRA_FACTORY_ABI);
  await codeStatus(provider, "BALANCER_POOL_REGISTERED", FACTORY_ADDRESSES.balancerVault, BALANCER_VAULT_ABI);
  await curveProviderStatus(provider, FACTORY_ADDRESSES.curveAddressProvider);

  for (const adapter of routeAdapterCapabilities) {
    const allRequiredAdaptersPresent = adapter.adapterPresent
      && !adapter.quoteAdapter.startsWith("REQUIRES_")
      && !adapter.calldataAdapter.startsWith("REQUIRES_");
    console.log(
      `ADAPTER_COVERAGE|poolType=${adapter.poolType}|adapterPresent=${adapter.adapterPresent}|discovery=${adapter.discoverySource}|stateReader=${adapter.stateReader}|quote=${adapter.quoteAdapter}|calldata=${adapter.calldataAdapter}|forkSimulation=${adapter.forkSimulation}|preSend=${adapter.preSendRevalidation}|routeEligible=${adapter.executable && allRequiredAdaptersPresent}|rejection=${adapter.executable && allRequiredAdaptersPresent ? "NONE" : adapter.rejectionReason || "FORK_SIM_OR_ADAPTER_MISSING"}`,
    );
  }
}

main().catch((error) => {
  console.error(`ROUTE_ENGINE_VERIFY_FAILED|${error?.message || error}`);
  process.exit(1);
});
