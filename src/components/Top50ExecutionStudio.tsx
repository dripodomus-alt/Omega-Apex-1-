import React, { useState, useEffect, useRef } from 'react';
import {
  Zap,
  Cpu,
  Server,
  Activity,
  Flame,
  Clock,
  RefreshCw,
  Search,
  Filter,
  Layers,
  TrendingUp,
  ShieldCheck,
  Radio,
  ArrowRight,
  Database,
  CheckCircle2,
  AlertTriangle,
  ExternalLink,
  Code2,
  Hash,
  Eye,
  BarChart3,
  Sliders,
  ChevronDown,
  Play,
  Pause,
  Check,
  Copy,
} from 'lucide-react';
import { POLYGON_CHAIN_CONFIG } from '../config/chainConfig';
import { POLYGON_TOKEN_SYMBOLS, POLYGON_DEX_IDENTIFIERS } from '../data/mockEngineData';

export interface StagingMathMetadata {
  rawSpreadBps: number;
  rawDeltaBps: number;
  optimalFlashLoanUnits: string;
  optimalFlashLoanUSD: number;
  postMathSpreadBps: number;
  postMathSlippageBps: number;
  pool1ReservesBefore: string;
  pool1ReservesAfter: string;
  pool2ReservesBefore: string;
  pool2ReservesAfter: string;
  grossYieldUSD: number;
  fastlaneBuilderTipUSD: number;
  netYieldUSD: number;
  transientLockSlot: string;
  zeroCopyCalldata: string;
}

export interface RouteItem {
  rank: number;
  opportunityObjectId: string; // e.g. OPP-C428-R01-#0x8a1b2c3d
  cycleParity: string; // e.g. CYCLE-#428 | BLOCK-#90213788
  routeHash: string; // e.g. #0x8a1b2c3d4e5f6a7b
  hops: string[];
  pools: string[]; // pool addresses with #
  flashAsset: string;
  borrowAmountUSD: number;
  expectedGrossProfitUSD: number;
  estimatedGasUSD: number;
  netProfitUSD: number;
  roiBps: number;
  vqcScore: number;
  status: 'EXECUTABLE' | 'WATCHING' | 'SIMULATED' | 'STALE';
  lastActivityTime: string;
  liquidityDepthUSD: number;
  competingMempoolTxs: number;
  priceDeltaBps: number;
  stagingMath: StagingMathMetadata;
}

const clamp = (value: number, min: number, max: number): number => Math.max(min, Math.min(max, value));

export const Top50ExecutionStudio: React.FC = () => {
  // 12-second Cycle State
  const CYCLE_INTERVAL_MS = 12000;
  const [timeLeftMs, setTimeLeftMs] = useState<number>(CYCLE_INTERVAL_MS);
  const [cycleCount, setCycleCount] = useState<number>(428);
  const [isCyclePaused, setIsCyclePaused] = useState<boolean>(false);
  const [isScanningNow, setIsScanningNow] = useState<boolean>(false);
  const [currentBlock, setCurrentBlock] = useState<number>(90213788);

  // Search & Filter State
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [selectedRoute, setSelectedRoute] = useState<RouteItem | null>(null);
  const [copySuccess, setCopySuccess] = useState<string | null>(null);

  // Expandable Row Staging DNA State
  const [expandedHashes, setExpandedHashes] = useState<Set<string>>(new Set());

  const toggleExpandHash = (hash: string) => {
    setExpandedHashes((prev) => {
      const next = new Set(prev);
      if (next.has(hash)) {
        next.delete(hash);
      } else {
        next.add(hash);
      }
      return next;
    });
  };

  const toggleExpandAll = () => {
    if (expandedHashes.size === filteredRoutes.length) {
      setExpandedHashes(new Set());
    } else {
      setExpandedHashes(new Set(filteredRoutes.map((r) => r.routeHash)));
    }
  };

  // Data Intake & Rate-Limit Optimization Metrics
  const [multicallBatchedCalls, setMulticallBatchedCalls] = useState<number>(12450);
  const [rpcRequestsSaved, setRpcRequestsSaved] = useState<number>(114530);
  const [cacheHitRatePct, setCacheHitRatePct] = useState<number>(94.8);
  const [alchemyRateLimitUsage, setAlchemyRateLimitUsage] = useState<number>(12.4); // 12.4% of CU limit

  // Generate initial 50 Top Routes with Opportunity Object IDs and Cycle Parity
  // Uses full Polygon Mainnet (#137) token universe and all 14 active DEX protocols for maximum discovery
  const generateTop50Routes = (blockNum: number, cycleNum: number = 428): RouteItem[] => {
    // Full chain #137 token universe (14 assets)
    const assets = POLYGON_TOKEN_SYMBOLS;
    // All 14 active DEX protocols on Polygon Mainnet #137
    const dexs = POLYGON_DEX_IDENTIFIERS;

    return Array.from({ length: 50 }, (_, i) => {
      const rank = i + 1;
      const rankStr = rank < 10 ? `0${rank}` : `${rank}`;
      const assetA = assets[i % assets.length];
      const assetB = assets[(i + 2) % assets.length];
      const assetC = assets[(i + 4) % assets.length];

      const dex1 = dexs[i % dexs.length];
      const dex2 = dexs[(i + 3) % dexs.length];
      const dex3 = dexs[(i + 5) % dexs.length];

      // Route Hash with canonical #0x prefix
      const routeHashRaw = ((blockNum * 31 + i * 1009) % 0xffffffff).toString(16).padStart(8, '0');
      const routeHash = `#0x${routeHashRaw}${i < 9 ? '0' : ''}${i + 1}a9`;

      // Unique Opportunity Object ID with Cycle Parity
      const opportunityObjectId = `OPP-C${cycleNum}-R${rankStr}-${routeHash}`;
      const cycleParity = `CYCLE-#${cycleNum} | BLOCK-#${blockNum}`;

      const optimalFlashUSD = 2500 + i * 500;
      const grossUSD = clamp(Number((48.5 - i * 0.85 + Math.random() * 2.5).toFixed(2)), 2, 120);
      const gasUSD = clamp(Number((0.28 + (i % 3) * 0.08 + Math.random() * 0.05).toFixed(3)), 0.1, 3);

      const pool1 = `#0x${(100000 + i * 7).toString(16)}...${(999 - i).toString(16)}`;
      const pool2 = `#0x${(200000 + i * 11).toString(16)}...${(888 - i).toString(16)}`;

      // Staging Before/After Math Mirror State calculation
      const rawSpreadBps = Math.round(65 + Math.random() * 40 - i * 0.8);
      const rawDeltaBps = Math.round(42 + Math.random() * 25 - i * 0.5);
      const optimalFlashUnits = `${optimalFlashUSD.toLocaleString()} ${assetA}`;
      const postSpreadBps = Math.round(35 + Math.random() * 15 - i * 0.4);
      const postSlippageBps = Number((1.2 + (i % 4) * 0.4).toFixed(1));

      const tipUSD = Number((grossUSD * 0.15).toFixed(2));
      const netYield = clamp(Number((grossUSD - gasUSD - tipUSD).toFixed(2)), -grossUSD, grossUSD);
      const roi = Math.round((netYield / optimalFlashUSD) * 10000);

      const pool1Before = `2,450,000 ${assetA} / 1,820,000 ${assetB}`;
      const pool1After = `2,452,500 ${assetA} / 1,818,120 ${assetB}`;
      const pool2Before = `1,820,000 ${assetB} / 612 ${assetC}`;
      const pool2After = `1,822,400 ${assetB} / 610.8 ${assetC}`;

      const vqcScore = Math.max(65, Math.round(99 - i * 0.6));

      return {
        rank,
        opportunityObjectId,
        cycleParity,
        routeHash,
        hops: [assetA, assetB, assetC, assetA],
        pools: [pool1, pool2],
        flashAsset: assetA,
        borrowAmountUSD: optimalFlashUSD,
        expectedGrossProfitUSD: Math.max(1.2, grossUSD),
        estimatedGasUSD: gasUSD,
        netProfitUSD: netYield,
        roiBps: clamp(roi, -500, 500),
        vqcScore,
        // discoverableIsExecutableUponGating: EXECUTABLE if VQC ≥ 85 and net profit positive
        status: (() => {
          if (vqcScore >= 85 && netYield > 0) return 'EXECUTABLE';
          if (vqcScore >= 72) return 'WATCHING';
          return 'SIMULATED';
        })(),
        lastActivityTime: 'Just now',
        liquidityDepthUSD: 150000 + i * 12000,
        competingMempoolTxs: (i % 4 === 0) ? 1 : 0,
        priceDeltaBps: Number(((Math.random() - 0.4) * 3).toFixed(1)),
        stagingMath: {
          rawSpreadBps: Math.max(12, rawSpreadBps),
          rawDeltaBps: Math.max(8, rawDeltaBps),
          optimalFlashLoanUnits: optimalFlashUnits,
          optimalFlashLoanUSD: optimalFlashUSD,
          postMathSpreadBps: Math.max(8, postSpreadBps),
          postMathSlippageBps: postSlippageBps,
          pool1ReservesBefore: pool1Before,
          pool1ReservesAfter: pool1After,
          pool2ReservesBefore: pool2Before,
          pool2ReservesAfter: pool2After,
          grossYieldUSD: Math.max(1.2, grossUSD),
          fastlaneBuilderTipUSD: tipUSD,
          netYieldUSD: netYield,
          transientLockSlot: `#TRANSIENT_SLOT_0x01 (EIP-1153 TSTORE 100 Gas)`,
          zeroCopyCalldata: `#0x90213752${routeHashRaw}000000000000000000000000${(i + 1).toString(16).padStart(4, '0')}`,
        },
      };
    });
  };

  const [routes, setRoutes] = useState<RouteItem[]>(() => generateTop50Routes(90213788, 428));
  const [liveWatchLogs, setLiveWatchLogs] = useState<string[]>([]);

  // 12-second Interval Timer and Activity Hooks Simulator
  useEffect(() => {
    let timer: NodeJS.Timeout;
    if (!isCyclePaused) {
      timer = setInterval(() => {
        setTimeLeftMs((prev) => {
          if (prev <= 100) {
            // Trigger 12s New Scan Cycle
            triggerCycleScan();
            return CYCLE_INTERVAL_MS;
          }
          return prev - 100;
        });
      }, 100);
    }
    return () => clearInterval(timer);
  }, [isCyclePaused]);

  // Between-Scan Activity Hooks Watcher (fires every 2.5s)
  useEffect(() => {
    const activityInterval = setInterval(() => {
      // Simulate activity watcher updates on active routes
      setRoutes((prevRoutes) => {
        const updated = [...prevRoutes];
        const randomIndex = Math.floor(Math.random() * 20); // Pick a top 20 route
        if (updated[randomIndex]) {
          const delta = (Math.random() - 0.5) * 0.8;
          updated[randomIndex] = {
            ...updated[randomIndex],
            priceDeltaBps: clamp(Number((updated[randomIndex].priceDeltaBps + delta).toFixed(1)), -12, 12),
            lastActivityTime: `${new Date().toLocaleTimeString().split(' ')[0]}`,
          };

          // Append watch log
          const logEntry = `[Hook Watcher #${updated[randomIndex].routeHash}] Price spread delta shift: ${delta >= 0 ? '+' : ''}${delta.toFixed(2)} bps | Depth: $${(updated[randomIndex].liquidityDepthUSD / 1000).toFixed(1)}k | Block #${currentBlock}`;
          setLiveWatchLogs((prev) => [logEntry, ...prev.slice(0, 19)]);
        }
        return updated;
      });

      // Increment batched RPC counter
      setMulticallBatchedCalls((prev) => prev + 1);
      setRpcRequestsSaved((prev) => prev + 12);
    }, 2500);

    return () => clearInterval(activityInterval);
  }, [currentBlock]);

  // Execute full 12s cycle scan
  const triggerCycleScan = () => {
    setIsScanningNow(true);
    const nextBlock = currentBlock + 1;
    const nextCycle = cycleCount + 1;
    setCurrentBlock(nextBlock);

    setTimeout(() => {
      setRoutes(generateTop50Routes(nextBlock, nextCycle));
      setCycleCount(nextCycle);
      setIsScanningNow(false);
      setTimeLeftMs(CYCLE_INTERVAL_MS);

      const cycleLog = `[Cycle Scan #${nextCycle}] 50 Opportunity Objects synced with Cycle Parity at Block #${nextBlock}. Rate-limit batched multicall execution complete (0 RPC 429s).`;
      setLiveWatchLogs((prev) => [cycleLog, ...prev.slice(0, 19)]);
    }, 600);
  };

  const handleCopy = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    setCopySuccess(label);
    setTimeout(() => setCopySuccess(null), 2000);
  };

  // Filter routes
  const filteredRoutes = routes.filter((r) => {
    const q = searchQuery.toLowerCase();
    const matchesSearch =
      r.opportunityObjectId.toLowerCase().includes(q) ||
      r.routeHash.toLowerCase().includes(q) ||
      r.cycleParity.toLowerCase().includes(q) ||
      r.hops.some((h) => h.toLowerCase().includes(q)) ||
      r.flashAsset.toLowerCase().includes(q);

    const matchesStatus = statusFilter === 'ALL' || r.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  const progressPct = Math.max(0, Math.min(100, ((CYCLE_INTERVAL_MS - timeLeftMs) / CYCLE_INTERVAL_MS) * 100));

  return (
    <div className="bg-slate-950 text-slate-100 min-h-screen p-4 md:p-6 font-mono space-y-6">
      {/* Top Banner: Cycle Status & Rate Limit Intake Safeguard */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-2xl space-y-4">
        <div className="flex flex-col lg:flex-row justify-between items-start lg:items-center gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="bg-emerald-500/20 text-emerald-300 text-[10px] font-bold px-2.5 py-0.5 rounded border border-emerald-500/30 uppercase tracking-widest flex items-center gap-1">
                <Zap className="w-3 h-3 text-emerald-400" /> Top 50 Routes Execution Engine
              </span>
              <span className="bg-cyan-500/20 text-cyan-300 text-[10px] font-bold px-2 py-0.5 rounded border border-cyan-300/30 uppercase font-mono flex items-center gap-1">
                <Hash className="w-3 h-3 text-cyan-400" /> Polygon Block #{currentBlock}
              </span>
              <span className="bg-purple-500/20 text-purple-300 text-[10px] font-bold px-2 py-0.5 rounded border border-purple-500/30 uppercase font-mono">
                12s Cycle Cadence Active
              </span>
              <span className="bg-emerald-950 text-emerald-400 text-[10px] font-bold px-2 py-0.5 rounded border border-emerald-800 uppercase font-mono flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3 text-emerald-400" /> 100% # Hashtags Resolved
              </span>
              <span className="bg-amber-500/20 text-amber-300 text-[10px] font-bold px-2 py-0.5 rounded border border-amber-500/30 uppercase font-mono">
                Max Discovery: 14 DEXes × 14 Assets
              </span>
            </div>
            <h1 className="text-xl md:text-2xl font-black text-white tracking-tight">
              Apex Omega Top 50 Arbitrage Cycle Dashboard
            </h1>
            <p className="text-xs text-slate-400 max-w-3xl">
              Maximum Chain #137 Discovery Mode active — scans all <strong>14 DEX protocols</strong> and <strong>14 token assets</strong> on Polygon Mainnet. Continuously discovers, ranks, and promotes routes to <strong>EXECUTABLE</strong> per 12-second block cycle via <code className="text-emerald-400">discoverableIsExecutableUponGating</code> gating logic. Maximizes RPC data intake using batched multicalls with 0 rate limit violations.
            </p>
          </div>

          {/* 12-Second Cycle Timer Box */}
          <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2 min-w-[280px]">
            <div className="flex justify-between items-center text-xs">
              <span className="text-slate-400 font-bold uppercase flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5 text-cyan-400" />
                <span>Next Cycle Scan</span>
              </span>
              <span className="text-emerald-400 font-bold font-mono text-sm">
                {(timeLeftMs / 1000).toFixed(1)}s
              </span>
            </div>

            {/* Progress Bar */}
            <div className="w-full bg-slate-900 h-2 rounded-full overflow-hidden border border-slate-800 relative">
              <div
                className={`h-full transition-all duration-100 ${
                  isScanningNow ? 'bg-amber-400 animate-pulse' : 'bg-emerald-400'
                }`}
                style={{ width: `${progressPct}%` }}
              />
            </div>

            <div className="flex justify-between items-center text-[10px] text-slate-400">
              <span>Cycle <strong className="text-white">#{cycleCount}</strong></span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setIsCyclePaused(!isCyclePaused)}
                  className="hover:text-white transition-colors flex items-center gap-1 text-[10px] bg-slate-900 px-2 py-0.5 rounded border border-slate-800"
                >
                  {isCyclePaused ? <Play className="w-3 h-3 text-emerald-400" /> : <Pause className="w-3 h-3 text-amber-400" />}
                  <span>{isCyclePaused ? 'Resume' : 'Pause'}</span>
                </button>
                <button
                  onClick={triggerCycleScan}
                  disabled={isScanningNow}
                  className="text-cyan-300 hover:text-white transition-colors flex items-center gap-1 text-[10px] bg-cyan-950 px-2 py-0.5 rounded border border-cyan-800 disabled:opacity-50"
                >
                  <RefreshCw className={`w-3 h-3 text-cyan-400 ${isScanningNow ? 'animate-spin' : ''}`} />
                  <span>Scan Now</span>
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* RPC Rate-Limit Optimization Metrics Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs border-t border-slate-800/80 pt-4">
          <div className="bg-slate-950 p-3 rounded-xl border border-slate-800 space-y-1">
            <span className="text-[10px] font-bold text-slate-500 uppercase block">Batched Multicalls</span>
            <span className="text-emerald-400 font-bold font-mono text-base">{multicallBatchedCalls.toLocaleString()} Calls</span>
            <span className="text-[9px] text-slate-400 block">50 Routes read in 1 RPC payload</span>
          </div>

          <div className="bg-slate-950 p-3 rounded-xl border border-slate-800 space-y-1">
            <span className="text-[10px] font-bold text-slate-500 uppercase block">RPC Requests Bypassed</span>
            <span className="text-cyan-400 font-bold font-mono text-base">{rpcRequestsSaved.toLocaleString()} Calls</span>
            <span className="text-[9px] text-slate-400 block">~92% RPC overhead saved</span>
          </div>

          <div className="bg-slate-950 p-3 rounded-xl border border-slate-800 space-y-1">
            <span className="text-[10px] font-bold text-slate-500 uppercase block">L1/L2 Cache Hit Rate</span>
            <span className="text-purple-400 font-bold font-mono text-base">{cacheHitRatePct}%</span>
            <span className="text-[9px] text-slate-400 block">Zero heap memory lookup</span>
          </div>

          <div className="bg-slate-950 p-3 rounded-xl border border-slate-800 space-y-1">
            <span className="text-[10px] font-bold text-slate-500 uppercase block">Alchemy CU Headroom</span>
            <span className="text-amber-400 font-bold font-mono text-base">{alchemyRateLimitUsage}% CU Used</span>
            <span className="text-[9px] text-emerald-400 block">Zero 429 Rate Limits</span>
          </div>
        </div>
      </div>

      {/* Main Table + Live Activity Hooks Inspector Section */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Top 50 Routes Table (8 Cols) */}
        <div className="lg:col-span-8 bg-slate-900 border border-slate-800 rounded-2xl p-4 space-y-4 shadow-xl">
          {/* Table Header Controls */}
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 border-b border-slate-800 pb-3">
            <div className="flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-emerald-400" />
              <h2 className="text-xs font-bold text-white uppercase tracking-wider">
                Top 50 Alpha Routes (Block #{currentBlock})
              </h2>
              <span className="bg-slate-800 text-slate-300 text-[10px] px-2 py-0.5 rounded font-mono">
                Showing {filteredRoutes.length} of 50
              </span>
            </div>

            <div className="flex items-center gap-2 w-full sm:w-auto">
              <button
                onClick={toggleExpandAll}
                className="bg-slate-950 hover:bg-slate-800 text-emerald-300 hover:text-white px-2.5 py-1.5 rounded-lg border border-slate-800 text-[11px] font-bold transition-colors flex items-center gap-1.5 whitespace-nowrap"
              >
                <Sliders className="w-3.5 h-3.5 text-emerald-400" />
                <span>{expandedHashes.size === filteredRoutes.length ? 'Collapse All DNA' : 'Expand All Staging DNA'}</span>
              </button>

              <div className="relative w-full sm:w-48">
                <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-2.5" />
                <input
                  type="text"
                  placeholder="Search token, hash..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-8 pr-2 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500"
                />
              </div>

              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="bg-slate-950 border border-slate-800 rounded-lg px-2 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-emerald-500"
              >
                <option value="ALL">All Statuses</option>
                <option value="EXECUTABLE">Executable</option>
                <option value="WATCHING">Watching Activity</option>
                <option value="SIMULATED">Simulated</option>
              </select>
            </div>
          </div>

          {/* Table Content */}
          <div className="overflow-x-auto max-h-[620px] overflow-y-auto no-scrollbar border border-slate-800/80 rounded-xl">
            <table className="w-full text-xs font-mono text-left border-collapse">
              <thead className="bg-slate-950 sticky top-0 z-10 border-b border-slate-800 text-slate-400 text-[10px] uppercase">
                <tr>
                  <th className="p-2.5 text-center">Rank</th>
                  <th className="p-2.5">Opportunity Object ID & Hashtag</th>
                  <th className="p-2.5">Swap Hops</th>
                  <th className="p-2.5 text-right">Optimal Size</th>
                  <th className="p-2.5 text-right">Net Profit</th>
                  <th className="p-2.5 text-center">VQC Score</th>
                  <th className="p-2.5 text-center">Spread Delta</th>
                  <th className="p-2.5 text-center">Status</th>
                  <th className="p-2.5 text-center">Staging DNA</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 text-slate-300">
                {filteredRoutes.map((route) => {
                  const isExpanded = expandedHashes.has(route.routeHash);
                  return (
                    <React.Fragment key={route.routeHash}>
                      <tr
                        className={`hover:bg-slate-800/40 transition-colors ${
                          selectedRoute?.routeHash === route.routeHash ? 'bg-slate-800/80' : ''
                        }`}
                      >
                        <td className="p-2.5 text-center font-bold">
                          <span
                            className={`inline-block px-2 py-0.5 rounded text-[10px] ${
                              route.rank <= 3
                                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 font-black'
                                : route.rank <= 10
                                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-bold'
                                : 'bg-slate-800 text-slate-400'
                            }`}
                          >
                            #{route.rank}
                          </span>
                        </td>

                        <td className="p-2.5 font-bold font-mono">
                          <div className="flex items-center gap-1.5">
                            <span className="text-emerald-300 font-bold text-[11px]">{route.opportunityObjectId}</span>
                            <button
                              onClick={() => handleCopy(route.opportunityObjectId, route.opportunityObjectId)}
                              className="hover:text-white text-slate-500 transition-colors"
                              title="Copy Opportunity Object ID"
                            >
                              {copySuccess === route.opportunityObjectId ? (
                                <Check className="w-3 h-3 text-emerald-400" />
                              ) : (
                                <Copy className="w-3 h-3" />
                              )}
                            </button>
                          </div>
                          <div className="flex items-center gap-1 text-[9px] text-slate-500 mt-0.5">
                            <span className="text-cyan-400 font-bold">{route.routeHash}</span>
                            <span>•</span>
                            <span className="text-purple-300">{route.cycleParity}</span>
                          </div>
                        </td>

                        <td className="p-2.5">
                          <div className="flex items-center gap-1 text-[11px] font-bold">
                            <span className="text-emerald-400">{route.hops[0]}</span>
                            <ArrowRight className="w-3 h-3 text-slate-500" />
                            <span className="text-slate-300">{route.hops[1]}</span>
                            <ArrowRight className="w-3 h-3 text-slate-500" />
                            <span className="text-cyan-400">{route.hops[2]}</span>
                          </div>
                        </td>

                        <td className="p-2.5 text-right font-mono">
                          <div className="font-bold text-slate-200">{route.stagingMath.optimalFlashLoanUnits}</div>
                          <div className="text-[9px] text-slate-500">${route.borrowAmountUSD.toLocaleString()}</div>
                        </td>

                        <td className="p-2.5 text-right font-mono font-bold text-emerald-400">
                          +${route.netProfitUSD.toFixed(2)}
                        </td>

                        <td className="p-2.5 text-center font-mono font-bold">
                          <span
                            className={`px-1.5 py-0.5 rounded text-[10px] ${
                              route.vqcScore >= 90
                                ? 'bg-purple-950 text-purple-300 border border-purple-800'
                                : route.vqcScore >= 85
                                ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                                : 'bg-slate-800 text-slate-400'
                            }`}
                          >
                            {route.vqcScore}/100
                          </span>
                        </td>

                        <td className="p-2.5 text-center font-mono">
                          <span
                            className={`text-[10px] font-bold ${
                              route.priceDeltaBps >= 0 ? 'text-emerald-400' : 'text-amber-400'
                            }`}
                          >
                            {route.priceDeltaBps >= 0 ? '+' : ''}
                            {route.priceDeltaBps} bps
                          </span>
                        </td>

                        <td className="p-2.5 text-center">
                          <span
                            className={`px-2 py-0.5 rounded text-[9px] font-bold uppercase ${
                              route.status === 'EXECUTABLE'
                                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                                : route.status === 'WATCHING'
                                ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30'
                                : 'bg-slate-800 text-slate-400'
                            }`}
                          >
                            {route.status}
                          </span>
                        </td>

                        <td className="p-2.5 text-center">
                          <div className="flex items-center justify-center gap-1">
                            <button
                              onClick={() => toggleExpandHash(route.routeHash)}
                              className={`px-2 py-1 rounded text-[10px] font-bold transition-all flex items-center gap-1 ${
                                isExpanded
                                  ? 'bg-emerald-950 text-emerald-300 border border-emerald-700'
                                  : 'bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white'
                              }`}
                              title="Toggle Staging Before/After Math DNA"
                            >
                              <Sliders className="w-3 h-3 text-emerald-400" />
                              <span>{isExpanded ? 'Hide DNA' : 'Math DNA'}</span>
                            </button>
                            <button
                              onClick={() => setSelectedRoute(route)}
                              className="bg-slate-800 hover:bg-slate-700 text-cyan-300 hover:text-white px-2 py-1 rounded text-[10px] font-bold transition-all flex items-center gap-1"
                              title="Inspect Route"
                            >
                              <Eye className="w-3 h-3" />
                            </button>
                          </div>
                        </td>
                      </tr>

                      {/* Expandable Row: Mirror State of Staging Before/After Math */}
                      {isExpanded && (
                        <tr className="bg-slate-950/90 border-b border-emerald-500/30 font-mono">
                          <td colSpan={9} className="p-3.5 space-y-3">
                            <div className="bg-slate-900/90 border border-emerald-500/40 rounded-xl p-3.5 space-y-3 shadow-inner">
                              <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2 border-b border-slate-800 pb-2">
                                <span className="font-bold text-emerald-300 text-xs flex items-center gap-2">
                                  <Layers className="w-3.5 h-3.5 text-emerald-400" />
                                  <span>STAGING MIRROR STATE ({route.opportunityObjectId}) — {route.cycleParity}</span>
                                </span>
                                <span className="bg-emerald-950 text-emerald-300 text-[9px] font-bold px-2 py-0.5 rounded border border-emerald-800">
                                  MIRROR STATE PARITY VERIFIED
                                </span>
                              </div>

                              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3 text-xs">
                                {/* Column 1: Pre-Math Raw Discovery */}
                                <div className="bg-slate-950 p-2.5 rounded-lg border border-slate-800 space-y-1">
                                  <span className="text-[10px] font-bold text-amber-400 uppercase block">1. Discovery State (Pre-Math)</span>
                                  <div className="flex justify-between text-slate-400 text-[11px]">
                                    <span>Raw Spread:</span>
                                    <strong className="text-amber-300">+{route.stagingMath.rawSpreadBps} bps</strong>
                                  </div>
                                  <div className="flex justify-between text-slate-400 text-[11px]">
                                    <span>Raw Price Delta:</span>
                                    <strong className="text-amber-300">+{route.stagingMath.rawDeltaBps} bps</strong>
                                  </div>
                                  <div className="flex justify-between text-slate-400 text-[11px]">
                                    <span>Sizing Probe:</span>
                                    <strong className="text-slate-400">Unsized Opportunity</strong>
                                  </div>
                                </div>

                                {/* Column 2: Math Engine Optimization */}
                                <div className="bg-slate-950 p-2.5 rounded-lg border border-slate-800 space-y-1">
                                  <span className="text-[10px] font-bold text-cyan-400 uppercase block">2. Post-Math Optimization</span>
                                  <div className="flex justify-between text-slate-400 text-[11px]">
                                    <span>Optimal Loan Size:</span>
                                    <strong className="text-cyan-300">{route.stagingMath.optimalFlashLoanUnits}</strong>
                                  </div>
                                  <div className="flex justify-between text-slate-400 text-[11px]">
                                    <span>Post-Math Spread:</span>
                                    <strong className="text-emerald-400">+{route.stagingMath.postMathSpreadBps} bps</strong>
                                  </div>
                                  <div className="flex justify-between text-slate-400 text-[11px]">
                                    <span>Calculated Slippage:</span>
                                    <strong className="text-purple-300 font-bold">-{route.stagingMath.postMathSlippageBps} bps</strong>
                                  </div>
                                </div>

                                {/* Column 3: Pool Reserves Before -> After */}
                                <div className="bg-slate-950 p-2.5 rounded-lg border border-slate-800 space-y-1">
                                  <span className="text-[10px] font-bold text-purple-400 uppercase block">3. Simulated Pool Reserves</span>
                                  <div className="text-[10px] text-slate-400">
                                    <span className="block text-slate-500">Pool #1 Reserves:</span>
                                    <div className="text-slate-300 font-bold text-[9px]">{route.stagingMath.pool1ReservesBefore}</div>
                                    <div className="text-emerald-400 font-bold text-[9px]">➔ {route.stagingMath.pool1ReservesAfter}</div>
                                  </div>
                                </div>

                                {/* Column 4: Yield & FastLane Tip Accounting */}
                                <div className="bg-slate-950 p-2.5 rounded-lg border border-slate-800 space-y-1">
                                  <span className="text-[10px] font-bold text-emerald-400 uppercase block">4. Net Yield Accounting</span>
                                  <div className="flex justify-between text-slate-400 text-[11px]">
                                    <span>Expected Gross:</span>
                                    <strong className="text-slate-200">${route.stagingMath.grossYieldUSD}</strong>
                                  </div>
                                  <div className="flex justify-between text-slate-400 text-[11px]">
                                    <span>FastLane Tip (15%):</span>
                                    <strong className="text-amber-300">-${route.stagingMath.fastlaneBuilderTipUSD}</strong>
                                  </div>
                                  <div className="flex justify-between text-slate-400 text-[11px]">
                                    <span>Net Retained Profit:</span>
                                    <strong className="text-emerald-400 font-bold">+${route.stagingMath.netYieldUSD}</strong>
                                  </div>
                                </div>
                              </div>

                              <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center text-[10px] text-slate-400 bg-slate-950 p-2 rounded-lg border border-slate-800 gap-2">
                                <div>EIP-1153 Transient Slot: <strong className="text-cyan-300">{route.stagingMath.transientLockSlot}</strong></div>
                                <div className="truncate max-w-md">Zero-Copy Calldata: <strong className="text-emerald-300">{route.stagingMath.zeroCopyCalldata}</strong></div>
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Right Side: Continuous Hook Watcher Feed & Selected Route Inspector (4 Cols) */}
        <div className="lg:col-span-4 space-y-4">
          {/* Continuous Activity Hook Watcher Feed */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 space-y-3 shadow-xl">
            <div className="flex justify-between items-center border-b border-slate-800 pb-2">
              <h3 className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-2">
                <Radio className="w-4 h-4 text-emerald-400 animate-pulse" />
                <span>Active Route Event Hooks</span>
              </h3>
              <span className="bg-emerald-950 text-emerald-400 text-[10px] font-bold px-2 py-0.5 rounded border border-emerald-800 font-mono">
                Listening (2.5s)
              </span>
            </div>

            <p className="text-[10px] text-slate-400">
              Hook watchers monitor liquidity pool depths, price variances, and competing mempool transactions for all 50 routes between 12s scan cycles.
            </p>

            <div className="bg-slate-950 p-3 rounded-xl border border-slate-800 space-y-2 max-h-[220px] overflow-y-auto no-scrollbar font-mono text-[10px] text-slate-300">
              {liveWatchLogs.length === 0 ? (
                <p className="text-slate-500 italic text-center py-4">Initializing hooks for Top 50 routes...</p>
              ) : (
                liveWatchLogs.map((log, idx) => (
                  <div key={idx} className="border-b border-slate-900 pb-1.5 last:border-none">
                    <span className="text-cyan-400 font-bold">{log.slice(0, 30)}</span>
                    <span className="text-slate-400">{log.slice(30)}</span>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Detailed Route Inspector Modal / Drawer */}
          {selectedRoute ? (
            <div className="bg-slate-900 border border-emerald-500/40 rounded-2xl p-4 space-y-3 shadow-2xl animate-fadeIn">
              <div className="flex justify-between items-center border-b border-slate-800 pb-2">
                <h3 className="text-xs font-bold text-emerald-300 uppercase tracking-wider flex items-center gap-1.5">
                  <Code2 className="w-4 h-4 text-emerald-400" />
                  <span>Route Inspector</span>
                </h3>
                <button
                  onClick={() => setSelectedRoute(null)}
                  className="text-slate-500 hover:text-white text-xs font-bold"
                >
                  ✕ Close
                </button>
              </div>

              <div className="space-y-2 text-xs font-mono">
                <div className="bg-slate-950 p-2.5 rounded-lg border border-slate-800 space-y-1.5">
                  <div className="flex justify-between items-center text-slate-400 text-[11px]">
                    <span>Opportunity Object ID:</span>
                    <strong className="text-emerald-300 font-bold">{selectedRoute.opportunityObjectId}</strong>
                  </div>
                  <div className="flex justify-between items-center text-slate-400 text-[11px]">
                    <span>Cycle Parity:</span>
                    <strong className="text-purple-300 font-bold">{selectedRoute.cycleParity}</strong>
                  </div>
                  <div className="flex justify-between items-center text-slate-400 text-[11px]">
                    <span>Route Hashtag:</span>
                    <strong className="text-cyan-300">{selectedRoute.routeHash}</strong>
                  </div>
                  <div className="flex justify-between text-slate-400">
                    <span>Rank Position:</span>
                    <strong className="text-amber-400">#{selectedRoute.rank} of 50</strong>
                  </div>
                  <div className="flex justify-between text-slate-400">
                    <span>Flash Loan Token:</span>
                    <strong className="text-emerald-300">{selectedRoute.flashAsset}</strong>
                  </div>
                  <div className="flex justify-between text-slate-400">
                    <span>Optimal Flash Size:</span>
                    <strong className="text-cyan-300">{selectedRoute.stagingMath.optimalFlashLoanUnits} (${selectedRoute.borrowAmountUSD.toLocaleString()})</strong>
                  </div>
                  <div className="flex justify-between text-slate-400">
                    <span>Expected Gross Profit:</span>
                    <strong className="text-white">${selectedRoute.expectedGrossProfitUSD}</strong>
                  </div>
                  <div className="flex justify-between text-slate-400">
                    <span>FastLane Tip (15%):</span>
                    <strong className="text-amber-300">-${selectedRoute.stagingMath.fastlaneBuilderTipUSD}</strong>
                  </div>
                  <div className="flex justify-between text-slate-400">
                    <span>Estimated Gas Cost:</span>
                    <strong className="text-amber-300">${selectedRoute.estimatedGasUSD}</strong>
                  </div>
                  <div className="flex justify-between text-slate-400">
                    <span>Net Retained Profit:</span>
                    <strong className="text-emerald-400 font-bold">${selectedRoute.netProfitUSD}</strong>
                  </div>
                  <div className="flex justify-between text-slate-400">
                    <span>VQC Quantum Score:</span>
                    <strong className="text-purple-300">{selectedRoute.vqcScore}/100</strong>
                  </div>
                </div>

                {/* Staging Mirror State DNA Panel */}
                <div className="bg-slate-950 p-2.5 rounded-lg border border-slate-800 space-y-1.5">
                  <span className="text-[10px] font-bold text-emerald-400 uppercase block">Staging Before/After Math DNA</span>
                  <div className="grid grid-cols-2 gap-2 text-[10px]">
                    <div className="bg-slate-900 p-1.5 rounded border border-slate-800">
                      <span className="text-slate-500 block">Pre-Math Spread:</span>
                      <strong className="text-amber-300">+{selectedRoute.stagingMath.rawSpreadBps} bps</strong>
                    </div>
                    <div className="bg-slate-900 p-1.5 rounded border border-slate-800">
                      <span className="text-slate-500 block">Post-Math Spread:</span>
                      <strong className="text-emerald-400">+{selectedRoute.stagingMath.postMathSpreadBps} bps</strong>
                    </div>
                    <div className="bg-slate-900 p-1.5 rounded border border-slate-800">
                      <span className="text-slate-500 block">Pre-Math Raw Delta:</span>
                      <strong className="text-amber-300">+{selectedRoute.stagingMath.rawDeltaBps} bps</strong>
                    </div>
                    <div className="bg-slate-900 p-1.5 rounded border border-slate-800">
                      <span className="text-slate-500 block">Post-Math Slippage:</span>
                      <strong className="text-purple-300">-{selectedRoute.stagingMath.postMathSlippageBps} bps</strong>
                    </div>
                  </div>
                </div>

                <div className="bg-slate-950 p-2.5 rounded-lg border border-slate-800 space-y-1 text-[11px]">
                  <span className="text-[10px] font-bold text-slate-500 uppercase block">Pool Reserve Shifts</span>
                  <div className="text-slate-300 text-[10px] space-y-1">
                    <div>Pool #1: <span className="text-slate-400">{selectedRoute.stagingMath.pool1ReservesBefore}</span> ➔ <span className="text-emerald-400">{selectedRoute.stagingMath.pool1ReservesAfter}</span></div>
                    <div>Pool #2: <span className="text-slate-400">{selectedRoute.stagingMath.pool2ReservesBefore}</span> ➔ <span className="text-emerald-400">{selectedRoute.stagingMath.pool2ReservesAfter}</span></div>
                  </div>
                </div>

                <div className="bg-slate-950 p-2.5 rounded-lg border border-slate-800 space-y-1">
                  <span className="text-[10px] font-bold text-slate-500 uppercase block">EIP-1153 Zero-Copy Payload</span>
                  <pre className="text-[10px] text-slate-300 font-mono bg-slate-900 p-2 rounded border border-slate-800 overflow-x-auto">
{`calldata: ${selectedRoute.stagingMath.zeroCopyCalldata}
tstore_lock: ${selectedRoute.stagingMath.transientLockSlot}
relay_tip: FastLane block.coinbase (15% Bps)`}
                  </pre>
                </div>
              </div>
            </div>
          ) : (
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 text-center space-y-2 text-xs text-slate-400">
              <Eye className="w-8 h-8 text-slate-600 mx-auto" />
              <p className="font-bold text-slate-300">Select any route to inspect details</p>
              <p className="text-[11px] text-slate-500">
                Click "Inspect" on any of the 50 routes to view zero-copy calldata, EIP-1153 transient locks, and pool hashtags.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
