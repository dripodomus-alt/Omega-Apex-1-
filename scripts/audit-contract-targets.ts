import { ethers } from 'ethers';
import { POLYGON_CHAIN_CONFIG } from '../src/config/chainConfig';
import { DODO_POLYGON_ADDRESSES } from '../src/utils/dodoCalldata';

type TargetKind = 'CONTRACT' | 'TOKEN' | 'EOA';

interface Target {
  name: string;
  address: string;
  kind: TargetKind;
  required: boolean;
}

const TARGETS: Target[] = [
  { name: 'c1ArbExecutorAddress', address: POLYGON_CHAIN_CONFIG.c1ArbExecutorAddress, kind: 'CONTRACT', required: true },
  { name: 'c2ArbExecutorAddress', address: POLYGON_CHAIN_CONFIG.c2ArbExecutorAddress, kind: 'CONTRACT', required: true },
  { name: 'hftDefaultTarget', address: POLYGON_CHAIN_CONFIG.hftDefaultTarget, kind: 'CONTRACT', required: true },
  { name: 'merkleDefaultTarget', address: POLYGON_CHAIN_CONFIG.merkleDefaultTarget, kind: 'CONTRACT', required: true },
  { name: 'liquidationExecutorAddress', address: POLYGON_CHAIN_CONFIG.liquidationExecutorAddress, kind: 'CONTRACT', required: true },
  { name: 'aaveV3Pool', address: '0x794a61358D6845594F94dc1DB02A252b5b4814aD', kind: 'CONTRACT', required: true },
  { name: 'aaveV3CapitalAdapter', address: POLYGON_CHAIN_CONFIG.aaveV3CapitalAdapter, kind: 'CONTRACT', required: true },
  { name: 'aaveV3LiquidationAdapter', address: POLYGON_CHAIN_CONFIG.aaveV3LiquidationAdapter, kind: 'CONTRACT', required: true },
  { name: 'balancerVaultAddress', address: POLYGON_CHAIN_CONFIG.balancerVaultAddress, kind: 'CONTRACT', required: true },
  { name: 'balancerVaultCapitalAdapter', address: POLYGON_CHAIN_CONFIG.balancerVaultCapitalAdapter, kind: 'CONTRACT', required: true },
  { name: 'quickSwapV2Router', address: '0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff', kind: 'CONTRACT', required: true },
  { name: 'sushiSwapV2Router', address: '0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506', kind: 'CONTRACT', required: true },
  { name: 'quickSwapV2Factory', address: '0x5757371414417b8c6caad45baef941abc7d3ab32', kind: 'CONTRACT', required: true },
  { name: 'sushiSwapV2Factory', address: '0xc35dadb65012ec5796536bd9864ed8773abc74c4', kind: 'CONTRACT', required: true },
  { name: 'uniswapV3Quoter', address: POLYGON_CHAIN_CONFIG.uniswapV3Quoter, kind: 'CONTRACT', required: true },
  { name: 'uniswapV3Router', address: POLYGON_CHAIN_CONFIG.uniswapV3Router, kind: 'CONTRACT', required: true },
  { name: 'algebraFactory', address: POLYGON_CHAIN_CONFIG.algebraFactory, kind: 'CONTRACT', required: true },
  { name: 'algebraQuoter', address: POLYGON_CHAIN_CONFIG.algebraQuoter, kind: 'CONTRACT', required: true },
  { name: 'algebraRouter', address: POLYGON_CHAIN_CONFIG.algebraRouter, kind: 'CONTRACT', required: true },
  { name: 'curveAddressProvider', address: POLYGON_CHAIN_CONFIG.curveAddressProvider, kind: 'CONTRACT', required: true },
  { name: 'dodoV2Router', address: POLYGON_CHAIN_CONFIG.dodoV2Router, kind: 'CONTRACT', required: true },
  { name: 'dodoDvmFactory', address: POLYGON_CHAIN_CONFIG.dodoDvmFactory, kind: 'CONTRACT', required: true },
  { name: 'dodoDppFactory', address: POLYGON_CHAIN_CONFIG.dodoDppFactory, kind: 'CONTRACT', required: true },
  { name: 'dodoMixSwapProxy', address: POLYGON_CHAIN_CONFIG.dodoMixSwapProxy, kind: 'CONTRACT', required: true },
  { name: 'dodoEncoderRouter', address: DODO_POLYGON_ADDRESSES.router, kind: 'CONTRACT', required: true },
  { name: 'dodoEncoderDvmFactory', address: DODO_POLYGON_ADDRESSES.dvmFactory, kind: 'CONTRACT', required: true },
  { name: 'dodoEncoderDppFactory', address: DODO_POLYGON_ADDRESSES.dppFactory, kind: 'CONTRACT', required: true },
  { name: 'dodoEncoderMixSwapProxy', address: DODO_POLYGON_ADDRESSES.mixSwapProxy, kind: 'CONTRACT', required: true },
  { name: 'USDC.e', address: '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174', kind: 'TOKEN', required: true },
  { name: 'WPOL/WMATIC', address: '0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270', kind: 'TOKEN', required: true },
  { name: 'WETH', address: '0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619', kind: 'TOKEN', required: true },
  { name: 'USDT', address: '0xc2132D05D31c914a87C6611C10748AEb04B58e8F', kind: 'TOKEN', required: true },
  { name: 'DAI', address: '0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063', kind: 'TOKEN', required: true },
  { name: 'botAddress', address: POLYGON_CHAIN_CONFIG.botAddress, kind: 'EOA', required: true },
  { name: 'profitReceiverAddress', address: POLYGON_CHAIN_CONFIG.profitReceiverAddress, kind: 'EOA', required: true },
];

const TIMEOUT_MS = Number(process.env.TARGET_AUDIT_RPC_TIMEOUT_MS || 5000);

function rpcCandidates(): string[] {
  const env = [
    process.env.PRIMARY_READ_RPC_URL,
    process.env.EXACT_CALL_RPC_URL,
    process.env.CHAINSTACK_URL,
    process.env.RPC_URL,
    process.env.POLYGON_RPC_URL,
  ];
  const publicFallbacks = ['https://polygon-bor-rpc.publicnode.com', 'https://polygon-rpc.com'];
  const configured = Object.values(POLYGON_CHAIN_CONFIG.rpcEndpoints).filter((v): v is string => typeof v === 'string');
  return [...env, ...publicFallbacks, ...configured]
    .filter((v): v is string => Boolean(v) && /^https?:\/\//i.test(v))
    .filter((v, i, arr) => arr.indexOf(v) === i);
}

function labelRpc(url: string): string {
  try { return new URL(url).host; } catch { return 'invalid-rpc-url'; }
}

async function rpc(url: string, method: string, params: unknown[] = []): Promise<string> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ jsonrpc: '2.0', id: 1, method, params }),
      signal: controller.signal,
    });
    const data = await response.json() as { result?: string; error?: { message?: string } };
    if (!response.ok || data.error || typeof data.result !== 'string') {
      throw new Error(data.error?.message || `HTTP ${response.status}`);
    }
    return data.result;
  } finally {
    clearTimeout(timeout);
  }
}

async function selectRpc(): Promise<{ url: string; label: string; blockHex: string; block: number }> {
  const errors: string[] = [];
  for (const url of rpcCandidates()) {
    try {
      const chainId = Number(await rpc(url, 'eth_chainId'));
      if (chainId !== 137) throw new Error(`wrong chainId ${chainId}`);
      const blockHex = await rpc(url, 'eth_blockNumber');
      return { url, label: labelRpc(url), blockHex, block: Number(blockHex) };
    } catch (err) {
      errors.push(`${labelRpc(url)}=${err instanceof Error ? err.message : String(err)}`);
    }
  }
  throw new Error(`No usable Polygon RPC endpoint. ${errors.slice(0, 4).join(' | ')}`);
}

async function main(): Promise<void> {
  const { url, label, blockHex, block } = await selectRpc();
  let failures = 0;
  const seen = new Map<string, string[]>();

  console.log(`CONTRACT_TARGET_AUDIT|rpcHost=${label}|block=${block}|targets=${TARGETS.length}`);

  for (const target of TARGETS) {
    const addressOk = ethers.isAddress(target.address);
    let codeBytes = -1;
    let status = 'PASS';
    let reason = 'ok';

    if (!addressOk) {
      status = 'FAIL';
      reason = 'invalid_address';
    } else {
      const checksum = ethers.getAddress(target.address);
      seen.set(checksum, [...(seen.get(checksum) ?? []), target.name]);
      if (target.kind !== 'EOA') {
        const code = await rpc(url, 'eth_getCode', [checksum, blockHex]);
        codeBytes = Math.max(0, (code.length - 2) / 2);
        if (code === '0x') {
          status = target.required ? 'FAIL' : 'WARN';
          reason = 'no_bytecode';
        }
      }
    }

    if (status === 'FAIL') failures += 1;
    console.log(`TARGET|${status}|name=${target.name}|kind=${target.kind}|address=${target.address}|codeBytes=${codeBytes}|reason=${reason}`);
  }

  for (const [address, names] of seen.entries()) {
    if (names.length > 1) console.log(`ALIAS|address=${address}|names=${names.join(',')}`);
  }

  if (failures > 0) {
    console.error(`CONTRACT_TARGET_AUDIT=FAIL failures=${failures}`);
    process.exitCode = 1;
    return;
  }
  console.log('CONTRACT_TARGET_AUDIT=PASS');
}

main().catch((err) => {
  console.error(`CONTRACT_TARGET_AUDIT=FAIL reason=${err instanceof Error ? err.message : String(err)}`);
  process.exitCode = 1;
});
