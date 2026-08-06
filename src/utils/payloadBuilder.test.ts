import { describe, it, expect, vi, beforeEach } from 'vitest';
import { buildPayloadForRoute } from './payloadBuilder';
import { DodoV2Adapter, UniswapV3Adapter, getAdapter } from './adapters';
import type { ArbitrageRoute, PoolInfo } from '../types';
import { DODO_POLYGON_ADDRESSES } from './dodoCalldata';

vi.mock('./ethersBroadcaster', () => ({
  OMEGA_EXECUTOR_ABI: [
    'function executeDodoPackedSwap(bytes path, uint256 amountIn)',
    'function executeMultiHopSwap(tuple(address target, bytes callData, uint256 value)[] calls)',
  ],
}));

vi.mock('../config/chainConfig', () => ({
  POLYGON_CHAIN_CONFIG: {
    c1ArbExecutorAddress: '0x409ece3Fd71DFBd8f692B600f36A89301cb37346',
    profitReceiverAddress: '0xAd93CCE6b616d08973472345Fa42A0b34F52d713',
  },
}));

function makeDodoPool(overrides: Partial<PoolInfo> = {}): PoolInfo {
  return {
    id: 'dodo-pool-1',
    name: 'DODO-WMATIC-USDC',
    protocol: 'DODO_V2_PMM',
    category: 'SWAPPABLE_EXECUTION',
    address: '0x813fC12B3BE39Ab68B6f21Cd8a2BCED7d75b31f4', // A real DODO pool
    token0: { symbol: 'WMATIC', decimals: 18, address: '0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270' },
    token1: { symbol: 'USDC.e', decimals: 6, address: '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174' },
    feeBps: 10,
    reserve0USD: 1000000,
    reserve1USD: 1000000,
    isFundingPool: false,
    status: 'ACTIVE',
    ...overrides,
  };
}

function makeUniswapV3Pool(overrides: Partial<PoolInfo> = {}): PoolInfo {
  return {
    id: 'uni-v3-pool-1',
    name: 'UNI-V3-USDC-WETH',
    protocol: 'V3_CLMM',
    category: 'SWAPPABLE_EXECUTION',
    address: '0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640', // A real UNI-V3 pool
    token0: { symbol: 'USDC.e', decimals: 6, address: '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174' },
    token1: { symbol: 'WETH', decimals: 18, address: '0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619' },
    feeBps: 5, // Corresponds to 500 fee tier
    reserve0USD: 2000000,
    reserve1USD: 2000000,
    isFundingPool: false,
    status: 'ACTIVE',
    ...overrides,
  };
}

function makeRoute(pools: PoolInfo[], overrides: Partial<ArbitrageRoute> = {}): ArbitrageRoute {
  return {
    id: 'route-dodo-1',
    pathString: 'WMATIC→USDC.e',
    length: 1,
    pools,
    expectedYieldUSD: 0,
    vqcAlphaScore: 0.88,
    vqcWinProbability: 0.82,
    optimalInputUSD: 50000,
    optimalInputWei: '50000000000000000000000', // 50,000 * 10^18
    grossProfitUSD: 300,
    estimatedGasUSD: 0.5,
    netProfitUSD: 300,
    stage: 'SIMULATED',
    timestamp: new Date().toISOString(),
    slippageToleranceBps: 50,
    isSelfFundingRisk: false,
    ...overrides,
  };
}

describe('Adapter Framework', () => {
  it('getAdapter should return a DodoV2Adapter for "DODO_V2"', () => {
    const adapter = getAdapter('DODO_V2');
    expect(adapter).toBeInstanceOf(DodoV2Adapter);
    expect(adapter.protocol).toBe('DODO_V2');
  });

  it('getAdapter should return a UniswapV3Adapter for "UNISWAP_V3"', () => {
    const adapter = getAdapter('UNISWAP_V3');
    expect(adapter).toBeInstanceOf(UniswapV3Adapter);
    expect(adapter.protocol).toBe('UNISWAP_V3');
  });

  it('getAdapter should throw for an unknown protocol', () => {
    expect(() => getAdapter('UNKNOWN_PROTOCOL')).toThrow(
      '[AdapterFactory] No adapter found for protocol: UNKNOWN_PROTOCOL'
    );
  });
});

describe('PayloadBuilder', () => {
  it('should build a correct payload for a multi-hop route', async () => {
    const dodoPool = makeDodoPool(); // WMATIC -> USDC.e
    const uniPool = makeUniswapV3Pool({
      // USDC.e -> WETH
      token0: dodoPool.token1,
      token1: { symbol: 'WETH', decimals: 18, address: '0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619' },
    });

    const route = makeRoute([dodoPool, uniPool], {
      pathString: 'WMATIC→USDC.e→WETH',
      length: 2,
    });

    const payload = await buildPayloadForRoute(route);

    // The payload should target our own executor contract
    expect(payload.to).toBe('0x409ece3Fd71DFBd8f692B600f36A89301cb37346');
    expect(payload.value).toBe(0n);
    expect(payload.description).toContain('Execute 2-hop swap');

    // Verify the calldata for the multicall
    // 1. Selector for `executeMultiHopSwap`
    const selector = payload.data.slice(0, 10);
    expect(selector).toBe('0x0d08c4f5'); // keccak256('executeMultiHopSwap(tuple(address,bytes,uint256)[])')[:4]

    // 2. Check that the calldata contains the target addresses of both adapters
    const dodoAdapter = new DodoV2Adapter();
    const uniAdapter = new UniswapV3Adapter();
    expect(payload.data).toContain(dodoAdapter.protocol.slice(2).toLowerCase());
    expect(payload.data).toContain(uniAdapter.routerAddress.slice(2).toLowerCase());

    // 3. Check that the calldata contains the function selector for DODO's swap
    const dodoSwapSelector = '0a354383'; // executeDodoPackedSwap
    expect(payload.data).toContain(dodoSwapSelector);

    // 4. Check that the calldata contains the function selector for Uniswap's swap
    const uniSwapSelector = 'c04b8602'; // exactInputSingle
    expect(payload.data).toContain(uniSwapSelector);
  });

  it('should build a correct payload for a single-hop DODO route', async () => {
    const dodoPool = makeDodoPool();
    const route = makeRoute([dodoPool], {
      pathString: 'WMATIC→USDC.e',
      length: 1,
    });

    const payload = await buildPayloadForRoute(route);

    // The payload should still target our own executor contract for consistency
    expect(payload.to).toBe('0x409ece3Fd71DFBd8f692B600f36A89301cb37346');
    expect(payload.value).toBe(0n);
    expect(payload.description).toContain('Execute 1-hop swap');

    // Verify the calldata for the multicall
    const selector = payload.data.slice(0, 10);
    expect(selector).toBe('0x0d08c4f5'); // executeMultiHopSwap

    // Check that the calldata contains the target address of the DODO adapter
    const dodoAdapter = new DodoV2Adapter();
    expect(payload.data).toContain(dodoAdapter.protocol.slice(2).toLowerCase());
  });

  it('should throw an error for a route with no pools', async () => {
    const routeWithNoPools = makeRoute([]);
    await expect(buildPayloadForRoute(routeWithNoPools)).rejects.toThrow(
      '[PayloadBuilder] Route must contain at least one pool.'
    );
  });
});
