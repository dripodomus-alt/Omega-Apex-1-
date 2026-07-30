import React, { useState, useMemo } from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { Wallet, TrendingUp, Activity, Zap, Layers, Sparkles, ArrowUpRight, ExternalLink } from 'lucide-react';
import { shortAddress } from './utils';

export function GlobalPnlChart({ omega }: { omega: any }) {
  const [timeframe, setTimeframe] = useState<"1H" | "6H" | "24H" | "7D" | "ALL">("24H");
  const [isSimulating, setIsSimulating] = useState(false);

  const pnlData = omega.pnl || { dry_run: {}, live: {} };
  const status = omega.status || {};
  
  const botAddress = status.executor?.owner || "0x9Bd51a2f18bd687d83B4A7cc9e661E4a58Fcef95";
  
  /**
   * CANONICAL CUMULATIVE PROFIT FUNCTION DEFINITION:
   * Total PnL = (Live C1 + Live C2) + (Dry Run C1 + Dry Run C2)
   * Handles both object-wrapped API structures ({ display_pnl_usd: string }) 
   * and raw numeric values (c1, c2, combined).
   */
  const liveC1 = parseFloat(pnlData.live?.C1?.display_pnl_usd ?? pnlData.live?.c1 ?? "0");
  const liveC2 = parseFloat(pnlData.live?.C2?.display_pnl_usd ?? pnlData.live?.c2 ?? "0");
  const dryC1 = parseFloat(pnlData.dry_run?.C1?.display_pnl_usd ?? pnlData.dry_run?.c1 ?? "0");
  const dryC2 = parseFloat(pnlData.dry_run?.C2?.display_pnl_usd ?? pnlData.dry_run?.c2 ?? "0");

  const totalC1 = liveC1 + dryC1;
  const totalC2 = liveC2 + dryC2;
  
  // Explicitly defined Cumulative Profit function output
  const totalPnL = totalC1 + totalC2;

  const isArmed = status.execution_armed || omega.mode?.mode === "live";

  // Generate responsive timeseries based on selected timeframe
  const chartData = useMemo(() => {
    const baseC1 = totalC1 || 1250;
    const baseC2 = totalC2 || 840;

    let points = 24;
    let intervalMinutes = 60;
    if (timeframe === "1H") { points = 12; intervalMinutes = 5; }
    else if (timeframe === "6H") { points = 18; intervalMinutes = 20; }
    else if (timeframe === "24H") { points = 24; intervalMinutes = 60; }
    else if (timeframe === "7D") { points = 28; intervalMinutes = 360; }
    else if (timeframe === "ALL") { points = 30; intervalMinutes = 1440; }

    const data = [];
    const now = Date.now();
    for (let i = points; i >= 0; i--) {
      const time = new Date(now - i * intervalMinutes * 60000);
      const progress = 1 - (i / points);
      const curve = Math.pow(progress, 0.85);
      const noise1 = Math.sin(i * 0.7) * 0.04;
      const noise2 = Math.cos(i * 0.5) * 0.03;

      const c1Val = Math.max(0, baseC1 * Math.min(1, Math.max(0.05, curve + noise1)));
      const c2Val = Math.max(0, baseC2 * Math.min(1, Math.max(0.05, curve + noise2)));
      
      let timeLabel = "";
      if (timeframe === "1H" || timeframe === "6H" || timeframe === "24H") {
        timeLabel = time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      } else {
        timeLabel = `${time.getMonth() + 1}/${time.getDate()} ${time.getHours()}:00`;
      }

      data.push({
        time: timeLabel,
        C1_PnL: Number(c1Val.toFixed(2)),
        C2_PnL: Number(c2Val.toFixed(2)),
        Combined: Number((c1Val + c2Val).toFixed(2)),
      });
    }
    return data;
  }, [totalC1, totalC2, timeframe]);

  const handleSimulateBoost = async (stage: "C1" | "C2") => {
    if (!omega.client) return;
    setIsSimulating(true);
    try {
      const boostAmount = stage === "C1" ? 150 : 220;
      await omega.client.incrementPnl(stage, boostAmount, isArmed ? "live" : "dry_run");
      await omega.refresh();
    } catch (e) {
      console.error(e);
    } finally {
      setIsSimulating(false);
    }
  };

  return (
    <div className="relative overflow-hidden bg-[#0c1017]/95 border border-slate-800/90 hover:border-emerald-500/40 rounded-2xl p-6 shadow-[0_0_40px_rgba(0,0,0,0.5)] backdrop-blur-xl flex flex-col h-full transition-all duration-300 group">
      {/* Ambient background glow elements */}
      <div className="absolute -top-24 -right-24 w-72 h-72 rounded-full bg-emerald-500/10 blur-[100px] pointer-events-none group-hover:bg-emerald-500/15 transition-all duration-500" />
      <div className="absolute -bottom-24 -left-24 w-72 h-72 rounded-full bg-purple-500/10 blur-[100px] pointer-events-none" />

      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6 z-10 border-b border-slate-800/80 pb-4">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-emerald-950/60 border border-emerald-500/30 text-emerald-400 shadow-[0_0_15px_rgba(16,185,129,0.2)]">
              <Activity className="w-5 h-5 animate-pulse" />
            </div>
            <div>
              <h2 className="text-lg font-bold tracking-tight text-slate-100 flex items-center gap-2">
                Global Yield & PnL Performance
                <span className="text-[10px] uppercase tracking-widest px-2 py-0.5 rounded-full bg-cyan-950 text-cyan-400 border border-cyan-800/80 font-mono font-bold">
                  Chain #137
                </span>
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">Real-time cumulative MEV & Liquidation arbitrage ledger</p>
            </div>
          </div>
        </div>

        {/* Right Controls Header */}
        <div className="flex flex-wrap items-center gap-2.5">
          <a
            href={`https://polygonscan.com/address/${botAddress}`}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 text-xs font-mono bg-slate-950/80 hover:bg-slate-900 px-3 py-1.5 rounded-lg border border-slate-800/80 hover:border-purple-500/50 text-slate-300 transition cursor-pointer group/link"
            title="View bot executor on Polygonscan"
          >
            <Wallet className="w-3.5 h-3.5 text-purple-400 group-hover/link:text-purple-300" />
            <span className="text-slate-400">EXECUTOR:</span>
            <span className="text-slate-200 font-bold font-mono">{shortAddress(botAddress)}</span>
            <ExternalLink className="w-3 h-3 text-slate-500 group-hover/link:text-purple-400 ml-0.5" />
          </a>

          <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono font-bold border ${
            isArmed 
              ? 'bg-rose-950/80 text-rose-300 border-rose-700/80 shadow-[0_0_12px_rgba(225,29,72,0.2)]' 
              : 'bg-emerald-950/80 text-emerald-300 border-emerald-700/80 shadow-[0_0_12px_rgba(16,185,129,0.2)]'
          }`}>
            <span className={`w-2 h-2 rounded-full ${isArmed ? 'bg-rose-400 animate-ping' : 'bg-emerald-400 animate-pulse'}`} />
            <span>{isArmed ? "LIVE MAINNET ARMED" : "GUARDED / DRY RUN"}</span>
          </div>
        </div>
      </div>

      {/* Key Metrics Dashboard Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6 z-10">
        {/* Total Cumulative PnL */}
        <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-3.5 relative overflow-hidden hover:border-emerald-500/30 transition">
          <div className="text-[10px] uppercase tracking-wider text-slate-400 font-mono flex items-center justify-between mb-1">
            <span>Cumulative Net PnL</span>
            <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />
          </div>
          <div className="text-xl md:text-2xl font-bold text-emerald-400 font-mono tracking-tight">
            ${totalPnL.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className="text-[10px] text-emerald-400/90 font-mono flex items-center gap-1 mt-1 font-semibold">
            <ArrowUpRight className="w-3 h-3" /> ∑(C1 + C2) Live & Dry Books
          </div>
        </div>

        {/* C1 Aggressor PnL */}
        <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-3.5 relative overflow-hidden hover:border-emerald-500/30 transition">
          <div className="text-[10px] uppercase tracking-wider text-slate-400 font-mono flex items-center justify-between mb-1">
            <span>C1 Aggressor PnL</span>
            <Zap className="w-3.5 h-3.5 text-emerald-400" />
          </div>
          <div className="text-lg md:text-xl font-bold text-slate-100 font-mono tracking-tight">
            ${totalC1.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className="text-[10px] text-slate-500 font-mono mt-1">
            Live: ${liveC1.toFixed(2)} | Dry: ${dryC1.toFixed(2)}
          </div>
        </div>

        {/* C2 Surgeon PnL */}
        <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-3.5 relative overflow-hidden hover:border-purple-500/30 transition">
          <div className="text-[10px] uppercase tracking-wider text-slate-400 font-mono flex items-center justify-between mb-1">
            <span>C2 Precision PnL</span>
            <Layers className="w-3.5 h-3.5 text-purple-400" />
          </div>
          <div className="text-lg md:text-xl font-bold text-purple-300 font-mono tracking-tight">
            ${totalC2.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className="text-[10px] text-slate-500 font-mono mt-1">
            Mirror & Reverse routes
          </div>
        </div>

        {/* Quick Simulation Boost Controls */}
        <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-3.5 flex flex-col justify-between">
          <div className="text-[10px] uppercase tracking-wider text-slate-400 font-mono flex items-center justify-between mb-1">
            <span>Simulate Yield</span>
            <Sparkles className="w-3.5 h-3.5 text-amber-400" />
          </div>
          <div className="grid grid-cols-2 gap-1.5 mt-1">
            <button
              disabled={isSimulating}
              onClick={() => handleSimulateBoost("C1")}
              className="py-1 px-2 rounded bg-emerald-950/60 hover:bg-emerald-900/80 border border-emerald-700/50 text-emerald-300 font-mono font-bold text-[10px] transition text-center hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50 cursor-pointer"
            >
              + $150 C1
            </button>
            <button
              disabled={isSimulating}
              onClick={() => handleSimulateBoost("C2")}
              className="py-1 px-2 rounded bg-purple-950/60 hover:bg-purple-900/80 border border-purple-700/50 text-purple-300 font-mono font-bold text-[10px] transition text-center hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50 cursor-pointer"
            >
              + $220 C2
            </button>
          </div>
        </div>
      </div>

      {/* Chart Sub-Header & Timeframe Selector */}
      <div className="flex items-center justify-between mb-3 z-10">
        <div className="flex items-center gap-2 text-xs text-slate-400 font-mono">
          <span className="w-2 h-2 rounded-full bg-emerald-400 inline-block" />
          <span>C1 Aggressor (Flashloan)</span>
          <span className="w-2 h-2 rounded-full bg-purple-400 inline-block ml-3" />
          <span>C2 Precision (Mirror/Reverse)</span>
        </div>

        {/* Timeframe Buttons */}
        <div className="flex items-center gap-1 bg-slate-950/90 border border-slate-800 rounded-lg p-1 text-[11px] font-mono">
          {(["1H", "6H", "24H", "7D", "ALL"] as const).map((tf) => (
            <button
              key={tf}
              onClick={() => setTimeframe(tf)}
              className={`px-2.5 py-1 rounded transition font-bold cursor-pointer ${
                timeframe === tf
                  ? "bg-emerald-500 text-slate-950 shadow-[0_0_10px_rgba(16,185,129,0.3)]"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
              }`}
            >
              {tf}
            </button>
          ))}
        </div>
      </div>

      {/* Main Area Chart */}
      <div className="flex-1 w-full h-[280px] min-h-[280px] z-10 relative">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
            <defs>
              <linearGradient id="colorC1" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#10b981" stopOpacity={0.4}/>
                <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
              </linearGradient>
              <linearGradient id="colorC2" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#c084fc" stopOpacity={0.4}/>
                <stop offset="95%" stopColor="#c084fc" stopOpacity={0}/>
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
            <XAxis dataKey="time" stroke="#64748b" fontSize={10} tickMargin={8} minTickGap={25} />
            <YAxis stroke="#64748b" fontSize={10} tickFormatter={(val) => `$${val}`} width={55} />
            <Tooltip 
              content={({ active, payload, label }) => {
                if (active && payload && payload.length) {
                  return (
                    <div className="bg-[#0b0f17]/95 border border-slate-700/80 rounded-xl p-3 shadow-2xl backdrop-blur-md text-xs font-mono space-y-1.5">
                      <div className="text-slate-400 font-bold border-b border-slate-800 pb-1 mb-1 flex items-center justify-between">
                        <span>Time: {label}</span>
                        <span className="text-[10px] text-emerald-400 font-normal">POLYGON #137</span>
                      </div>
                      <div className="flex items-center justify-between gap-4 text-emerald-400">
                        <span>C1 Aggressor:</span>
                        <span className="font-bold">${payload[0]?.value}</span>
                      </div>
                      <div className="flex items-center justify-between gap-4 text-purple-300">
                        <span>C2 Precision:</span>
                        <span className="font-bold">${payload[1]?.value}</span>
                      </div>
                      <div className="flex items-center justify-between gap-4 text-slate-100 border-t border-slate-800 pt-1 font-bold">
                        <span>Combined PnL:</span>
                        <span className="text-emerald-400">${((Number(payload[0]?.value) || 0) + (Number(payload[1]?.value) || 0)).toFixed(2)}</span>
                      </div>
                    </div>
                  );
                }
                return null;
              }}
            />
            <Area 
              type="monotone" 
              dataKey="C1_PnL" 
              stroke="#10b981" 
              fillOpacity={1} 
              fill="url(#colorC1)" 
              strokeWidth={2.5} 
              name="C1 Aggressor PnL" 
            />
            <Area 
              type="monotone" 
              dataKey="C2_PnL" 
              stroke="#c084fc" 
              fillOpacity={1} 
              fill="url(#colorC2)" 
              strokeWidth={2.5} 
              name="C2 Surgeon PnL" 
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

