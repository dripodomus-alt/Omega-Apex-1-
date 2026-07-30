import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Copy, ArrowRight, Activity, Zap, ShieldAlert, Cpu } from "lucide-react";

interface Opportunity {
  pair: string;
  route?: string;
  spread_bps?: number;
  profit_usd?: number;
  dex_a?: string;
  dex_b?: string;
  confidence?: number;
  c1ExecutionEligible?: boolean;
  c1ExecutionSlot?: number;
  status?: string;
  path?: string;
  venues?: string;
  rawSpreadBps?: string | number;
  rawSpreadDelta?: string | number;
  rawLeg1BuyPrice?: string | number;
  rawLeg2SellPrice?: string | number;
  leg1BuyPrice?: string | number;
  leg2SellPrice?: string | number;
  actualProfit?: string | number;
  actualProfitRaw?: string | number;
  netProfitUsd?: string | number;
  maxApplicableCapital?: string | number;
  routeRiskCap?: string | number;
  routeTvlRiskCap?: string | number;
  routePoolStateCap?: string | number;
  routePoolStateCapUsd?: string | number;
  routeMaxPoolReserveFractionBps?: string | number;
  capitalLimitedBy?: string;
  sizingRule?: string;
  reason?: string;
}

interface HyperImmersiveOpportunitiesProps {
  opportunities: Opportunity[];
  diagnostics?: any;
  connectionStatus?: "live" | "poll" | "reconnecting" | "connecting" | "error";
}

export default function HyperImmersiveOpportunities({ opportunities, diagnostics, connectionStatus = "poll" }: HyperImmersiveOpportunitiesProps) {
  const [activeId, setActiveId] = useState<number | null>(null);
  const diagnosticRoutes = diagnostics?.diagnosticRoutes || [];
  const displayOpportunities = opportunities.length ? opportunities : diagnosticRoutes;
  const showingDiagnostics = opportunities.length === 0 && diagnosticRoutes.length > 0;
  const discovery = diagnostics?.discovery || {};
  const routeLimits = diagnostics?.routeLimits || {};
  const totalRoutes = discovery.total_routes_observed ?? routeLimits.totalRoutesObserved ?? displayOpportunities.length;
  const topRouteLimit = routeLimits.topRouteDisplayLimit ?? discovery.top_50_routes_visible ?? 50;
  const visibleRoutes = showingDiagnostics
    ? routeLimits.diagnosticVisibleRoutes ?? diagnosticRoutes.length
    : routeLimits.visibleRoutes ?? opportunities.length;
  const c1ExecutableVisible = discovery.c1_executable_visible ?? routeLimits.c1ExecutableVisible ?? opportunities.filter((opp) => opp.c1ExecutionEligible || opp.status === "EXECUTABLE_PROFIT_CANDIDATE").length;
  const c1Limit = routeLimits.c1ExecutableLimitPerCycle ?? discovery.c1_executable_limit_per_cycle ?? 10;
  const c2PerC1Limit = routeLimits.c2PerC1Limit ?? discovery.c2_per_c1_limit ?? 5;
  const c2Limit = routeLimits.c2DecisionLimitPerCycle ?? discovery.c2_decision_limit_per_cycle ?? 50;
  const c2DecisionCount = routeLimits.c2DecisionCount ?? discovery.c2_decision_count ?? 0;
  const statusText = connectionStatus === "live"
    ? diagnostics?.summary || "Live opportunity feed connected"
    : "API feed disconnected or returning invalid data";
  const statusTone = connectionStatus === "live" ? "text-cyan-400" : "text-red-400";
  const displayNumber = (value: any, digits = 6) => {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed.toFixed(digits) : String(value ?? "NA");
  };

  // Background grid animation logic could be added here
  
  return (
    <div className="relative w-full h-full min-h-[400px] bg-[#050505] overflow-hidden rounded-xl border border-cyan-500/20 shadow-[inset_0_1px_0_rgba(255,255,255,0.07),inset_0_0_32px_rgba(0,0,0,0.38),0_0_40px_rgba(0,255,255,0.05)] glass-specular p-6 font-mono">
      {/* Immersive Background Effects */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-0 left-0 w-full h-[1px] bg-gradient-to-r from-transparent via-cyan-500 to-transparent opacity-30" />
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:24px_24px] [mask-image:radial-gradient(ellipse_60%_60%_at_50%_50%,#000_70%,transparent_100%)]" />
        <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[400px] bg-cyan-900/10 blur-[100px] rounded-full mix-blend-screen" />
      </div>

      <div className="relative z-10 flex flex-col h-full">
        {/* Header Section */}
        <div className="flex items-center justify-between mb-8 pb-4 border-b border-cyan-500/20">
          <div className="flex items-center gap-4">
            <div className="relative flex items-center justify-center w-12 h-12 bg-cyan-950/50 rounded-lg border border-cyan-500/40 shadow-[0_0_15px_rgba(0,255,255,0.2)] overflow-hidden">
              <motion.div 
                animate={{ rotate: 360 }}
                transition={{ duration: 4, repeat: Infinity, ease: "linear" }}
                className="absolute inset-0 border-t-2 border-cyan-400 rounded-full opacity-50 m-1"
              />
              <Zap className="w-5 h-5 text-cyan-400" />
            </div>
            <div>
              <h2 className="text-xl font-bold tracking-widest text-transparent bg-clip-text bg-gradient-to-r from-white to-cyan-400">
                HYPER IMMERSIVE 2.0
              </h2>
              <div className="flex items-center gap-2 mt-1">
                <span className={`w-2 h-2 rounded-full ${connectionStatus === "live" ? "bg-cyan-400" : "bg-red-500"} animate-pulse`} />
                <span className={`text-xs tracking-widest uppercase ${connectionStatus === "live" ? "text-cyan-500/70" : "text-red-400/80"}`}>
                  {connectionStatus === "live" ? "Nexus Detection Matrix active" : "API feed not synchronized"}
                </span>
              </div>
            </div>
          </div>
          
          <div className="flex flex-col items-end">
            <span className="text-4xl font-bold tracking-tighter text-cyan-400 drop-shadow-[0_0_10px_rgba(0,255,255,0.4)]">
              {displayOpportunities.length.toString().padStart(2, '0')}
            </span>
            <span className="text-[10px] uppercase tracking-[0.2em] text-gray-500">
              {showingDiagnostics ? "Diagnostic Vectors" : "Live Vectors"}
            </span>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-5 text-[10px] uppercase tracking-wider">
          <div className="border border-cyan-500/15 bg-black/30 rounded-md px-3 py-2">
            <span className="block text-gray-600">Total Routes</span>
            <span className="text-cyan-300 font-bold">{totalRoutes}</span>
          </div>
          <div className="border border-cyan-500/15 bg-black/30 rounded-md px-3 py-2">
            <span className="block text-gray-600">Top Routes</span>
            <span className="text-cyan-300 font-bold">{visibleRoutes}/{topRouteLimit}</span>
          </div>
          <div className="border border-cyan-500/15 bg-black/30 rounded-md px-3 py-2">
            <span className="block text-gray-600">C1 Exec Top</span>
            <span className="text-emerald-300 font-bold">{c1ExecutableVisible}/{c1Limit}</span>
          </div>
          <div className="border border-cyan-500/15 bg-black/30 rounded-md px-3 py-2">
            <span className="block text-gray-600">C2 {c1Limit}x{c2PerC1Limit}</span>
            <span className="text-yellow-300 font-bold">{c2DecisionCount}/{c2Limit}</span>
          </div>
        </div>

        {/* Opportunity Grid */}
        <div className="flex-1 overflow-y-auto pr-2 scrollbar-none">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 pb-4">
            <AnimatePresence>
              {displayOpportunities.map((opp, idx) => (
                <motion.div
                  key={`${opp.pair}-${idx}`}
                  initial={{ opacity: 0, y: 20, scale: 0.95 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.9 }}
                  transition={{ duration: 0.4, delay: idx * 0.05 }}
                  onMouseEnter={() => setActiveId(idx)}
                  onMouseLeave={() => setActiveId(null)}
                  className={`
                    relative group cursor-pointer overflow-hidden rounded-xl border transition-all duration-300
                    ${activeId === idx 
                      ? 'bg-cyan-950/40 border-cyan-400 shadow-[0_0_30px_rgba(0,255,255,0.15)] z-20' 
                      : 'bg-[#0a0a0c] border-[#1e2025] hover:border-cyan-500/50 hover:bg-[#0c0f12] z-10'}
                  `}
                >
                  {/* Card Glow Effect */}
                  <div className="absolute inset-0 bg-gradient-to-br from-cyan-500/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
                  
                  <div className="p-5 flex flex-col h-full relative z-10">
                    <div className="flex justify-between items-start mb-4">
                      <div>
                        <div className="text-xs text-cyan-500 font-bold tracking-widest mb-1">{opp.pair || opp.path || "ROUTE"}</div>
                        <div className="flex items-center gap-2 text-[10px] text-gray-400 tracking-wider font-semibold">
                          <span className="px-1.5 py-0.5 rounded bg-gray-800 text-gray-300">{opp.dex_a || "DEX-A"}</span>
                          <ArrowRight className="w-3 h-3 text-cyan-500" />
                          <span className="px-1.5 py-0.5 rounded bg-gray-800 text-gray-300">{opp.dex_b || "DEX-B"}</span>
                        </div>
                      </div>
                      <div className="flex flex-col items-end">
                        <span className="text-lg font-bold text-[#00f5a0] leading-none drop-shadow-[0_0_8px_rgba(0,245,160,0.3)]">
                          {Number(opp.netProfitUsd ?? opp.profit_usd ?? 0) >= 0 ? "+" : ""}${Number(opp.netProfitUsd ?? opp.profit_usd ?? 0).toFixed(2)}
                        </span>
                        <span className="text-[9px] text-[#00f5a0]/60 mt-1 uppercase tracking-wider">
                          {displayNumber(opp.rawSpreadBps ?? opp.spread_bps ?? 0, 3)} RAW BPS
                        </span>
                        <span className={`text-[8px] mt-1 uppercase tracking-wider ${opp.c1ExecutionEligible ? "text-emerald-300" : "text-gray-500"}`}>
                          {opp.c1ExecutionEligible ? `C1 SLOT ${opp.c1ExecutionSlot}` : "LIST ONLY"}
                        </span>
                      </div>
                    </div>

                    <div className="mt-auto">
                      <div className="flex justify-between text-[10px] text-gray-500 mb-1 font-semibold tracking-wider">
                        <span>CONFIDENCE</span>
                        <span className="text-cyan-400">{opp.confidence || 98}%</span>
                      </div>
                      <div className="h-1.5 w-full bg-gray-900 rounded-full overflow-hidden relative">
                        <motion.div 
                          initial={{ width: 0 }}
                          animate={{ width: `${opp.confidence || 98}%` }}
                          transition={{ duration: 1, ease: "easeOut" }}
                          className="absolute top-0 left-0 h-full bg-gradient-to-r from-cyan-600 to-cyan-400 shadow-[0_0_10px_rgba(0,255,255,0.5)]"
                        />
                      </div>
                    </div>

                    {(opp.path || opp.venues) && (
                      <div className="mt-3 text-[9px] text-gray-500 leading-relaxed break-words">
                        {opp.path && <div>{opp.path}</div>}
                        {opp.venues && <div className="text-gray-600">{opp.venues}</div>}
                      </div>
                    )}

                    <div className="mt-3 grid grid-cols-2 gap-2 text-[9px] leading-tight">
                      <div className="border border-cyan-500/10 bg-black/25 rounded px-2 py-1.5">
                        <span className="block text-gray-600 uppercase">Raw Buy</span>
                        <span className="text-cyan-200 font-bold">{displayNumber(opp.rawLeg1BuyPrice, 8)}</span>
                      </div>
                      <div className="border border-cyan-500/10 bg-black/25 rounded px-2 py-1.5">
                        <span className="block text-gray-600 uppercase">Raw Sell</span>
                        <span className="text-cyan-200 font-bold">{displayNumber(opp.rawLeg2SellPrice, 8)}</span>
                      </div>
                      <div className="border border-cyan-500/10 bg-black/25 rounded px-2 py-1.5">
                        <span className="block text-gray-600 uppercase">Quote Buy</span>
                        <span className="text-yellow-200 font-bold">{displayNumber(opp.leg1BuyPrice, 8)}</span>
                      </div>
                      <div className="border border-cyan-500/10 bg-black/25 rounded px-2 py-1.5">
                        <span className="block text-gray-600 uppercase">Quote Sell</span>
                        <span className="text-yellow-200 font-bold">{displayNumber(opp.leg2SellPrice, 8)}</span>
                      </div>
                      <div className="col-span-2 border border-cyan-500/10 bg-black/25 rounded px-2 py-1.5">
                        <span className="block text-gray-600 uppercase">Actual Profit After Costs</span>
                        <span className={Number(opp.actualProfit ?? opp.netProfitUsd ?? 0) >= 0 ? "text-emerald-300 font-bold" : "text-red-300 font-bold"}>
                          {displayNumber(opp.actualProfit ?? opp.netProfitUsd, 6)}
                        </span>
                      </div>
                      <div className="border border-cyan-500/10 bg-black/25 rounded px-2 py-1.5">
                        <span className="block text-gray-600 uppercase">Max Capital</span>
                        <span className="text-cyan-200 font-bold">{displayNumber(opp.maxApplicableCapital, 6)}</span>
                      </div>
                      <div className="border border-cyan-500/10 bg-black/25 rounded px-2 py-1.5">
                        <span className="block text-gray-600 uppercase">Pool Cap</span>
                        <span className="text-cyan-200 font-bold">{displayNumber(opp.routePoolStateCap, 6)}</span>
                      </div>
                      <div className="border border-cyan-500/10 bg-black/25 rounded px-2 py-1.5">
                        <span className="block text-gray-600 uppercase">TVL Cap</span>
                        <span className="text-gray-300 font-bold">{displayNumber(opp.routeTvlRiskCap ?? opp.routeRiskCap, 6)}</span>
                      </div>
                      <div className="border border-cyan-500/10 bg-black/25 rounded px-2 py-1.5">
                        <span className="block text-gray-600 uppercase">Limiter</span>
                        <span className="text-yellow-200 font-bold">{opp.capitalLimitedBy || "NA"}</span>
                      </div>
                      <div className="col-span-2 border border-cyan-500/10 bg-black/25 rounded px-2 py-1.5">
                        <span className="block text-gray-600 uppercase">Sizing Rule</span>
                        <span className="text-gray-300 font-bold">
                          {opp.sizingRule || `pool reserve <= ${displayNumber(opp.routeMaxPoolReserveFractionBps, 0)} bps`}
                        </span>
                      </div>
                    </div>

                    {/* Cyber Glitch Detail on Hover */}
                    <AnimatePresence>
                      {activeId === idx && (
                        <motion.div 
                          initial={{ opacity: 0, height: 0 }}
                          animate={{ opacity: 1, height: 'auto' }}
                          exit={{ opacity: 0, height: 0 }}
                          className="pt-4 mt-4 border-t border-cyan-500/20 flex items-center justify-between"
                        >
                           <div className="flex items-center gap-1.5 text-[9px] text-cyan-300 tracking-widest">
                             <Activity className="w-3 h-3" />
                             <span>{opp.c1ExecutionEligible ? "SYNCED & EXEC SLOT" : (opp.reason || "DIAGNOSTIC LISTED").slice(0, 80)}</span>
                           </div>
                           <button className="px-3 py-1 bg-cyan-500/20 hover:bg-cyan-500/40 text-cyan-100 rounded text-[9px] tracking-widest transition-colors uppercase border border-cyan-500/30">
                             {opp.c1ExecutionEligible ? "Execute Vector" : "Listed Only"}
                           </button>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
            
                {displayOpportunities.length === 0 && (
              <div className="col-span-full min-h-44 flex flex-col items-center justify-center border border-dashed border-[#1e2025] rounded-xl text-gray-500 px-4 text-center">
                <ShieldAlert className={`w-8 h-8 mb-3 opacity-70 ${statusTone}`} />
                <span className={`text-xs uppercase tracking-widest font-bold ${statusTone}`}>
                  {connectionStatus === "live" ? "No executable or diagnostic vectors" : "Opportunity API disconnected"}
                </span>
                <span className="text-[10px] mt-2 max-w-2xl leading-relaxed">
                  {statusText}
                </span>
                {connectionStatus === "live" && (
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-4 w-full max-w-2xl text-[9px] uppercase tracking-wider">
                    <div className="border border-[#1e2025] bg-black/30 rounded px-2 py-2">
                      <span className="block text-gray-600">Ready Pools</span>
                      <span className="text-cyan-300 font-bold">{discovery.ready_pools ?? 0}</span>
                    </div>
                    <div className="border border-[#1e2025] bg-black/30 rounded px-2 py-2">
                      <span className="block text-gray-600">Total Pools</span>
                      <span className="text-cyan-300 font-bold">{discovery.total_pools ?? 0}</span>
                    </div>
                    <div className="border border-[#1e2025] bg-black/30 rounded px-2 py-2">
                      <span className="block text-gray-600">Top Routes</span>
                      <span className="text-cyan-300 font-bold">{discovery.cached_spreads ?? 0}</span>
                    </div>
                    <div className="border border-[#1e2025] bg-black/30 rounded px-2 py-2">
                      <span className="block text-gray-600">Reason</span>
                      <span className="text-yellow-300 font-bold normal-case tracking-normal">{discovery.summary || "No executable spread passed gates"}</span>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
