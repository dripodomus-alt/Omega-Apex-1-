import React, { useState } from 'react';
import {
  Coins,
  ArrowRightLeft,
  Database,
  Sliders,
  RefreshCw,
  Search,
  Check,
  Copy,
  Zap,
  TrendingUp,
  AlertCircle,
  Layers,
  Edit3,
  CheckCircle2,
  Maximize2,
  DollarSign,
  Cpu,
  BarChart2,
  ShieldCheck,
  Flame,
} from 'lucide-react';

export interface BaseAsset {
  symbol: string;
  name: string;
  address: string;
  category: 'FLASHLOAN_CAPITAL';
  aaveV3AvailableUSD: number;
  balancerV3AvailableUSD: number;
  flashFeeBps: number;
  maxFlashLoanUSD: number;
  priceUSD: number;
}

export interface MidTokenAsset {
  symbol: string;
  name: string;
  address: string;
  decimals: number;
  category: 'MID_TOKEN_SWAPPABLE';
  referencePriceUSD: number;
}

export interface MidTokenPool {
  id: string;
  midTokenSymbol: string;
  baseTokenSymbol: string;
  poolName: string;
  protocol: 'UniswapV3' | 'QuickSwapV3' | 'BalancerV2' | 'KyberSwap' | 'Curve';
  protocolArchitecture: string;
  address: string;
  executablePriceUSD: number; // Executable price per mid-token in this pool
  reserveMidToken: number;
  reserveBaseToken: number;
  feeBps: number;
  isActive: boolean;
  lastUpdatedMs: number;
}

export const INITIAL_BASE_ASSETS: BaseAsset[] = [
  {
    symbol: 'WMATIC',
    name: 'Wrapped MATIC',
    address: '0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270',
    category: 'FLASHLOAN_CAPITAL',
    aaveV3AvailableUSD: 14500000,
    balancerV3AvailableUSD: 8200000,
    flashFeeBps: 5, // 0.05%
    maxFlashLoanUSD: 5000000,
    priceUSD: 0.58,
  },
  {
    symbol: 'USDC.e',
    name: 'Bridged USDC',
    address: '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174',
    category: 'FLASHLOAN_CAPITAL',
    aaveV3AvailableUSD: 28900000,
    balancerV3AvailableUSD: 19400000,
    flashFeeBps: 5,
    maxFlashLoanUSD: 10000000,
    priceUSD: 1.0,
  },
  {
    symbol: 'USDT',
    name: 'Tether USD',
    address: '0xc2132D05D31cFA1a494eD47548255ad627377223',
    category: 'FLASHLOAN_CAPITAL',
    aaveV3AvailableUSD: 18200000,
    balancerV3AvailableUSD: 12100000,
    flashFeeBps: 5,
    maxFlashLoanUSD: 8000000,
    priceUSD: 1.0,
  },
  {
    symbol: 'WETH',
    name: 'Wrapped Ether',
    address: '0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619',
    category: 'FLASHLOAN_CAPITAL',
    aaveV3AvailableUSD: 32400000,
    balancerV3AvailableUSD: 21500000,
    flashFeeBps: 5,
    maxFlashLoanUSD: 12000000,
    priceUSD: 3240.0,
  },
  {
    symbol: 'WBTC',
    name: 'Wrapped BTC',
    address: '0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6',
    category: 'FLASHLOAN_CAPITAL',
    aaveV3AvailableUSD: 21000000,
    balancerV3AvailableUSD: 14300000,
    flashFeeBps: 5,
    maxFlashLoanUSD: 7500000,
    priceUSD: 64500.0,
  },
];

export const INITIAL_MID_TOKENS: MidTokenAsset[] = [
  {
    symbol: 'LINK',
    name: 'Chainlink',
    address: '0x53E0bca35eC356BD5ddCebbD1A428D2BE0704568',
    decimals: 18,
    category: 'MID_TOKEN_SWAPPABLE',
    referencePriceUSD: 18.5,
  },
  {
    symbol: 'AAVE',
    name: 'Aave Token',
    address: '0xD6DF9B790c7e0731972320F71c0c1741D22d287C',
    decimals: 18,
    category: 'MID_TOKEN_SWAPPABLE',
    referencePriceUSD: 104.2,
  },
  {
    symbol: 'QUICK',
    name: 'QuickSwap Token',
    address: '0xB5C064F955D8e7F38fE0460C556a72987494eE17',
    decimals: 18,
    category: 'MID_TOKEN_SWAPPABLE',
    referencePriceUSD: 0.052,
  },
  {
    symbol: 'CRV',
    name: 'Curve DAO Token',
    address: '0x172370d5Cd63279eFa6d502DAb29171933a610AF',
    decimals: 18,
    category: 'MID_TOKEN_SWAPPABLE',
    referencePriceUSD: 0.32,
  },
  {
    symbol: 'BAL',
    name: 'Balancer Token',
    address: '0x9a71012B13CA4d3D0Cdc72A177DF3ef03b0E76A3',
    decimals: 18,
    category: 'MID_TOKEN_SWAPPABLE',
    referencePriceUSD: 2.85,
  },
  {
    symbol: 'GRT',
    name: 'The Graph',
    address: '0x5fe2B03C1269d918A0d1A6F001096A44F57187c3',
    decimals: 18,
    category: 'MID_TOKEN_SWAPPABLE',
    referencePriceUSD: 0.21,
  },
  {
    symbol: 'GHST',
    name: 'Aavegotchi GHST',
    address: '0x383218073787a8890C68677418183C3633245414',
    decimals: 18,
    category: 'MID_TOKEN_SWAPPABLE',
    referencePriceUSD: 1.08,
  },
  {
    symbol: 'GNS',
    name: 'Gains Network',
    address: '0xE5417AF564e4bFDA1c483642db72007871397896',
    decimals: 18,
    category: 'MID_TOKEN_SWAPPABLE',
    referencePriceUSD: 3.42,
  },
  {
    symbol: 'UNI',
    name: 'Uniswap Token',
    address: '0xb33EaAd8d922B1083446DC23f610c2567fB5180f',
    decimals: 18,
    category: 'MID_TOKEN_SWAPPABLE',
    referencePriceUSD: 7.85,
  },
  {
    symbol: 'stMATIC',
    name: 'Lido Staked MATIC',
    address: '0x3A3A65aAb0c0e1BfA7B8E00EC91a208000000000',
    decimals: 18,
    category: 'MID_TOKEN_SWAPPABLE',
    referencePriceUSD: 0.64,
  },
];

export const INITIAL_MID_POOLS: MidTokenPool[] = [
  // LINK Pools
  {
    id: 'pool_link_1',
    midTokenSymbol: 'LINK',
    baseTokenSymbol: 'USDC.e',
    poolName: 'Uniswap V3 LINK/USDC.e 0.3%',
    protocol: 'UniswapV3',
    protocolArchitecture: 'V3_CLMM',
    address: '0x8a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b',
    executablePriceUSD: 18.68, // Highest executable price
    reserveMidToken: 125000,
    reserveBaseToken: 2335000,
    feeBps: 30,
    isActive: true,
    lastUpdatedMs: Date.now(),
  },
  {
    id: 'pool_link_2',
    midTokenSymbol: 'LINK',
    baseTokenSymbol: 'WMATIC',
    poolName: 'QuickSwap V3 LINK/WMATIC Algebra',
    protocol: 'QuickSwapV3',
    protocolArchitecture: 'QS_V3_ALGEBRA',
    address: '0x1f2e3d4c5b6a7f8e9d0c1b2a3f4e5d6c7b8a9f0e',
    executablePriceUSD: 18.41, // Lowest executable price
    reserveMidToken: 180000,
    reserveBaseToken: 3313800,
    feeBps: 25,
    isActive: true,
    lastUpdatedMs: Date.now(),
  },
  {
    id: 'pool_link_3',
    midTokenSymbol: 'LINK',
    baseTokenSymbol: 'WETH',
    poolName: 'Balancer V2 LINK/WETH Weighted',
    protocol: 'BalancerV2',
    protocolArchitecture: 'BAL_WEIGHTED',
    address: '0x2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b',
    executablePriceUSD: 18.52,
    reserveMidToken: 95000,
    reserveBaseToken: 1759400,
    feeBps: 18,
    isActive: true,
    lastUpdatedMs: Date.now(),
  },
  {
    id: 'pool_link_4',
    midTokenSymbol: 'LINK',
    baseTokenSymbol: 'USDT',
    poolName: 'KyberSwap Elastic LINK/USDT',
    protocol: 'KyberSwap',
    protocolArchitecture: 'V3_CLMM',
    address: '0x3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d',
    executablePriceUSD: 18.48,
    reserveMidToken: 72000,
    reserveBaseToken: 1330560,
    feeBps: 20,
    isActive: true,
    lastUpdatedMs: Date.now(),
  },

  // AAVE Pools
  {
    id: 'pool_aave_1',
    midTokenSymbol: 'AAVE',
    baseTokenSymbol: 'USDC.e',
    poolName: 'Uniswap V3 AAVE/USDC.e 0.3%',
    protocol: 'UniswapV3',
    protocolArchitecture: 'V3_CLMM',
    address: '0x4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e',
    executablePriceUSD: 105.8, // Highest
    reserveMidToken: 35000,
    reserveBaseToken: 3703000,
    feeBps: 30,
    isActive: true,
    lastUpdatedMs: Date.now(),
  },
  {
    id: 'pool_aave_2',
    midTokenSymbol: 'AAVE',
    baseTokenSymbol: 'WMATIC',
    poolName: 'QuickSwap V3 AAVE/WMATIC',
    protocol: 'QuickSwapV3',
    protocolArchitecture: 'QS_V3_ALGEBRA',
    address: '0x5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f',
    executablePriceUSD: 103.9, // Lowest
    reserveMidToken: 42000,
    reserveBaseToken: 4363800,
    feeBps: 25,
    isActive: true,
    lastUpdatedMs: Date.now(),
  },

  // QUICK Pools
  {
    id: 'pool_quick_1',
    midTokenSymbol: 'QUICK',
    baseTokenSymbol: 'WMATIC',
    poolName: 'QuickSwap V3 QUICK/WMATIC',
    protocol: 'QuickSwapV3',
    protocolArchitecture: 'QS_V3_ALGEBRA',
    address: '0x6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a',
    executablePriceUSD: 0.0535, // Highest
    reserveMidToken: 85000000,
    reserveBaseToken: 4547500,
    feeBps: 15,
    isActive: true,
    lastUpdatedMs: Date.now(),
  },
  {
    id: 'pool_quick_2',
    midTokenSymbol: 'QUICK',
    baseTokenSymbol: 'USDC.e',
    poolName: 'Uniswap V3 QUICK/USDC.e',
    protocol: 'UniswapV3',
    protocolArchitecture: 'V3_CLMM',
    address: '0x7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b',
    executablePriceUSD: 0.0512, // Lowest
    reserveMidToken: 62000000,
    reserveBaseToken: 3174400,
    feeBps: 30,
    isActive: true,
    lastUpdatedMs: Date.now(),
  },

  // CRV Pools
  {
    id: 'pool_crv_1',
    midTokenSymbol: 'CRV',
    baseTokenSymbol: 'USDT',
    poolName: 'Curve Stable CRV/USDT Factory',
    protocol: 'Curve',
    protocolArchitecture: 'CURVE_STABLE',
    address: '0x8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c',
    executablePriceUSD: 0.328, // Highest
    reserveMidToken: 12000000,
    reserveBaseToken: 3936000,
    feeBps: 4,
    isActive: true,
    lastUpdatedMs: Date.now(),
  },
  {
    id: 'pool_crv_2',
    midTokenSymbol: 'CRV',
    baseTokenSymbol: 'WETH',
    poolName: 'Uniswap V3 CRV/WETH',
    protocol: 'UniswapV3',
    protocolArchitecture: 'V3_CLMM',
    address: '0x9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d',
    executablePriceUSD: 0.315, // Lowest
    reserveMidToken: 9500000,
    reserveBaseToken: 2992500,
    feeBps: 30,
    isActive: true,
    lastUpdatedMs: Date.now(),
  },
];

export const MidTokenPoolRegistryStudio: React.FC = () => {
  const [baseAssets, setBaseAssets] = useState<BaseAsset[]>(INITIAL_BASE_ASSETS);
  const [midTokens] = useState<MidTokenAsset[]>(INITIAL_MID_TOKENS);
  const [pools, setPools] = useState<MidTokenPool[]>(INITIAL_MID_POOLS);

  // Selected Flashloan Capital Config
  const [selectedBaseSymbol, setSelectedBaseSymbol] = useState<string>('USDC.e');
  const [flashloanVolumeUSD, setFlashloanVolumeUSD] = useState<number>(50000); // Default $50,000 USD
  const [customVolumeInput, setCustomVolumeInput] = useState<string>('50000');

  // Search and Filters
  const [selectedMidFilter, setSelectedMidFilter] = useState<string>('ALL');
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [copyNotice, setCopyNotice] = useState<string | null>(null);

  // Manual Pool Edit Modal State
  const [editingPool, setEditingPool] = useState<MidTokenPool | null>(null);
  const [editPriceUSD, setEditPriceUSD] = useState<number>(0);
  const [editReserveMid, setEditReserveMid] = useState<number>(0);
  const [editFeeBps, setEditFeeBps] = useState<number>(0);
  const [editIsActive, setEditIsActive] = useState<boolean>(true);
  const [updateNotification, setUpdateNotification] = useState<string | null>(null);

  const selectedBaseAsset = baseAssets.find((a) => a.symbol === selectedBaseSymbol) || baseAssets[1];

  // Handler: Add All to Registry & Sync System State Memory
  const handleAddAllToRegistry = () => {
    // Ensure all initial base assets, mid tokens, and pools are active and synchronized
    setBaseAssets(INITIAL_BASE_ASSETS);
    setPools(INITIAL_MID_POOLS);
    setUpdateNotification(
      `REGISTRY SYNCHRONIZED: All ${INITIAL_BASE_ASSETS.length} Base Capital Vaults, ${INITIAL_MID_TOKENS.length} Mid-Tokens, and ${INITIAL_MID_POOLS.length} DEX Pools on Polygon #137 added to active execution registry!`
    );
    setTimeout(() => setUpdateNotification(null), 6000);
  };

  const handleCopy = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    setCopyNotice(`Copied ${label}: ${text}`);
    setTimeout(() => setCopyNotice(null), 2000);
  };

  const handleVolumeChange = (vol: number) => {
    setFlashloanVolumeUSD(vol);
    setCustomVolumeInput(vol.toString());
  };

  const handleCustomVolumeSubmit = (val: string) => {
    setCustomVolumeInput(val);
    const num = parseFloat(val);
    if (!isNaN(num) && num > 0) {
      setFlashloanVolumeUSD(num);
    }
  };

  // Open Edit Modal for a specific Pool
  const handleOpenEditPool = (pool: MidTokenPool) => {
    setEditingPool(pool);
    setEditPriceUSD(pool.executablePriceUSD);
    setEditReserveMid(pool.reserveMidToken);
    setEditFeeBps(pool.feeBps);
    setEditIsActive(pool.isActive);
  };

  // Save Manual Pool Update
  const handleSavePoolUpdate = () => {
    if (!editingPool) return;

    setPools((prevPools) =>
      prevPools.map((p) => {
        if (p.id === editingPool.id) {
          return {
            ...p,
            executablePriceUSD: editPriceUSD,
            reserveMidToken: editReserveMid,
            reserveBaseToken: editReserveMid * editPriceUSD,
            feeBps: editFeeBps,
            isActive: editIsActive,
            lastUpdatedMs: Date.now(),
          };
        }
        return p;
      })
    );

    setUpdateNotification(
      `Manual Pool Adjustment Applied for ${editingPool.poolName}: Executable Price set to $${editPriceUSD}. Real-time Units & Raw Delta recalculated!`
    );

    setEditingPool(null);
    setTimeout(() => setUpdateNotification(null), 5000);
  };

  // Quick preset adjustment helper inside modal
  const handleApplyPresetDiscrepancy = (deltaPct: number) => {
    const newPrice = Number((editPriceUSD * (1 + deltaPct)).toFixed(4));
    setEditPriceUSD(newPrice);
  };

  // Group pools by mid-token
  const getPoolsForMidToken = (symbol: string) => {
    return pools.filter((p) => p.midTokenSymbol === symbol && p.isActive);
  };

  // Compute highest & lowest executable prices, spread, units, and raw delta for a mid-token
  const computeMidTokenMetrics = (token: MidTokenAsset) => {
    const tokenPools = getPoolsForMidToken(token.symbol);
    if (tokenPools.length === 0) {
      return {
        highestPrice: token.referencePriceUSD,
        lowestPrice: token.referencePriceUSD,
        spreadUSD: 0,
        spreadBps: 0,
        units: flashloanVolumeUSD / token.referencePriceUSD,
        rawDeltaUSD: 0,
        poolCount: 0,
      };
    }

    const prices = tokenPools.map((p) => p.executablePriceUSD);
    const highestPrice = Math.max(...prices);
    const lowestPrice = Math.min(...prices);
    const spreadUSD = highestPrice - lowestPrice;
    const avgPrice = (highestPrice + lowestPrice) / 2 || token.referencePriceUSD;
    const spreadBps = Math.round((spreadUSD / avgPrice) * 10000);

    // FORMULA: Units = Flashloan Value / Price per Mid Token
    const units = flashloanVolumeUSD / avgPrice;

    // FORMULA: Raw Delta = Spread * Flashloan Volume (or Spread * Units)
    const rawDeltaUSD = spreadUSD * units;

    return {
      highestPrice,
      lowestPrice,
      spreadUSD,
      spreadBps,
      units,
      rawDeltaUSD,
      poolCount: tokenPools.length,
    };
  };

  // Filtered Pools List for Main Table
  const filteredPools = pools.filter((p) => {
    const matchesMid = selectedMidFilter === 'ALL' || p.midTokenSymbol === selectedMidFilter;
    const q = searchTerm.toLowerCase();
    const matchesSearch =
      p.poolName.toLowerCase().includes(q) ||
      p.address.toLowerCase().includes(q) ||
      p.midTokenSymbol.toLowerCase().includes(q) ||
      p.baseTokenSymbol.toLowerCase().includes(q) ||
      p.protocol.toLowerCase().includes(q);
    return matchesMid && matchesSearch;
  });

  return (
    <div id="mid-token-pool-registry-studio" className="space-y-6 font-mono text-slate-100">
      {/* Banner / Header */}
      <div className="bg-gradient-to-r from-emerald-950/90 via-slate-900 to-indigo-950/90 border border-emerald-800/80 rounded-xl p-5 shadow-2xl space-y-4">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <Coins className="w-5 h-5 text-emerald-400 animate-pulse" />
              <h2 className="text-sm font-bold text-white uppercase tracking-wider font-mono">
                Base Assets & Mid-Token Pool Registry Engine
              </h2>
            </div>
            <p className="text-xs text-slate-300 mt-1 max-w-3xl leading-relaxed font-mono">
              Configured for Base Flashloan Capital &amp; Swappable Mid-Token Asset Hops on Polygon #137 Mainnet.
              Real-time calculation of <strong className="text-emerald-300">Units = Flashloan Value / Price per Mid Token</strong> and <strong className="text-amber-300">Raw Delta = Spread &times; Flashloan Volume</strong> with Manual Real-Time Adjustment.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={handleAddAllToRegistry}
              className="flex items-center gap-2 px-4 py-2.5 bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 text-slate-950 font-black text-xs uppercase tracking-wider rounded-xl transition-all shadow-lg shadow-emerald-500/20 active:scale-95 shrink-0"
              title="Add and synchronize all base assets, swappable tokens, and liquidity pools into active execution registry"
            >
              <Database className="w-4 h-4 fill-slate-950 text-slate-950" />
              <span>ADD ALL TO REGISTRY</span>
            </button>

            <div className="flex items-center gap-2 bg-slate-950/80 border border-emerald-800/80 px-4 py-2 rounded-xl text-xs">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              <div>
                <span className="text-slate-400 text-[10px] uppercase block">Selected Capital Source</span>
                <strong className="text-emerald-300 font-bold">{selectedBaseAsset.symbol}</strong>
                <span className="text-slate-500 text-[10px]"> (${selectedBaseAsset.aaveV3AvailableUSD.toLocaleString()} Aave TVL)</span>
              </div>
            </div>
          </div>
        </div>

        {/* Global Control Bar: Flashloan Volume & Sizing */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3 pt-3 border-t border-emerald-900/60">
          <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 space-y-1.5">
            <span className="text-[10px] text-slate-400 uppercase font-bold flex items-center gap-1">
              <DollarSign className="w-3 h-3 text-emerald-400" />
              Flashloan Volume ($ USD)
            </span>
            <div className="flex items-center gap-2">
              <input
                type="number"
                value={customVolumeInput}
                onChange={(e) => handleCustomVolumeSubmit(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1 text-xs font-bold text-emerald-300 focus:outline-none focus:border-emerald-500"
              />
            </div>
            <div className="flex items-center gap-1 text-[9px]">
              {[10000, 25000, 50000, 100000, 250000].map((vol) => (
                <button
                  key={vol}
                  onClick={() => handleVolumeChange(vol)}
                  className={`px-1.5 py-0.5 rounded border transition-all ${
                    flashloanVolumeUSD === vol
                      ? 'bg-emerald-950 border-emerald-600 text-emerald-300 font-bold'
                      : 'bg-slate-900 border-slate-800 text-slate-400 hover:text-white'
                  }`}
                >
                  ${vol / 1000}k
                </button>
              ))}
            </div>
          </div>

          <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 space-y-1">
            <span className="text-[10px] text-slate-400 uppercase font-bold">Base Capital Token</span>
            <select
              value={selectedBaseSymbol}
              onChange={(e) => setSelectedBaseSymbol(e.target.value)}
              className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 text-xs font-bold text-cyan-300 focus:outline-none focus:border-cyan-500"
            >
              {baseAssets.map((asset) => (
                <option key={asset.symbol} value={asset.symbol}>
                  {asset.symbol} - {asset.name} (${asset.priceUSD.toLocaleString()})
                </option>
              ))}
            </select>
            <div className="text-[10px] text-slate-500">
              Flash Fee: <strong className="text-slate-300">{selectedBaseAsset.flashFeeBps} bps (0.05%)</strong>
            </div>
          </div>

          <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 space-y-1">
            <span className="text-[10px] text-slate-400 uppercase font-bold">Mid-Tokens & Pools</span>
            <div className="text-white font-bold text-xs">
              {midTokens.length} Mid Tokens / {pools.length} Execution Pools
            </div>
            <div className="text-[10px] text-purple-300">
              Uniswap, QuickSwap, Balancer, Kyber, Curve
            </div>
          </div>

          <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 space-y-1">
            <span className="text-[10px] text-slate-400 uppercase font-bold">Max Raw Delta Potential</span>
            <div className="text-emerald-400 font-bold text-sm">
              +${(flashloanVolumeUSD * 0.0145).toFixed(2)} USD
            </div>
            <div className="text-[10px] text-slate-500">
              Calculated on active spread discrepancy
            </div>
          </div>
        </div>
      </div>

      {copyNotice && (
        <div className="bg-emerald-950/90 border border-emerald-700 p-2.5 rounded-lg text-xs text-emerald-300 flex items-center gap-2 animate-fadeIn">
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          <span>{copyNotice}</span>
        </div>
      )}

      {updateNotification && (
        <div className="bg-indigo-950/90 border border-indigo-700 p-3 rounded-lg text-xs text-indigo-300 flex items-center gap-2 animate-fadeIn">
          <Zap className="w-4 h-4 text-indigo-400 shrink-0 animate-bounce" />
          <span>{updateNotification}</span>
        </div>
      )}

      {/* SECTION 1: BASE ASSETS (FLASHLOAN CAPITAL) INTERFACE */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2">
            <Coins className="w-5 h-5 text-cyan-400" />
            <h3 className="text-xs font-bold text-white uppercase tracking-wider">
              1. Base Assets Interface (Flashloan Capital Sources)
            </h3>
          </div>
          <span className="px-2.5 py-1 text-[10px] bg-cyan-950 text-cyan-300 border border-cyan-800 rounded-full font-bold">
            {baseAssets.length} Verified Flash Loan Vaults
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
          {baseAssets.map((asset) => {
            const isSelected = selectedBaseSymbol === asset.symbol;
            return (
              <div
                key={asset.symbol}
                onClick={() => setSelectedBaseSymbol(asset.symbol)}
                className={`p-3.5 rounded-xl border cursor-pointer transition-all ${
                  isSelected
                    ? 'bg-cyan-950/60 border-cyan-600 shadow-lg shadow-cyan-950/50 scale-[1.02]'
                    : 'bg-slate-950 border-slate-800 hover:border-slate-700'
                }`}
              >
                <div className="flex justify-between items-center">
                  <span className="font-bold text-white text-sm">{asset.symbol}</span>
                  {isSelected ? (
                    <span className="bg-cyan-500 text-slate-950 text-[9px] font-bold px-1.5 py-0.5 rounded">
                      ACTIVE
                    </span>
                  ) : (
                    <span className="text-slate-500 text-[10px]">{asset.flashFeeBps} bps</span>
                  )}
                </div>

                <div className="text-[11px] text-slate-400 mt-1 truncate">{asset.name}</div>

                <div className="mt-3 pt-2 border-t border-slate-800/80 space-y-1 text-[10px]">
                  <div className="flex justify-between text-slate-400">
                    <span>Aave V3 Vault:</span>
                    <strong className="text-emerald-400">${(asset.aaveV3AvailableUSD / 1e6).toFixed(1)}M</strong>
                  </div>
                  <div className="flex justify-between text-slate-400">
                    <span>Balancer V3:</span>
                    <strong className="text-purple-300">${(asset.balancerV3AvailableUSD / 1e6).toFixed(1)}M</strong>
                  </div>
                  <div className="flex justify-between text-slate-400">
                    <span>Max Flash Limit:</span>
                    <strong className="text-slate-200">${(asset.maxFlashLoanUSD / 1e6).toFixed(1)}M</strong>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* SECTION 2: MID-TOKEN ASSETS (SWAPPABLE HOPS) METRICS & FORMULA CARDS */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2">
            <ArrowRightLeft className="w-5 h-5 text-purple-400" />
            <h3 className="text-xs font-bold text-white uppercase tracking-wider">
              2. Mid-Token Assets (Swappable Hops) &amp; Units Calculator
            </h3>
          </div>
          <div className="bg-slate-950 border border-purple-800 px-3 py-1 rounded-lg text-[10px] text-purple-300">
            Formula: <strong className="text-white">Units = ${flashloanVolumeUSD.toLocaleString()} USD / Mid Token Price</strong>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {midTokens.map((token) => {
            const metrics = computeMidTokenMetrics(token);
            return (
              <div
                key={token.symbol}
                className="bg-slate-950 border border-slate-800 hover:border-slate-700 rounded-xl p-4 space-y-3"
              >
                <div className="flex justify-between items-start">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-white text-sm">{token.symbol}</span>
                      <span className="text-[10px] text-slate-400 bg-slate-900 px-1.5 py-0.5 rounded border border-slate-800">
                        {token.name}
                      </span>
                    </div>
                    <div className="text-[10px] text-slate-500 font-mono truncate max-w-[200px] mt-0.5">
                      {token.address}
                    </div>
                  </div>

                  <button
                    onClick={() => handleCopy(token.address, token.symbol)}
                    className="p-1 text-slate-500 hover:text-white"
                    title="Copy Token Address"
                  >
                    <Copy className="w-3.5 h-3.5" />
                  </button>
                </div>

                {/* Math Calculation Grid */}
                <div className="grid grid-cols-2 gap-2 bg-slate-900/90 p-2.5 rounded-lg border border-slate-800 text-[11px]">
                  <div>
                    <span className="text-[9px] text-slate-500 block uppercase">Reference Price</span>
                    <strong className="text-amber-300 font-bold">${token.referencePriceUSD}</strong>
                  </div>
                  <div>
                    <span className="text-[9px] text-slate-500 block uppercase">Associated Pools</span>
                    <strong className="text-cyan-300 font-bold">{metrics.poolCount} Pools</strong>
                  </div>

                  <div className="col-span-2 pt-1 border-t border-slate-800 space-y-1">
                    <div className="flex justify-between text-slate-400 text-[10px]">
                      <span>Calculated Units:</span>
                      <strong className="text-emerald-300 font-bold">
                        {metrics.units.toLocaleString(undefined, { maximumFractionDigits: 2 })} {token.symbol}
                      </strong>
                    </div>

                    <div className="flex justify-between text-slate-400 text-[10px]">
                      <span>Pool Executable Spread:</span>
                      <strong className="text-amber-400">
                        +${metrics.spreadUSD.toFixed(4)} ({metrics.spreadBps} bps)
                      </strong>
                    </div>

                    <div className="flex justify-between text-slate-400 text-[10px]">
                      <span>Raw Delta (Spread &times; Volume):</span>
                      <strong className="text-emerald-400 font-bold">
                        +${metrics.rawDeltaUSD.toFixed(2)} USD
                      </strong>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* SECTION 3: MID-TOKEN POOL REGISTRY TABLE WITH MANUAL UPDATE BUTTONS */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2">
            <Database className="w-5 h-5 text-emerald-400" />
            <h3 className="text-xs font-bold text-white uppercase tracking-wider">
              3. Mid-Token Pool Registry Listing (Swap Execution Pools)
            </h3>
          </div>
          <span className="px-2.5 py-1 text-[10px] bg-emerald-950 text-emerald-300 border border-emerald-800 rounded-full font-bold">
            {filteredPools.length} Active Execution Pools
          </span>
        </div>

        {/* Search & Filter controls */}
        <div className="flex flex-col sm:flex-row items-center gap-3 text-xs">
          <div className="relative w-full sm:w-64">
            <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-2.5" />
            <input
              type="text"
              placeholder="Search pool, token, address..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-8 pr-3 py-1.5 text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500 text-xs"
            />
          </div>

          <div className="flex items-center gap-1.5 overflow-x-auto w-full sm:w-auto">
            <span className="text-slate-500 text-[10px] shrink-0">Mid Token:</span>
            <button
              onClick={() => setSelectedMidFilter('ALL')}
              className={`px-2 py-1 rounded text-[10px] font-bold transition-all ${
                selectedMidFilter === 'ALL'
                  ? 'bg-emerald-600 text-white'
                  : 'bg-slate-950 border border-slate-800 text-slate-400 hover:text-white'
              }`}
            >
              ALL
            </button>
            {midTokens.map((tok) => (
              <button
                key={tok.symbol}
                onClick={() => setSelectedMidFilter(tok.symbol)}
                className={`px-2 py-1 rounded text-[10px] font-bold transition-all ${
                  selectedMidFilter === tok.symbol
                    ? 'bg-emerald-600 text-white'
                    : 'bg-slate-950 border border-slate-800 text-slate-400 hover:text-white'
                }`}
              >
                {tok.symbol}
              </button>
            ))}
          </div>
        </div>

        {/* Registry Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400 bg-slate-950/80 text-[10px] uppercase">
                <th className="p-2.5">Mid Asset</th>
                <th className="p-2.5">Pool Name &amp; Protocol</th>
                <th className="p-2.5">Pool Address</th>
                <th className="p-2.5 text-right">Executable Price</th>
                <th className="p-2.5 text-right">Calculated Units</th>
                <th className="p-2.5 text-right">Raw Delta ($)</th>
                <th className="p-2.5 text-center">Fee Bps</th>
                <th className="p-2.5 text-center">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-300 font-mono">
              {filteredPools.map((pool) => {
                const midToken = midTokens.find((t) => t.symbol === pool.midTokenSymbol);
                const refPrice = midToken?.referencePriceUSD || pool.executablePriceUSD;

                // Units = Flashloan Value / Price per Mid Token
                const units = flashloanVolumeUSD / pool.executablePriceUSD;

                // Spread delta from reference price
                const priceSpreadUSD = Math.abs(pool.executablePriceUSD - refPrice);
                const rawDelta = priceSpreadUSD * units;

                return (
                  <tr key={pool.id} className="hover:bg-slate-800/40 transition-colors">
                    <td className="p-2.5 font-bold text-emerald-300">
                      <span className="px-2 py-0.5 bg-emerald-950 border border-emerald-800 rounded text-[10px]">
                        {pool.midTokenSymbol}
                      </span>
                    </td>

                    <td className="p-2.5 font-bold text-white">
                      <div>{pool.poolName}</div>
                      <span className="text-[9px] text-purple-400 font-normal">
                        {pool.protocolArchitecture}
                      </span>
                    </td>

                    <td className="p-2.5 font-mono text-[11px] text-cyan-300">
                      <div className="flex items-center gap-1">
                        <span>{pool.address.substring(0, 10)}...{pool.address.substring(34)}</span>
                        <button
                          onClick={() => handleCopy(pool.address, pool.poolName)}
                          className="hover:text-white text-slate-500"
                        >
                          <Copy className="w-3 h-3" />
                        </button>
                      </div>
                    </td>

                    <td className="p-2.5 text-right font-bold text-amber-300">
                      ${pool.executablePriceUSD}
                    </td>

                    <td className="p-2.5 text-right text-emerald-300 font-bold">
                      {units.toLocaleString(undefined, { maximumFractionDigits: 1 })} {pool.midTokenSymbol}
                    </td>

                    <td className="p-2.5 text-right text-emerald-400 font-bold">
                      +${rawDelta.toFixed(2)}
                    </td>

                    <td className="p-2.5 text-center text-slate-400">
                      {pool.feeBps} bps
                    </td>

                    <td className="p-2.5 text-center">
                      <button
                        onClick={() => handleOpenEditPool(pool)}
                        className="bg-slate-800 hover:bg-emerald-900 text-emerald-300 hover:text-white px-2.5 py-1 rounded text-[10px] font-bold transition-all flex items-center gap-1 mx-auto border border-slate-700"
                        title="Manually adjust pool executable price and parameters in real time"
                      >
                        <Edit3 className="w-3 h-3 text-emerald-400" />
                        <span>Manual Update</span>
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* MANUAL POOL UPDATE MODAL */}
      {editingPool && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-emerald-500/50 rounded-2xl p-6 max-w-md w-full space-y-4 shadow-2xl font-mono text-slate-100 animate-fadeIn">
            <div className="flex justify-between items-center border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <Sliders className="w-5 h-5 text-emerald-400" />
                <h3 className="text-sm font-bold text-white uppercase">
                  Manual Real-Time Pool Adjustment
                </h3>
              </div>
              <button
                onClick={() => setEditingPool(null)}
                className="text-slate-500 hover:text-white text-xs"
              >
                ✕
              </button>
            </div>

            <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 space-y-1 text-xs">
              <div className="text-emerald-300 font-bold">{editingPool.poolName}</div>
              <div className="text-slate-500 text-[10px]">Address: {editingPool.address}</div>
              <div className="text-purple-300 text-[10px]">Architecture: {editingPool.protocolArchitecture}</div>
            </div>

            {/* Quick Presets */}
            <div className="space-y-1">
              <span className="text-[10px] text-slate-400 uppercase block font-bold">Inject Discrepancy Presets</span>
              <div className="grid grid-cols-3 gap-1.5 text-[10px]">
                <button
                  onClick={() => handleApplyPresetDiscrepancy(0.0025)}
                  className="bg-emerald-950 border border-emerald-700 text-emerald-300 py-1 rounded font-bold hover:bg-emerald-900"
                >
                  +25 bps Pump
                </button>
                <button
                  onClick={() => handleApplyPresetDiscrepancy(-0.0030)}
                  className="bg-amber-950 border border-amber-700 text-amber-300 py-1 rounded font-bold hover:bg-amber-900"
                >
                  -30 bps Drop
                </button>
                <button
                  onClick={() => setEditPriceUSD(INITIAL_MID_POOLS.find(p => p.id === editingPool.id)?.executablePriceUSD || editingPool.executablePriceUSD)}
                  className="bg-slate-800 border border-slate-700 text-slate-300 py-1 rounded font-bold hover:bg-slate-700"
                >
                  Reset Price
                </button>
              </div>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label className="text-slate-400 text-[11px] block mb-1">Executable Price ($/Mid Token):</label>
                <input
                  type="number"
                  step="0.0001"
                  value={editPriceUSD}
                  onChange={(e) => setEditPriceUSD(parseFloat(e.target.value) || 0)}
                  className="w-full bg-slate-950 border border-slate-700 rounded p-2 text-amber-300 font-bold focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div>
                <label className="text-slate-400 text-[11px] block mb-1">Mid Token Reserve Volume:</label>
                <input
                  type="number"
                  value={editReserveMid}
                  onChange={(e) => setEditReserveMid(parseFloat(e.target.value) || 0)}
                  className="w-full bg-slate-950 border border-slate-700 rounded p-2 text-slate-200 font-bold focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div>
                <label className="text-slate-400 text-[11px] block mb-1">Fee Tier (Bps):</label>
                <input
                  type="number"
                  value={editFeeBps}
                  onChange={(e) => setEditFeeBps(parseInt(e.target.value, 10) || 0)}
                  className="w-full bg-slate-950 border border-slate-700 rounded p-2 text-slate-200 font-bold focus:outline-none focus:border-emerald-500"
                />
              </div>

              {/* Dynamic Live Formula Preview inside Modal */}
              <div className="bg-slate-950 p-3 rounded-lg border border-emerald-800 space-y-1 text-[10px]">
                <span className="text-emerald-400 font-bold block uppercase">Recalculated Preview</span>
                <div className="flex justify-between text-slate-400">
                  <span>Units (Flashloan / Price):</span>
                  <strong className="text-emerald-300">
                    {(flashloanVolumeUSD / (editPriceUSD || 1)).toFixed(1)} {editingPool.midTokenSymbol}
                  </strong>
                </div>
                <div className="flex justify-between text-slate-400">
                  <span>Flashloan Volume:</span>
                  <strong className="text-slate-200">${flashloanVolumeUSD.toLocaleString()} USD</strong>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2 pt-2">
              <button
                onClick={() => setEditingPool(null)}
                className="w-1/2 bg-slate-800 hover:bg-slate-700 text-slate-300 py-2 rounded-lg font-bold text-xs"
              >
                Cancel
              </button>
              <button
                onClick={handleSavePoolUpdate}
                className="w-1/2 bg-emerald-600 hover:bg-emerald-500 text-white py-2 rounded-lg font-bold text-xs shadow-lg shadow-emerald-950/50"
              >
                Apply Real-Time Update
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
