import type { PoolInfo, ProtocolType } from '../types';
import { POLYGON_TOKENS, CHAINLINK_FEEDS } from '../data/mockEngineData';

export type AssetRole =
  | 'FLASHLOAN_CAPITAL'
  | 'BASE_ROUTE_ASSET'
  | 'MID_TOKEN_ASSET'
  | 'SWAPPABLE_POOL_ASSET'
  | 'POOL_STATE_ASSET'
  | 'PRICE_ASSET';

export type VenueSource = 'AMM_POOL' | 'AGGREGATOR_DISCOVERY' | 'EXTERNAL_DISCOVERY';

export interface PipelineAsset {
  symbol: string;
  canonicalSymbol: string;
  aliases: string[];
  address: string;
  decimals: number;
  roles: AssetRole[];
  priceUSD?: number;
  maxFlashLoanUSD?: number;
  flashFeeBps?: number;
}

export interface VenueRegistryEntry {
  id: string;
  name: string;
  protocol: string;
  protocolType?: ProtocolType;
  source: VenueSource;
  executableCalldata: boolean;
}

const token = (key: keyof typeof POLYGON_TOKENS) => POLYGON_TOKENS[key];

export const FLASHLOAN_CAPITAL_ASSETS: PipelineAsset[] = [
  {
    symbol: 'WMATIC',
    canonicalSymbol: 'WPOL',
    aliases: ['WMATIC', 'WPOL', 'POL'],
    address: token('WMATIC').address,
    decimals: token('WMATIC').decimals,
    roles: ['FLASHLOAN_CAPITAL', 'BASE_ROUTE_ASSET', 'SWAPPABLE_POOL_ASSET', 'POOL_STATE_ASSET', 'PRICE_ASSET'],
    priceUSD: CHAINLINK_FEEDS.WPOL.priceUSD,
    maxFlashLoanUSD: 5_000_000,
    flashFeeBps: 5,
  },
  {
    symbol: 'USDC.e',
    canonicalSymbol: 'USDC.e',
    aliases: ['USDC.e', 'USDC'],
    address: token('USDC').address,
    decimals: token('USDC').decimals,
    roles: ['FLASHLOAN_CAPITAL', 'BASE_ROUTE_ASSET', 'SWAPPABLE_POOL_ASSET', 'POOL_STATE_ASSET', 'PRICE_ASSET'],
    priceUSD: CHAINLINK_FEEDS.USDC.priceUSD,
    maxFlashLoanUSD: 10_000_000,
    flashFeeBps: 5,
  },
  {
    symbol: 'USDC',
    canonicalSymbol: 'USDC',
    aliases: ['USDC', 'Native USDC'],
    address: token('USDC_NATIVE').address,
    decimals: token('USDC_NATIVE').decimals,
    roles: ['FLASHLOAN_CAPITAL', 'BASE_ROUTE_ASSET', 'SWAPPABLE_POOL_ASSET', 'POOL_STATE_ASSET', 'PRICE_ASSET'],
    priceUSD: CHAINLINK_FEEDS.USDC.priceUSD,
    maxFlashLoanUSD: 8_000_000,
    flashFeeBps: 5,
  },
  {
    symbol: 'USDT',
    canonicalSymbol: 'USDT',
    aliases: ['USDT'],
    address: token('USDT').address,
    decimals: token('USDT').decimals,
    roles: ['FLASHLOAN_CAPITAL', 'BASE_ROUTE_ASSET', 'SWAPPABLE_POOL_ASSET', 'POOL_STATE_ASSET', 'PRICE_ASSET'],
    priceUSD: CHAINLINK_FEEDS.USDT.priceUSD,
    maxFlashLoanUSD: 8_000_000,
    flashFeeBps: 5,
  },
  {
    symbol: 'WETH',
    canonicalSymbol: 'WETH',
    aliases: ['WETH', 'ETH'],
    address: token('WETH').address,
    decimals: token('WETH').decimals,
    roles: ['FLASHLOAN_CAPITAL', 'BASE_ROUTE_ASSET', 'SWAPPABLE_POOL_ASSET', 'POOL_STATE_ASSET', 'PRICE_ASSET'],
    priceUSD: CHAINLINK_FEEDS.WETH.priceUSD,
    maxFlashLoanUSD: 12_000_000,
    flashFeeBps: 5,
  },
  {
    symbol: 'WBTC',
    canonicalSymbol: 'WBTC',
    aliases: ['WBTC', 'BTC'],
    address: token('WBTC').address,
    decimals: token('WBTC').decimals,
    roles: ['FLASHLOAN_CAPITAL', 'BASE_ROUTE_ASSET', 'SWAPPABLE_POOL_ASSET', 'POOL_STATE_ASSET', 'PRICE_ASSET'],
    priceUSD: CHAINLINK_FEEDS.WBTC.priceUSD,
    maxFlashLoanUSD: 7_500_000,
    flashFeeBps: 5,
  },
  {
    symbol: 'DAI',
    canonicalSymbol: 'DAI',
    aliases: ['DAI'],
    address: token('DAI').address,
    decimals: token('DAI').decimals,
    roles: ['FLASHLOAN_CAPITAL', 'BASE_ROUTE_ASSET', 'SWAPPABLE_POOL_ASSET', 'POOL_STATE_ASSET', 'PRICE_ASSET'],
    priceUSD: CHAINLINK_FEEDS.DAI.priceUSD,
    maxFlashLoanUSD: 4_000_000,
    flashFeeBps: 5,
  },
];

export const MID_TOKEN_ASSETS: PipelineAsset[] = [
  { symbol: 'LINK', canonicalSymbol: 'LINK', aliases: ['LINK'], address: token('LINK').address, decimals: token('LINK').decimals, roles: ['MID_TOKEN_ASSET', 'SWAPPABLE_POOL_ASSET', 'POOL_STATE_ASSET', 'PRICE_ASSET'], priceUSD: CHAINLINK_FEEDS.LINK.priceUSD },
  { symbol: 'AAVE', canonicalSymbol: 'AAVE', aliases: ['AAVE'], address: token('AAVE').address, decimals: token('AAVE').decimals, roles: ['MID_TOKEN_ASSET', 'SWAPPABLE_POOL_ASSET', 'POOL_STATE_ASSET', 'PRICE_ASSET'], priceUSD: CHAINLINK_FEEDS.AAVE.priceUSD },
  { symbol: 'QUICK', canonicalSymbol: 'QUICK', aliases: ['QUICK'], address: token('QUICK').address, decimals: token('QUICK').decimals, roles: ['MID_TOKEN_ASSET', 'SWAPPABLE_POOL_ASSET', 'POOL_STATE_ASSET', 'PRICE_ASSET'] },
  { symbol: 'CRV', canonicalSymbol: 'CRV', aliases: ['CRV'], address: '0x172370d5Cd63279eFa6d502DAb29171933a610AF', decimals: 18, roles: ['MID_TOKEN_ASSET', 'SWAPPABLE_POOL_ASSET', 'POOL_STATE_ASSET', 'PRICE_ASSET'], priceUSD: CHAINLINK_FEEDS.CRV.priceUSD },
  { symbol: 'BAL', canonicalSymbol: 'BAL', aliases: ['BAL'], address: '0x9a71012B13CA4d3D0Cdc72A177DF3ef03b0E76A3', decimals: 18, roles: ['MID_TOKEN_ASSET', 'SWAPPABLE_POOL_ASSET', 'POOL_STATE_ASSET', 'PRICE_ASSET'], priceUSD: CHAINLINK_FEEDS.BAL.priceUSD },
  { symbol: 'GHST', canonicalSymbol: 'GHST', aliases: ['GHST'], address: token('GHST').address, decimals: token('GHST').decimals, roles: ['MID_TOKEN_ASSET', 'SWAPPABLE_POOL_ASSET', 'POOL_STATE_ASSET', 'PRICE_ASSET'] },
  { symbol: 'stMATIC', canonicalSymbol: 'stMATIC', aliases: ['stMATIC'], address: token('stMATIC').address, decimals: token('stMATIC').decimals, roles: ['MID_TOKEN_ASSET', 'SWAPPABLE_POOL_ASSET', 'POOL_STATE_ASSET', 'PRICE_ASSET'] },
  { symbol: 'MaticX', canonicalSymbol: 'MaticX', aliases: ['MaticX'], address: token('MaticX').address, decimals: token('MaticX').decimals, roles: ['MID_TOKEN_ASSET', 'SWAPPABLE_POOL_ASSET', 'POOL_STATE_ASSET', 'PRICE_ASSET'] },
];

export const SWAPPABLE_ASSETS: PipelineAsset[] = [
  ...FLASHLOAN_CAPITAL_ASSETS,
  ...MID_TOKEN_ASSETS,
];

export const PRICE_ASSETS: PipelineAsset[] = SWAPPABLE_ASSETS.filter((asset) => asset.roles.includes('PRICE_ASSET'));

export const EXECUTABLE_VENUES: VenueRegistryEntry[] = [
  { id: 'uniswap-v3', name: 'Uniswap V3', protocol: 'UniswapV3', protocolType: 'V3_CLMM', source: 'AMM_POOL', executableCalldata: true },
  { id: 'quickswap-v2', name: 'QuickSwap V2', protocol: 'QuickSwapV2', protocolType: 'QS_V2_CPMM', source: 'AMM_POOL', executableCalldata: true },
  { id: 'quickswap-v3', name: 'QuickSwap V3 Algebra', protocol: 'QuickSwapV3', protocolType: 'QS_V3_ALGEBRA', source: 'AMM_POOL', executableCalldata: true },
  { id: 'sushiswap-v2', name: 'SushiSwap V2', protocol: 'SushiSwapV2', protocolType: 'V2_CPMM', source: 'AMM_POOL', executableCalldata: true },
  { id: 'curve-polygon', name: 'Curve Polygon', protocol: 'Curve', protocolType: 'CURVE_STABLE', source: 'AMM_POOL', executableCalldata: true },
  { id: 'balancer-weighted', name: 'Balancer Weighted', protocol: 'BalancerV2', protocolType: 'BAL_WEIGHTED', source: 'AMM_POOL', executableCalldata: true },
  { id: 'dodo-v2-pmm', name: 'DODO V2 PMM', protocol: 'DodoV2', protocolType: 'DODO_V2_PMM', source: 'AMM_POOL', executableCalldata: true },
  { id: 'kyberswap-elastic', name: 'KyberSwap Elastic', protocol: 'KyberSwap', protocolType: 'V3_CLMM', source: 'AMM_POOL', executableCalldata: true },
];

export const DISCOVERY_ONLY_AGGREGATORS: VenueRegistryEntry[] = [
  { id: 'dexscreener', name: 'DEX Screener', protocol: 'DexScreener', source: 'EXTERNAL_DISCOVERY', executableCalldata: false },
  { id: 'oneinch', name: '1inch', protocol: '1inch', source: 'AGGREGATOR_DISCOVERY', executableCalldata: false },
  { id: 'zero-x', name: '0x', protocol: '0x', source: 'AGGREGATOR_DISCOVERY', executableCalldata: false },
  { id: 'paraswap', name: 'ParaSwap', protocol: 'ParaSwap', source: 'AGGREGATOR_DISCOVERY', executableCalldata: false },
  { id: 'openocean', name: 'OpenOcean', protocol: 'OpenOcean', source: 'AGGREGATOR_DISCOVERY', executableCalldata: false },
  { id: 'odos', name: 'Odos', protocol: 'Odos', source: 'AGGREGATOR_DISCOVERY', executableCalldata: false },
];

export const ALL_DISCOVERY_VENUES = [...EXECUTABLE_VENUES, ...DISCOVERY_ONLY_AGGREGATORS];

const norm = (value: string | undefined) => (value ?? '').trim().toLowerCase();

function indexAssets(assets: PipelineAsset[]) {
  const bySymbol = new Map<string, PipelineAsset>();
  const byAddress = new Map<string, PipelineAsset>();
  for (const asset of assets) {
    bySymbol.set(norm(asset.symbol), asset);
    bySymbol.set(norm(asset.canonicalSymbol), asset);
    for (const alias of asset.aliases) bySymbol.set(norm(alias), asset);
    byAddress.set(norm(asset.address), asset);
  }
  return { bySymbol, byAddress };
}

const swappableIndex = indexAssets(SWAPPABLE_ASSETS);
const flashIndex = indexAssets(FLASHLOAN_CAPITAL_ASSETS);
const priceIndex = indexAssets(PRICE_ASSETS);

export function resolveSwappableAsset(symbolOrAddress: string | undefined): PipelineAsset | undefined {
  return swappableIndex.byAddress.get(norm(symbolOrAddress)) ?? swappableIndex.bySymbol.get(norm(symbolOrAddress));
}

export function resolveFlashloanCapitalAsset(symbolOrAddress: string | undefined): PipelineAsset | undefined {
  return flashIndex.byAddress.get(norm(symbolOrAddress)) ?? flashIndex.bySymbol.get(norm(symbolOrAddress));
}

export function hasPriceAsset(symbolOrAddress: string | undefined): boolean {
  return priceIndex.byAddress.has(norm(symbolOrAddress)) || priceIndex.bySymbol.has(norm(symbolOrAddress));
}

export function isExecutableProtocol(protocol: ProtocolType): boolean {
  return EXECUTABLE_VENUES.some((venue) => venue.protocolType === protocol && venue.executableCalldata);
}

export function routeAssetSymbols(pools: PoolInfo[]): string[] {
  return Array.from(new Set(pools.flatMap((pool) => [pool.token0?.symbol, pool.token1?.symbol]).filter(Boolean) as string[]));
}

export function buildAssetUniverseProfile() {
  return {
    flashloanCapitalAssets: FLASHLOAN_CAPITAL_ASSETS.map((asset) => asset.symbol),
    baseRouteAssets: FLASHLOAN_CAPITAL_ASSETS.filter((asset) => asset.roles.includes('BASE_ROUTE_ASSET')).map((asset) => asset.symbol),
    midTokenAssets: MID_TOKEN_ASSETS.map((asset) => asset.symbol),
    swappablePoolStateAssets: SWAPPABLE_ASSETS.map((asset) => asset.symbol),
    priceAssets: PRICE_ASSETS.map((asset) => asset.symbol),
    executableDexes: EXECUTABLE_VENUES.map((venue) => venue.name),
    discoveryAggregators: DISCOVERY_ONLY_AGGREGATORS.map((venue) => venue.name),
    executableProtocols: Array.from(new Set(EXECUTABLE_VENUES.map((venue) => venue.protocolType).filter(Boolean))),
  };
}
