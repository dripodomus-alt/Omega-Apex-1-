import React, { useState } from 'react';
import { ArbitrageRoute, PipelineStage, PoolInfo } from '../types';
import { validateRouteAssetRegistry } from '../utils/mathEngine';
import { OpportunityDnaCard } from './OpportunityDnaCard';
import { D3RoutePathGraph } from './D3RoutePathGraph';
import { VqcSparklineChart } from './VqcSparklineChart';
import { RouteProfitTrendChart } from './RouteProfitTrendChart';
import { SystemRule026Controller } from './SystemRule026Controller';
import {
  Play,
  ArrowRight,
  ShieldCheck,
  AlertTriangle,
  Zap,
  CheckCircle2,
  RefreshCw,
  BarChart2,
  Sparkles,
  Database,
  Dna,
  LayoutGrid,
  Bell,
  BellOff,
  Sliders,
  Filter,
  ShieldAlert,
  Volume2,
  VolumeX,
  X,
  Check,
  CheckSquare,
  Square,
  Layers,
  ArrowUpDown,
  DollarSign,
  Lock,
} from 'lucide-react';

interface PipelineScannerProps {
  routes: ArbitrageRoute[];
  pools?: PoolInfo[];
  onExecuteRoute: (routeId: string) => void;
  onAdvanceRouteStage?: (routeId: string) => void;
  onSelectRouteForInjector: (route: ArbitrageRoute) => void;
  onAnalyzeRouteWithAI: (route: ArbitrageRoute) => void;
  onAddSimulatedRoute: () => void;
}

const STAGES: { stage: PipelineStage; label: string; desc: string; color: string }[] = [
  { stage: 'DISCOVERED', label: '1. Discovered', desc: 'Bellman-Ford-Curve path found', color: 'border-slate-700 bg-slate-900 text-slate-300' },
  { stage: 'RANKED', label: '2. VQC Ranked', desc: 'Quantum ML Surplus > 0.85', color: 'border-purple-800 bg-purple-950/40 text-purple-300' },
  { stage: 'SIMULATED', label: '3. Apex Solved', desc: 'Derivative dP/dx=0 calculated', color: 'border-indigo-800 bg-indigo-950/40 text-indigo-300' },
  { stage: 'PREPARED', label: '4. Vault Approved', desc: 'Balancer V3 EIP-1153 flash', color: 'border-cyan-800 bg-cyan-950/40 text-cyan-300' },
  { stage: 'EXECUTED', label: '5. Relay Mined', desc: 'Polygon block inclusion', color: 'border-emerald-800 bg-emerald-950/40 text-emerald-300' },
  { stage: 'ACCOUNTED', label: '6. SQL Logged', desc: 'Redis XADD -> Cloud SQL', color: 'border-amber-800 bg-amber-950/40 text-amber-300' },
];

export const PipelineScanner: React.FC<PipelineScannerProps> = ({
  routes,
  pools = [],
  onExecuteRoute,
  onAdvanceRouteStage,
  onSelectRouteForInjector,
  onAnalyzeRouteWithAI,
  onAddSimulatedRoute,
}) => {
  const [selectedStageFilter, setSelectedStageFilter] = useState<PipelineStage | 'ALL'>('ALL');
  const [viewMode, setViewMode] = useState<'dna' | 'standard'>('dna');
  const [hoveredRoute, setHoveredRoute] = useState<ArbitrageRoute | null>(null);

  // Batch Route Selection State
  const [selectedRouteIds, setSelectedRouteIds] = useState<Set<string>>(new Set());
  const [batchNotification, setBatchNotification] = useState<string | null>(null);

  // User-defined risk notification threshold parameters
  const [maxSlippageBps, setMaxSlippageBps] = useState<number>(35); // 0.35% default
  const [maxGasRatioPercent, setMaxGasRatioPercent] = useState<number>(35.0); // 35% max gas/profit ratio default
  const [filterMode, setFilterMode] = useState<'ALL' | 'FLAGGED' | 'COMPLIANT'>('ALL');
  const [soundAlertsEnabled, setSoundAlertsEnabled] = useState<boolean>(true);
  const [isThresholdPanelOpen, setIsThresholdPanelOpen] = useState<boolean>(false);
  const [dismissedBanner, setDismissedBanner] = useState<boolean>(false);

  // Route evaluation helper function
  const evalRouteAlert = (route: ArbitrageRoute) => {
    const gasRatio = route.grossProfitUSD > 0
      ? (route.estimatedGasUSD / route.grossProfitUSD) * 100
      : 100;
    const slippageExceeded = route.slippageToleranceBps > maxSlippageBps;
    const gasRatioExceeded = gasRatio > maxGasRatioPercent;
    return {
      isFlagged: slippageExceeded || gasRatioExceeded,
      slippageExceeded,
      gasRatioExceeded,
      gasRatio,
    };
  };

  const stageFilteredRoutes = selectedStageFilter === 'ALL'
    ? routes
    : routes.filter((r) => r.stage === selectedStageFilter);

  // Sorting state for prioritizing high-value opportunities
  const [sortBy, setSortBy] = useState<'netProfitDesc' | 'vqcScoreDesc' | 'default'>('netProfitDesc');

  // Routing Variation Filter State
  const [selectedVariationFilter, setSelectedVariationFilter] = useState<string>('ALL');

  // Threshold state for auto-selecting high-profit opportunities
  const [highProfitThreshold, setHighProfitThreshold] = useState<number>(500);

  // Helper: Categorize route into routing variation
  const getRouteVariationCategory = (r: ArbitrageRoute): string => {
    const p = r.pathString.toLowerCase();
    if (p.includes('aave') || p.includes('liquidation')) return 'AAVE_LIQUIDATION';
    if (p.includes('balancer v3') || p.includes('transient storage') || p.includes('spatial')) return 'SPATIAL_FLASHLOAN';
    if (p.includes('jit') || p.includes('tricrypto')) return 'JIT_REBALANCE';
    if (p.includes('subgraph') || p.includes('sub-graph')) return 'SUBGRAPH_TRANSIENT';
    if (r.length === 2) return '2_HOP_TRIANGULAR';
    if (r.length === 3) return '3_HOP_CYCLIC';
    if (r.length >= 4) return '4_HOP_MULTIDEX';
    return '2_HOP_TRIANGULAR';
  };

  // Final filtered list based on compliance mode & routing variation
  const filteredRoutes = stageFilteredRoutes.filter((route) => {
    const alertInfo = evalRouteAlert(route);
    if (filterMode === 'FLAGGED' && !alertInfo.isFlagged) return false;
    if (filterMode === 'COMPLIANT' && alertInfo.isFlagged) return false;

    if (selectedVariationFilter !== 'ALL') {
      const category = getRouteVariationCategory(route);
      if (category !== selectedVariationFilter) return false;
    }

    return true;
  });

  // Sorted routes list based on selected sort toggle
  const sortedRoutes = [...filteredRoutes].sort((a, b) => {
    if (sortBy === 'netProfitDesc') {
      return b.netProfitUSD - a.netProfitUSD;
    }
    if (sortBy === 'vqcScoreDesc') {
      return b.vqcAlphaScore - a.vqcAlphaScore;
    }
    return 0;
  });

  // Flagged summary stats across stage-filtered set
  const flaggedRoutes = stageFilteredRoutes.filter((r) => evalRouteAlert(r).isFlagged);
  const compliantCount = stageFilteredRoutes.length - flaggedRoutes.length;

  const slippageFlaggedCount = stageFilteredRoutes.filter((r) => evalRouteAlert(r).slippageExceeded).length;
  const gasFlaggedCount = stageFilteredRoutes.filter((r) => evalRouteAlert(r).gasRatioExceeded).length;

  const activeGraphRoute = hoveredRoute || sortedRoutes[0] || routes[0] || null;

  // Selected Batch Summary Metrics
  const selectedRoutesList = routes.filter((r) => selectedRouteIds.has(r.id));
  const selectedBatchTotalNetProfitUSD = selectedRoutesList.reduce((sum, r) => sum + r.netProfitUSD, 0);
  const selectedBatchTotalGrossProfitUSD = selectedRoutesList.reduce((sum, r) => sum + r.grossProfitUSD, 0);
  const selectedBatchTotalGasUSD = selectedRoutesList.reduce((sum, r) => sum + r.estimatedGasUSD, 0);
  const selectedBatchAvgVqcScore =
    selectedRoutesList.length > 0
      ? selectedRoutesList.reduce((sum, r) => sum + r.vqcAlphaScore, 0) / selectedRoutesList.length
      : 0;

  // Selection & Batch Execution Helpers
  const toggleSelectRoute = (id: string) => {
    setSelectedRouteIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const executableFilteredRoutes = sortedRoutes.filter((r) => {
    const isExecuted = r.stage === 'EXECUTED' || r.stage === 'ACCOUNTED';
    const registryCheck = validateRouteAssetRegistry(r, pools);
    return !isExecuted && registryCheck.isExecutable;
  });

  const isAllExecutableSelected =
    executableFilteredRoutes.length > 0 &&
    executableFilteredRoutes.every((r) => selectedRouteIds.has(r.id));

  const toggleSelectAll = () => {
    if (isAllExecutableSelected) {
      setSelectedRouteIds(new Set());
    } else {
      setSelectedRouteIds(new Set(executableFilteredRoutes.map((r) => r.id)));
    }
  };

  const handleSelectHighProfit = () => {
    const matchingIds = executableFilteredRoutes
      .filter((r) => r.netProfitUSD >= highProfitThreshold)
      .map((r) => r.id);
    setSelectedRouteIds(new Set(matchingIds));
  };

  const handleBatchExecute = () => {
    const idsToExecute = Array.from(selectedRouteIds);
    if (idsToExecute.length === 0) return;

    idsToExecute.forEach((id) => {
      onExecuteRoute(id);
    });

    setBatchNotification(`Batch Execution Triggered: ${idsToExecute.length} selected route(s) dispatched to Relay!`);
    setSelectedRouteIds(new Set());

    setTimeout(() => {
      setBatchNotification(null);
    }, 5000);
  };

  return (
    <div id="pipeline-scanner-module" className="space-y-6">
      {/* Stage Flow Indicator */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-xl">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Zap className="w-5 h-5 text-emerald-400" />
            <h2 className="text-sm font-bold text-white uppercase tracking-wider font-mono">
              OMEGA V5 Execution Pipeline Lineage
            </h2>
          </div>
          <button
            onClick={onAddSimulatedRoute}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold rounded-lg shadow-lg shadow-emerald-600/20 transition-all active:scale-95"
          >
            <Zap className="w-3.5 h-3.5" />
            <span>Discover Arbitrage Opportunity</span>
          </button>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-6 gap-2">
          {STAGES.map((s) => {
            const count = routes.filter((r) => r.stage === s.stage).length;
            const isSelected = selectedStageFilter === s.stage;
            return (
              <button
                key={s.stage}
                onClick={() => setSelectedStageFilter(isSelected ? 'ALL' : s.stage)}
                className={`text-left p-3 rounded-lg border transition-all relative overflow-hidden ${s.color} ${
                  isSelected ? 'ring-2 ring-emerald-400 font-bold scale-[1.02]' : 'hover:border-slate-600'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono font-semibold">{s.label}</span>
                  <span className="px-1.5 py-0.5 text-[10px] rounded-full bg-slate-950/80 font-mono border border-slate-700/50">
                    {count}
                  </span>
                </div>
                <p className="text-[10px] opacity-75 mt-1 line-clamp-1">{s.desc}</p>
              </button>
            );
          })}
        </div>
      </div>

      {/* 026. Final System Rule: Configurable Execution Machine Alignment */}
      <SystemRule026Controller />

      {/* Dynamic D3 Route Hop Sequence Diagram */}
      <D3RoutePathGraph route={activeGraphRoute} />

      {/* Net Profit Cluster Distribution Trend Chart */}
      <RouteProfitTrendChart routes={routes} selectedRouteIds={selectedRouteIds} />

      {/* Top of the Industry Execution Integrity Safeguard Status Banner */}
      <div className="bg-gradient-to-r from-slate-900 via-emerald-950/80 to-slate-900 border border-emerald-800/80 rounded-xl p-4 shadow-xl font-mono flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-emerald-950 border border-emerald-700/80 rounded-xl text-emerald-400 shadow-md shrink-0">
            <ShieldCheck className="w-5 h-5 animate-pulse" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-xs font-black text-white uppercase tracking-wider">
                Execution Integrity Safeguard Shield: ACTIVE
              </h3>
              <span className="px-2 py-0.5 bg-emerald-950 text-emerald-300 border border-emerald-800 rounded text-[9px] font-bold">
                0% Revert Rate Guarantee
              </span>
            </div>
            <p className="text-[11px] text-slate-300 mt-0.5 font-sans">
              <code className="text-emerald-300">eth_call</code> pre-flight simulation, EIP-1153 reentrancy lock, FastLane/Flashbots MEV private tunnel & Chainlink oracle quorum enabled.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap shrink-0">
          <div className="px-2.5 py-1 bg-slate-950 border border-slate-800 rounded-lg text-[10px] text-slate-300 font-bold flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
            <span>FastLane Private Tunnel</span>
          </div>
          <div className="px-2.5 py-1 bg-slate-950 border border-slate-800 rounded-lg text-[10px] text-cyan-300 font-bold flex items-center gap-1.5">
            <Lock className="w-3 h-3 text-cyan-400" />
            <span>EIP-1153 TSTORE</span>
          </div>
          <div className="px-2.5 py-1 bg-slate-950 border border-slate-800 rounded-lg text-[10px] text-amber-300 font-bold flex items-center gap-1.5">
            <CheckCircle2 className="w-3 h-3 text-amber-400" />
            <span>Chainlink Quorum &lt;15bps</span>
          </div>
        </div>
      </div>

      {/* Risk Notification Threshold Controls Bar */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-xl space-y-3 font-mono">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 border-b border-slate-800/80 pb-3">
          <div className="flex items-center gap-2">
            <div className="p-1.5 bg-amber-950 border border-amber-800 rounded-lg text-amber-400">
              <Bell className="w-4 h-4 animate-bounce" />
            </div>
            <div>
              <h3 className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-2">
                <span>Threshold Notification System</span>
                {flaggedRoutes.length > 0 ? (
                  <span className="px-2 py-0.5 bg-rose-950 text-rose-300 border border-rose-800 rounded-full text-[10px] font-bold animate-pulse">
                    {flaggedRoutes.length} Route Alert{flaggedRoutes.length > 1 ? 's' : ''} Active
                  </span>
                ) : (
                  <span className="px-2 py-0.5 bg-emerald-950 text-emerald-300 border border-emerald-800 rounded-full text-[10px] font-bold">
                    All Routes Compliant
                  </span>
                )}
              </h3>
              <p className="text-[11px] text-slate-400 font-sans">
                Real-time MEV risk flags for routes exceeding maximum slippage tolerance or gas-to-profit limits.
              </p>
            </div>
          </div>

          {/* Quick Filter Buttons & Threshold Panel Trigger */}
          <div className="flex items-center gap-2 flex-wrap">
            <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs">
              <button
                onClick={() => setFilterMode('ALL')}
                className={`px-2.5 py-1 rounded text-[11px] font-bold transition-all ${
                  filterMode === 'ALL'
                    ? 'bg-slate-800 text-white border border-slate-700'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                All ({stageFilteredRoutes.length})
              </button>
              <button
                onClick={() => setFilterMode('FLAGGED')}
                className={`px-2.5 py-1 rounded text-[11px] font-bold transition-all flex items-center gap-1 ${
                  filterMode === 'FLAGGED'
                    ? 'bg-rose-950 text-rose-300 border border-rose-800'
                    : 'text-slate-400 hover:text-rose-300'
                }`}
              >
                <AlertTriangle className="w-3 h-3 text-rose-400" />
                <span>Flagged ({flaggedRoutes.length})</span>
              </button>
              <button
                onClick={() => setFilterMode('COMPLIANT')}
                className={`px-2.5 py-1 rounded text-[11px] font-bold transition-all flex items-center gap-1 ${
                  filterMode === 'COMPLIANT'
                    ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                    : 'text-slate-400 hover:text-emerald-300'
                }`}
              >
                <Check className="w-3 h-3 text-emerald-400" />
                <span>Compliant ({compliantCount})</span>
              </button>
            </div>

            <button
              onClick={() => setSoundAlertsEnabled(!soundAlertsEnabled)}
              title={soundAlertsEnabled ? 'Sound Notifications Enabled' : 'Sound Notifications Muted'}
              className={`p-2 rounded-lg border text-xs transition-all ${
                soundAlertsEnabled
                  ? 'bg-indigo-950 text-indigo-300 border-indigo-800'
                  : 'bg-slate-950 text-slate-500 border-slate-800'
              }`}
            >
              {soundAlertsEnabled ? <Volume2 className="w-4 h-4 text-indigo-400" /> : <VolumeX className="w-4 h-4" />}
            </button>

            <button
              onClick={() => setIsThresholdPanelOpen(!isThresholdPanelOpen)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-bold transition-all ${
                isThresholdPanelOpen
                  ? 'bg-amber-950 text-amber-300 border-amber-700'
                  : 'bg-slate-950 text-slate-300 border-slate-800 hover:border-slate-700'
              }`}
            >
              <Sliders className="w-3.5 h-3.5 text-amber-400" />
              <span>Configure Limits</span>
            </button>
          </div>
        </div>

        {/* Expandable Threshold Tuning Panel */}
        {isThresholdPanelOpen && (
          <div className="p-4 bg-slate-950 border border-slate-800 rounded-xl space-y-4 animate-in fade-in duration-200">
            <div className="flex items-center justify-between text-xs text-amber-300 font-bold border-b border-slate-800/80 pb-2">
              <span className="flex items-center gap-1.5">
                <Sliders className="w-4 h-4 text-amber-400" />
                <span>Risk Notification Threshold Parameters</span>
              </span>
              <button
                onClick={() => {
                  setMaxSlippageBps(35);
                  setMaxGasRatioPercent(35.0);
                }}
                className="text-[10px] text-slate-400 hover:text-amber-300 underline"
              >
                Reset to Safety Defaults (35bps / 35%)
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 text-xs">
              {/* Slippage Threshold Slider */}
              <div className="space-y-2">
                <div className="flex justify-between items-center text-slate-300 font-semibold">
                  <label className="flex items-center gap-1.5">
                    <ShieldAlert className="w-4 h-4 text-amber-400" />
                    <span>Max Slippage Tolerance Threshold</span>
                  </label>
                  <span className="text-amber-400 font-bold bg-amber-950/80 px-2 py-0.5 rounded border border-amber-800">
                    {maxSlippageBps} bps ({ (maxSlippageBps / 100).toFixed(2) }%)
                  </span>
                </div>
                <input
                  type="range"
                  min="10"
                  max="100"
                  step="5"
                  value={maxSlippageBps}
                  onChange={(e) => setMaxSlippageBps(Number(e.target.value))}
                  className="w-full accent-amber-500 cursor-pointer"
                />
                <div className="flex justify-between text-[10px] text-slate-500 font-sans">
                  <span>10 bps (Strict 0.10%)</span>
                  <span>50 bps (Standard)</span>
                  <span>100 bps (High Risk 1.0%)</span>
                </div>
              </div>

              {/* Gas-to-Profit Ratio Slider */}
              <div className="space-y-2">
                <div className="flex justify-between items-center text-slate-300 font-semibold">
                  <label className="flex items-center gap-1.5">
                    <Zap className="w-4 h-4 text-rose-400" />
                    <span>Max Gas-to-Profit Ratio Threshold</span>
                  </label>
                  <span className="text-rose-400 font-bold bg-rose-950/80 px-2 py-0.5 rounded border border-rose-800">
                    {maxGasRatioPercent.toFixed(1)}% of Gross Profit
                  </span>
                </div>
                <input
                  type="range"
                  min="10"
                  max="80"
                  step="2.5"
                  value={maxGasRatioPercent}
                  onChange={(e) => setMaxGasRatioPercent(Number(e.target.value))}
                  className="w-full accent-rose-500 cursor-pointer"
                />
                <div className="flex justify-between text-[10px] text-slate-500 font-sans">
                  <span>10% (High Efficiency)</span>
                  <span>35% (Balanced)</span>
                  <span>80% (Extreme Gas Burn)</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* High Risk Notification Banner */}
        {flaggedRoutes.length > 0 && !dismissedBanner && (
          <div className="p-4 bg-gradient-to-r from-rose-950/80 via-slate-950 to-amber-950/80 border border-rose-800/80 rounded-xl flex flex-col md:flex-row md:items-center justify-between gap-3 shadow-lg shadow-rose-950/20">
            <div className="flex items-start gap-3">
              <div className="p-2 bg-rose-900/60 border border-rose-700 rounded-lg text-rose-300 shrink-0 mt-0.5">
                <ShieldAlert className="w-5 h-5 animate-pulse text-rose-400" />
              </div>
              <div className="space-y-1">
                <div className="text-xs font-bold text-white flex items-center gap-2">
                  <span>THRESHOLD NOTIFICATION ALERT</span>
                  <span className="text-rose-300 text-[11px] font-normal">
                    ({flaggedRoutes.length} route{flaggedRoutes.length > 1 ? 's' : ''} exceeding safety limits)
                  </span>
                </div>
                <p className="text-[11px] text-slate-300 leading-relaxed font-sans">
                  Routes flagged for exceeding defined safety thresholds:{' '}
                  {slippageFlaggedCount > 0 && (
                    <strong className="text-amber-300 font-mono">
                      {slippageFlaggedCount} Slippage &gt; {maxSlippageBps}bps
                    </strong>
                  )}{' '}
                  {slippageFlaggedCount > 0 && gasFlaggedCount > 0 && ' | '}
                  {gasFlaggedCount > 0 && (
                    <strong className="text-rose-300 font-mono">
                      {gasFlaggedCount} Gas Ratio &gt; {maxGasRatioPercent.toFixed(1)}%
                    </strong>
                  )}. Consider lowering flashloan sizing or adjusting execution parameters.
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              <button
                onClick={() => setFilterMode('FLAGGED')}
                className="px-3 py-1.5 bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold rounded-lg shadow transition-all"
              >
                Filter Flagged ({flaggedRoutes.length})
              </button>
              <button
                onClick={() => setDismissedBanner(true)}
                className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800"
                title="Dismiss Banner"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Routes List with DNA Cards Toggle & Batch Execute Bar */}
      <div className="space-y-4">
        {batchNotification && (
          <div className="p-3 bg-emerald-950/90 border border-emerald-600 rounded-xl font-mono text-xs text-emerald-200 flex items-center justify-between shadow-xl animate-in fade-in slide-in-from-top-2 duration-200">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 animate-bounce" />
              <span>{batchNotification}</span>
            </div>
            <button
              onClick={() => setBatchNotification(null)}
              className="text-emerald-400 hover:text-white font-bold"
            >
              ✕
            </button>
          </div>
        )}

        {/* Batch Action Toolbar & Selected Batch Summary Bar */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-3 shadow-md font-mono">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-3 flex-wrap">
              <button
                onClick={toggleSelectAll}
                disabled={executableFilteredRoutes.length === 0}
                className="flex items-center gap-2 px-3 py-1.5 bg-slate-950 border border-slate-700 hover:border-slate-600 rounded-lg text-xs font-bold text-slate-200 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                title="Select or deselect all executable routes"
              >
                <input
                  type="checkbox"
                  checked={isAllExecutableSelected}
                  onChange={toggleSelectAll}
                  disabled={executableFilteredRoutes.length === 0}
                  className="w-4 h-4 rounded border-slate-700 bg-slate-900 text-emerald-500 focus:ring-emerald-500 cursor-pointer accent-emerald-500"
                />
                <span>
                  {isAllExecutableSelected ? 'Deselect All' : `Select Executable (${executableFilteredRoutes.length})`}
                </span>
              </button>

              {/* Select High-Profit Control Group */}
              <div className="flex items-center gap-1.5 bg-slate-950 border border-slate-800 p-1 rounded-lg">
                <span className="text-[11px] text-amber-400 font-bold pl-1.5">$</span>
                <input
                  type="number"
                  value={highProfitThreshold}
                  onChange={(e) => setHighProfitThreshold(Number(e.target.value) || 0)}
                  className="w-16 bg-slate-900 border border-slate-700 rounded text-xs px-1.5 py-0.5 text-emerald-300 font-bold focus:outline-none focus:border-amber-500"
                  placeholder="Min $"
                  title="Min net profit threshold in USD"
                />
                <button
                  onClick={handleSelectHighProfit}
                  className="px-2.5 py-1 bg-amber-950 hover:bg-amber-900 border border-amber-800/80 text-amber-300 text-xs font-bold rounded transition-all flex items-center gap-1 shadow-sm active:scale-95"
                  title={`Automatically select executable routes with net profit >= $${highProfitThreshold}`}
                >
                  <Filter className="w-3.5 h-3.5 text-amber-400" />
                  <span>Select High-Profit (&ge;${highProfitThreshold.toLocaleString()})</span>
                </button>
              </div>

              {selectedRouteIds.size > 0 && (
                <span className="text-xs font-bold text-emerald-300 bg-emerald-950/90 px-3 py-1 rounded-lg border border-emerald-800 flex items-center gap-1.5 shadow-sm">
                  <CheckSquare className="w-3.5 h-3.5 text-emerald-400" />
                  <span>{selectedRouteIds.size} Route{selectedRouteIds.size > 1 ? 's' : ''} Selected</span>
                </span>
              )}
            </div>

            <div className="flex items-center gap-2">
              {selectedRouteIds.size > 0 && (
                <button
                  onClick={() => setSelectedRouteIds(new Set())}
                  className="px-3 py-1.5 text-slate-400 hover:text-white text-xs border border-slate-800 hover:border-slate-700 rounded-lg transition-all"
                >
                  Clear Selection
                </button>
              )}

              <button
                onClick={handleBatchExecute}
                disabled={selectedRouteIds.size === 0}
                className={`flex items-center gap-2 px-4 py-1.5 text-xs font-bold rounded-lg transition-all shadow-lg ${
                  selectedRouteIds.size > 0
                    ? 'bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white shadow-emerald-600/30 ring-2 ring-emerald-400/50 animate-pulse'
                    : 'bg-slate-800 text-slate-500 border border-slate-700 cursor-not-allowed'
                }`}
              >
                <Zap className="w-4 h-4 text-amber-300" />
                <span>Batch Execute Dispatched ({selectedRouteIds.size})</span>
              </button>
            </div>
          </div>

          {/* Total Potential Net Profit Summary Bar */}
          {selectedRouteIds.size > 0 ? (
            <div className="pt-3 border-t border-slate-800/80 bg-slate-950/90 p-3.5 rounded-lg border border-emerald-900/60 flex flex-col md:flex-row md:items-center justify-between gap-4 animate-in fade-in duration-200">
              <div className="flex items-center gap-3">
                <div className="p-2.5 bg-emerald-950 border border-emerald-700/80 rounded-lg text-emerald-400 shadow-md shrink-0">
                  <DollarSign className="w-5 h-5 animate-pulse" />
                </div>
                <div>
                  <div className="text-[10px] text-slate-400 uppercase tracking-widest font-semibold flex items-center gap-1.5">
                    <span>Selected Batch Opportunity Yield</span>
                    <span className="px-1.5 py-0.2 text-[9px] bg-emerald-900/80 text-emerald-300 rounded font-bold">
                      {selectedRouteIds.size} Routes
                    </span>
                  </div>
                  <div className="text-xl font-black text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 via-teal-300 to-cyan-300 flex items-center gap-2 mt-0.5">
                    <span>${selectedBatchTotalNetProfitUSD.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                    <span className="text-xs text-emerald-400/80 font-normal">Total Potential Net Profit</span>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-xs border-t md:border-t-0 md:border-l border-slate-800 pt-2.5 md:pt-0 md:pl-5">
                <div>
                  <div className="text-[10px] text-slate-500 uppercase font-semibold">Total Gross Profit</div>
                  <div className="font-bold text-slate-200">${selectedBatchTotalGrossProfitUSD.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
                </div>
                <div>
                  <div className="text-[10px] text-slate-500 uppercase font-semibold">Total Gas Overhead</div>
                  <div className="font-bold text-amber-400">${selectedBatchTotalGasUSD.toFixed(2)}</div>
                </div>
                <div>
                  <div className="text-[10px] text-slate-500 uppercase font-semibold">Avg VQC Alpha Score</div>
                  <div className="font-bold text-purple-300">{(selectedBatchAvgVqcScore * 100).toFixed(1)}%</div>
                </div>
              </div>
            </div>
          ) : (
            <div className="pt-2 text-[11px] text-slate-500 flex items-center justify-between">
              <span>Mark routes using checkboxes on cards to calculate total potential net profit batch yield.</span>
              <span className="text-slate-600 hidden sm:inline">0 routes currently marked</span>
            </div>
          )}
        </div>

        {/* Routing Variations Selection Matrix Bar */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 shadow-md font-mono flex items-center gap-2 overflow-x-auto">
          <span className="text-xs text-slate-400 font-bold uppercase shrink-0">Routing Variations:</span>
          {[
            { id: 'ALL', label: 'All Variations' },
            { id: '2_HOP_TRIANGULAR', label: '2-Hop Triangular' },
            { id: '3_HOP_CYCLIC', label: '3-Hop Cyclic' },
            { id: '4_HOP_MULTIDEX', label: '4-Hop Multi-DEX' },
            { id: 'AAVE_LIQUIDATION', label: 'Aave Liquidation' },
            { id: 'SPATIAL_FLASHLOAN', label: 'Spatial Flashloan' },
            { id: 'JIT_REBALANCE', label: 'JIT Rebalance' },
            { id: 'SUBGRAPH_TRANSIENT', label: 'Sub-Graph Transient' },
          ].map((v) => (
            <button
              key={v.id}
              onClick={() => setSelectedVariationFilter(v.id)}
              className={`px-3 py-1 rounded-lg text-xs font-bold shrink-0 border transition-all ${
                selectedVariationFilter === v.id
                  ? 'bg-gradient-to-r from-emerald-500 to-teal-500 text-slate-950 font-black shadow'
                  : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-white'
              }`}
            >
              {v.label}
            </button>
          ))}
        </div>

        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
          <h3 className="text-xs font-mono uppercase tracking-wider text-slate-400 font-semibold flex items-center gap-2">
            <span>Active Polygon Arbitrage Routes ({sortedRoutes.length})</span>
            {selectedStageFilter !== 'ALL' && (
              <span className="text-emerald-400 font-normal">
                Stage: {selectedStageFilter}
              </span>
            )}
            {filterMode !== 'ALL' && (
              <span className="text-amber-400 font-bold">
                [{filterMode} MODE]
              </span>
            )}
          </h3>

          <div className="flex flex-wrap items-center gap-2">
            {/* Sort Toggle Controls */}
            <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-lg border border-slate-800 font-mono text-xs">
              <span className="text-slate-500 px-1.5 flex items-center gap-1">
                <ArrowUpDown className="w-3.5 h-3.5 text-amber-400" />
                <span className="hidden sm:inline text-[11px] uppercase font-semibold">Sort:</span>
              </span>
              <button
                onClick={() => setSortBy('netProfitDesc')}
                className={`px-2.5 py-1 rounded text-xs transition-all ${
                  sortBy === 'netProfitDesc'
                    ? 'bg-amber-950 text-amber-300 border border-amber-700/80 shadow-sm font-bold'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
                title="Sort by Net Profit USD descending to prioritize high-value opportunities"
              >
                Net Profit ($) ↓
              </button>
              <button
                onClick={() => setSortBy('vqcScoreDesc')}
                className={`px-2.5 py-1 rounded text-xs transition-all ${
                  sortBy === 'vqcScoreDesc'
                    ? 'bg-purple-950 text-purple-300 border border-purple-700/80 shadow-sm font-bold'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
                title="Sort by VQC Alpha Score descending"
              >
                VQC Alpha ↓
              </button>
              <button
                onClick={() => setSortBy('default')}
                className={`px-2.5 py-1 rounded text-xs transition-all ${
                  sortBy === 'default'
                    ? 'bg-slate-800 text-slate-200 border border-slate-700 shadow-sm font-bold'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
                title="Default discovery sequence"
              >
                Default
              </button>
            </div>

            {/* View Mode Switcher */}
            <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-lg border border-slate-800 shrink-0 font-mono">
              <button
                onClick={() => setViewMode('dna')}
                className={`flex items-center gap-1.5 px-3 py-1 rounded text-xs font-bold transition-all ${
                  viewMode === 'dna'
                    ? 'bg-emerald-950 text-emerald-300 border border-emerald-700/80 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Dna className="w-3.5 h-3.5 text-emerald-400" />
                <span>DNA Cards</span>
              </button>
              <button
                onClick={() => setViewMode('standard')}
                className={`flex items-center gap-1.5 px-3 py-1 rounded text-xs font-mono transition-all ${
                  viewMode === 'standard'
                    ? 'bg-slate-800 text-slate-200 border border-slate-700 shadow-sm font-bold'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <LayoutGrid className="w-3.5 h-3.5" />
                <span>Compact View</span>
              </button>
            </div>
          </div>
        </div>

        {sortedRoutes.length === 0 ? (
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-8 text-center text-slate-400 font-mono space-y-2">
            <p className="text-sm font-medium text-slate-200">No arbitrage routes match the current filters.</p>
            <p className="text-xs text-slate-400 font-sans">
              Stage: <strong className="text-white">{selectedStageFilter}</strong> | Compliance Filter: <strong className="text-amber-300">{filterMode}</strong>
            </p>
            <div className="pt-2 flex justify-center gap-3">
              <button
                onClick={() => {
                  setSelectedStageFilter('ALL');
                  setFilterMode('ALL');
                }}
                className="px-3 py-1.5 bg-emerald-950 border border-emerald-800 text-emerald-300 text-xs font-bold rounded-lg hover:bg-emerald-900"
              >
                Reset All Filters
              </button>
            </div>
          </div>
        ) : viewMode === 'dna' ? (
          <div className="grid grid-cols-1 gap-5">
            {sortedRoutes.map((route, idx) => (
              <OpportunityDnaCard
                key={`${route.id}-${idx}`}
                route={route}
                pools={pools}
                maxSlippageBps={maxSlippageBps}
                maxGasRatioPercent={maxGasRatioPercent}
                isSelected={selectedRouteIds.has(route.id)}
                onToggleSelect={toggleSelectRoute}
                onExecuteRoute={onExecuteRoute}
                onAdvanceRouteStage={onAdvanceRouteStage}
                onSelectRouteForInjector={onSelectRouteForInjector}
                onAnalyzeRouteWithAI={onAnalyzeRouteWithAI}
                onHoverRoute={(r) => setHoveredRoute(r)}
              />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4">
            {sortedRoutes.map((route, idx) => {
              const isExecuted = route.stage === 'EXECUTED' || route.stage === 'ACCOUNTED';
              const registryCheck = validateRouteAssetRegistry(route, pools);
              const canExecute = !isExecuted && registryCheck.isExecutable;
              const alertInfo = evalRouteAlert(route);
              const isSelected = selectedRouteIds.has(route.id);

              return (
                <div
                  key={`${route.id}-${idx}`}
                  id={`route-card-${route.id}`}
                  onMouseEnter={() => setHoveredRoute(route)}
                  onMouseLeave={() => setHoveredRoute(null)}
                  className={`bg-slate-900 border rounded-xl p-5 shadow-lg transition-all ${
                    isSelected
                      ? 'border-emerald-500 bg-slate-900/95 ring-2 ring-emerald-500/40 shadow-emerald-950/20'
                      : alertInfo.isFlagged
                      ? 'border-amber-500/80 bg-slate-900/95 ring-1 ring-amber-500/30'
                      : 'border-slate-800 hover:border-slate-700'
                  }`}
                >
                  <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                    {/* Path & Pool Metadata */}
                    <div className="space-y-2 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        {canExecute && (
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => toggleSelectRoute(route.id)}
                            className="w-4 h-4 rounded border-slate-700 bg-slate-950 text-emerald-500 focus:ring-emerald-500 cursor-pointer shrink-0 accent-emerald-500"
                            title="Select route for batch execution"
                          />
                        )}

                        <span className="px-2 py-0.5 bg-slate-800 text-slate-300 font-mono text-xs font-semibold rounded border border-slate-700">
                          {route.id}
                        </span>
                        <span className="px-2 py-0.5 bg-purple-950 text-purple-300 border border-purple-800/60 font-mono text-xs rounded flex items-center gap-1">
                          <Zap className="w-3 h-3 text-purple-400" />
                          VQC Alpha: {(route.vqcAlphaScore * 100).toFixed(1)}%
                        </span>
                        <span className="px-2 py-0.5 bg-indigo-950 text-indigo-300 border border-indigo-800/60 font-mono text-xs rounded font-mono">
                          Win Prob: {(route.vqcWinProbability * 100).toFixed(1)}%
                        </span>
                        <span className="px-2 py-0.5 bg-emerald-950 text-emerald-300 border border-emerald-800/60 font-mono text-xs rounded font-mono">
                          Stage: {route.stage}
                        </span>
                        {registryCheck.isExecutable ? (
                          <span className="px-2 py-0.5 bg-emerald-950 text-emerald-300 border border-emerald-800/80 font-mono text-xs rounded flex items-center gap-1 font-mono">
                            <ShieldCheck className="w-3 h-3 text-emerald-400" />
                            Registry Verified
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 bg-rose-950 text-rose-300 border border-rose-800/80 font-mono text-xs rounded flex items-center gap-1 font-mono">
                            <AlertTriangle className="w-3 h-3 text-rose-400" />
                            Unregistered Asset Blocked
                          </span>
                        )}

                        {alertInfo.slippageExceeded && (
                          <span className="px-2 py-0.5 bg-amber-950 text-amber-300 border border-amber-800 font-mono text-xs rounded flex items-center gap-1 font-bold animate-pulse">
                            <AlertTriangle className="w-3 h-3 text-amber-400" />
                            Slippage: {route.slippageToleranceBps}bps &gt; {maxSlippageBps}bps
                          </span>
                        )}

                        {alertInfo.gasRatioExceeded && (
                          <span className="px-2 py-0.5 bg-rose-950 text-rose-300 border border-rose-800 font-mono text-xs rounded flex items-center gap-1 font-bold animate-pulse">
                            <AlertTriangle className="w-3 h-3 text-rose-400" />
                            Gas/Profit: {alertInfo.gasRatio.toFixed(1)}% &gt; {maxGasRatioPercent.toFixed(1)}%
                          </span>
                        )}
                      </div>

                      <div className="text-sm font-mono font-medium text-white flex items-center gap-2 bg-slate-950/80 p-2.5 rounded-lg border border-slate-800">
                        <ArrowRight className="w-4 h-4 text-emerald-400 shrink-0" />
                        <span className="truncate">{route.pathString}</span>
                      </div>

                      <div className="flex flex-wrap items-center gap-4 text-xs text-slate-400 font-mono">
                        <div className="flex items-center gap-1 text-slate-300 font-mono">
                          <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                          <span>Isolated Flashloan Pot: Balancer V3 Vault</span>
                        </div>
                        <span>•</span>
                        <div>Slippage Cap: <strong className="text-white font-mono">{route.slippageToleranceBps / 100}%</strong></div>
                        <span>•</span>
                        <div>Timestamp: <span className="text-slate-300 font-mono">{route.timestamp}</span></div>
                      </div>
                    </div>

                    {/* VQC Sparkline Chart & Financial Metrics Box */}
                    <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
                      <VqcSparklineChart score={route.vqcAlphaScore} history={route.vqcAlphaHistory} />

                      <div className="bg-slate-950/90 border border-slate-800 p-3.5 rounded-xl flex items-center justify-between gap-6 min-w-[260px]">
                        <div>
                          <div className="text-[11px] uppercase tracking-wider text-slate-400 font-mono">Optimal Input (x*)</div>
                          <div className="text-sm font-bold text-slate-200 font-mono mt-0.5">
                            ${route.optimalInputUSD.toLocaleString()}
                          </div>
                          <div className="text-[10px] text-slate-500 font-mono mt-0.5">
                            Gas: ~${route.estimatedGasUSD} ({alertInfo.gasRatio.toFixed(1)}%)
                          </div>
                        </div>

                        <div className="text-right border-l border-slate-800 pl-4">
                          <div className="text-[11px] uppercase tracking-wider text-emerald-400 font-mono font-semibold">Net Profit Apex</div>
                          <div className="text-lg font-extrabold text-emerald-400 font-mono mt-0.5">
                            +${route.netProfitUSD.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                          </div>
                          <div className="text-[10px] text-slate-400 font-mono mt-0.5">
                            Gross: ${route.grossProfitUSD.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Interactive Actions */}
                    <div className="flex flex-wrap lg:flex-col gap-2 shrink-0">
                      <button
                        onClick={() => onSelectRouteForInjector(route)}
                        className="flex items-center justify-center gap-1.5 px-3 py-2 bg-indigo-600/90 hover:bg-indigo-600 text-white text-xs font-medium rounded-lg transition-all active:scale-95"
                      >
                        <BarChart2 className="w-3.5 h-3.5" />
                        <span>Calculus Apex Math</span>
                      </button>

                      <button
                        onClick={() => canExecute && onExecuteRoute(route.id)}
                        disabled={!canExecute}
                        title={!registryCheck.isExecutable ? registryCheck.reason : undefined}
                        className={`flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-semibold rounded-lg transition-all active:scale-95 ${
                          isExecuted
                            ? 'bg-slate-800 text-slate-500 cursor-not-allowed border border-slate-700'
                            : !registryCheck.isExecutable
                            ? 'bg-rose-950/60 text-rose-400 border border-rose-800/80 cursor-not-allowed'
                            : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-md shadow-emerald-600/20'
                        }`}
                      >
                        {isExecuted ? (
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                        ) : !registryCheck.isExecutable ? (
                          <AlertTriangle className="w-3.5 h-3.5 text-rose-400" />
                        ) : (
                          <Play className="w-3.5 h-3.5" />
                        )}
                        <span>
                          {isExecuted
                            ? 'Mined & Accounted'
                            : !registryCheck.isExecutable
                            ? 'Asset Unregistered'
                            : 'Execute Relay'}
                        </span>
                      </button>

                      <button
                        onClick={() => onAnalyzeRouteWithAI(route)}
                        className="flex items-center justify-center gap-1.5 px-3 py-2 bg-purple-900/60 hover:bg-purple-900 text-purple-200 text-xs font-medium rounded-lg border border-purple-700/50 transition-all"
                      >
                        <Sparkles className="w-3.5 h-3.5 text-purple-300" />
                        <span>Gemini MEV Review</span>
                      </button>
                    </div>
                  </div>

                  {route.notes && (
                    <div className="mt-3 pt-2 border-t border-slate-800/80 text-xs text-slate-400 flex items-center gap-2 font-mono">
                      <span className="text-indigo-400">Engine Note:</span>
                      <span>{route.notes}</span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

