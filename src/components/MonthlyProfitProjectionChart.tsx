import React, { useState } from 'react';
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
} from 'recharts';
import {
  TrendingUp,
  Calendar,
  Zap,
  Sliders,
  DollarSign,
  ArrowUpRight,
  ShieldCheck,
  Percent,
  Sparkles,
  BarChart3,
  Layers,
} from 'lucide-react';
import { SimulationAuditLog } from '../types';

interface MonthlyProfitProjectionChartProps {
  logs: SimulationAuditLog[];
}

export const MonthlyProfitProjectionChart: React.FC<MonthlyProfitProjectionChartProps> = ({ logs }) => {
  // Derive historical metrics from logs
  const successfulLogs = logs.filter((l) => l.status === 'SUCCESS');
  const historicalTotalProfit = successfulLogs.reduce((sum, l) => sum + l.netProfitUSD, 0);
  const sampleCount = successfulLogs.length || 1;
  const historicalAvgProfit = historicalTotalProfit > 0 ? historicalTotalProfit / sampleCount : 185;

  // Interactive controls state
  const [dailyTradesCount, setDailyTradesCount] = useState<number>(24); // Default 24 executions/day (1 per hr)
  const [winRatePercent, setWinRatePercent] = useState<number>(95);
  const [avgProfitPerTrade, setAvgProfitPerTrade] = useState<number>(Math.round(historicalAvgProfit));
  const [isCompounding, setIsCompounding] = useState<boolean>(true);
  const [dailyCompoundRateBps, setDailyCompoundRateBps] = useState<number>(15); // 0.15% daily reinvestment yield

  // Generate 30-day projection data
  const today = new Date();
  const projectionData = Array.from({ length: 30 }, (_, idx) => {
    const dayNum = idx + 1;
    const dateStr = new Date(today.getTime() + idx * 86400000).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
    });

    const expectedWins = dailyTradesCount * (winRatePercent / 100);
    const expectedLosses = dailyTradesCount * (1 - winRatePercent / 100);

    // Base daily profit calculation
    let baseDailyProfit = expectedWins * avgProfitPerTrade - expectedLosses * (avgProfitPerTrade * 0.4);

    if (isCompounding) {
      const compoundFactor = Math.pow(1 + dailyCompoundRateBps / 10000, idx);
      baseDailyProfit = baseDailyProfit * compoundFactor;
    }

    // Cumulative sum
    let cumulativeBase = 0;
    let cumulativeUpper = 0;
    let cumulativeLower = 0;

    for (let d = 1; d <= dayNum; d++) {
      let dProfit = expectedWins * avgProfitPerTrade - expectedLosses * (avgProfitPerTrade * 0.4);
      if (isCompounding) {
        dProfit *= Math.pow(1 + dailyCompoundRateBps / 10000, d - 1);
      }
      cumulativeBase += dProfit;
      cumulativeUpper += dProfit * 1.18; // +18% optimistic alpha variance
      cumulativeLower += dProfit * 0.82; // -18% conservative gas volatility variance
    }

    return {
      day: `Day ${dayNum}`,
      date: dateStr,
      dayNumber: dayNum,
      dailyProfit: Number(baseDailyProfit.toFixed(2)),
      cumulativeProfit: Number(cumulativeBase.toFixed(2)),
      upperBound: Number(cumulativeUpper.toFixed(2)),
      lowerBound: Number(cumulativeLower.toFixed(2)),
    };
  });

  const finalDay = projectionData[29];
  const projectedMonthlyTotal = finalDay.cumulativeProfit;
  const projectedMonthlyUpper = finalDay.upperBound;
  const projectedMonthlyLower = finalDay.lowerBound;
  const avgDailyYield = projectedMonthlyTotal / 30;

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl font-mono space-y-4">
      {/* Top Header & Extrapolation Controls */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b border-slate-800 pb-3">
        <div>
          <div className="flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-emerald-400" />
            <h3 className="text-xs font-bold text-white uppercase tracking-wider">
              30-Day Monthly Profit Projection Engine
            </h3>
            <span className="px-2 py-0.5 bg-emerald-950 text-emerald-300 border border-emerald-800 rounded text-[9px] font-bold flex items-center gap-1">
              <Sparkles className="w-3 h-3 text-emerald-400" />
              <span>Extrapolated Yield Model</span>
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Predict potential 30-day cumulative net returns extrapolated from live execution parameters and compounding reinvestment rate.
          </p>
        </div>

        {/* Quick Extrapolation Parameter Sliders */}
        <div className="flex flex-wrap items-center gap-3 shrink-0 text-xs">
          <div className="bg-slate-950 border border-slate-800 px-3 py-1.5 rounded-lg space-y-0.5">
            <div className="flex items-center justify-between gap-2 text-[10px] text-slate-400">
              <span>Executions / Day:</span>
              <span className="text-amber-400 font-bold">{dailyTradesCount}</span>
            </div>
            <input
              type="range"
              min={1}
              max={100}
              value={dailyTradesCount}
              onChange={(e) => setDailyTradesCount(Number(e.target.value))}
              className="w-28 bg-slate-900 accent-amber-400 cursor-pointer h-1 rounded"
            />
          </div>

          <div className="bg-slate-950 border border-slate-800 px-3 py-1.5 rounded-lg space-y-0.5">
            <div className="flex items-center justify-between gap-2 text-[10px] text-slate-400">
              <span>Win Rate %:</span>
              <span className="text-emerald-400 font-bold">{winRatePercent}%</span>
            </div>
            <input
              type="range"
              min={50}
              max={100}
              value={winRatePercent}
              onChange={(e) => setWinRatePercent(Number(e.target.value))}
              className="w-28 bg-slate-900 accent-emerald-400 cursor-pointer h-1 rounded"
            />
          </div>

          <div className="bg-slate-950 border border-slate-800 px-3 py-1.5 rounded-lg space-y-0.5">
            <div className="flex items-center justify-between gap-2 text-[10px] text-slate-400">
              <span>Avg Profit / Exec:</span>
              <span className="text-cyan-300 font-bold">${avgProfitPerTrade}</span>
            </div>
            <input
              type="range"
              min={10}
              max={1000}
              step={10}
              value={avgProfitPerTrade}
              onChange={(e) => setAvgProfitPerTrade(Number(e.target.value))}
              className="w-28 bg-slate-900 accent-cyan-400 cursor-pointer h-1 rounded"
            />
          </div>

          <label className="flex items-center gap-1.5 bg-slate-950 border border-purple-800 px-3 py-2 rounded-lg cursor-pointer">
            <input
              type="checkbox"
              checked={isCompounding}
              onChange={(e) => setIsCompounding(e.target.checked)}
              className="w-3.5 h-3.5 accent-purple-500 rounded"
            />
            <span className="text-purple-300 font-bold text-[11px]">Reinvest Compounding</span>
          </label>
        </div>
      </div>

      {/* Projections Key Summary Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="bg-slate-950/80 border border-emerald-800/80 p-3.5 rounded-lg shadow-inner space-y-1">
          <div className="text-[10px] text-slate-400 uppercase font-semibold">Projected 30-Day Net Return</div>
          <div className="text-lg font-black text-emerald-400">
            ${projectedMonthlyTotal.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className="text-[10px] text-emerald-500 font-bold flex items-center gap-1">
            <ArrowUpRight className="w-3 h-3" />
            <span>Extrapolated Baseline</span>
          </div>
        </div>

        <div className="bg-slate-950/80 border border-cyan-800/80 p-3.5 rounded-lg shadow-inner space-y-1">
          <div className="text-[10px] text-slate-400 uppercase font-semibold">Estimated Daily Average Yield</div>
          <div className="text-lg font-black text-cyan-300">
            ${avgDailyYield.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} / day
          </div>
          <div className="text-[10px] text-cyan-400/80 font-bold">
            Based on {dailyTradesCount} trades @ {winRatePercent}% win rate
          </div>
        </div>

        <div className="bg-slate-950/80 border border-purple-800/80 p-3.5 rounded-lg shadow-inner space-y-1">
          <div className="text-[10px] text-slate-400 uppercase font-semibold">Optimistic High Alpha (+18%)</div>
          <div className="text-lg font-black text-purple-300">
            ${projectedMonthlyUpper.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className="text-[10px] text-purple-400/80 font-bold">
            Upper Confidence Corridor
          </div>
        </div>

        <div className="bg-slate-950/80 border border-amber-800/80 p-3.5 rounded-lg shadow-inner space-y-1">
          <div className="text-[10px] text-slate-400 uppercase font-semibold">Conservative High Gas (-18%)</div>
          <div className="text-lg font-black text-amber-300">
            ${projectedMonthlyLower.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className="text-[10px] text-amber-400/80 font-bold">
            Lower Volatility Floor
          </div>
        </div>
      </div>

      {/* Recharts 30-Day Monthly Extrapolation Projection Chart */}
      <div className="bg-slate-950/90 border border-slate-800 p-3 rounded-xl h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={projectionData} margin={{ top: 15, right: 20, left: 15, bottom: 5 }}>
            <defs>
              <linearGradient id="cumulGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#10b981" stopOpacity={0.4} />
                <stop offset="95%" stopColor="#10b981" stopOpacity={0.0} />
              </linearGradient>
              <linearGradient id="upperGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#c084fc" stopOpacity={0.25} />
                <stop offset="95%" stopColor="#c084fc" stopOpacity={0.0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
            <XAxis
              dataKey="date"
              stroke="#64748b"
              fontSize={10}
              tickLine={false}
              axisLine={{ stroke: '#334155' }}
            />
            <YAxis
              stroke="#64748b"
              fontSize={10}
              tickLine={false}
              axisLine={{ stroke: '#334155' }}
              tickFormatter={(val) => `$${(val / 1000).toFixed(0)}k`}
            />
            <Tooltip
              content={({ active, payload }) => {
                if (active && payload && payload.length) {
                  const data = payload[0].payload;
                  return (
                    <div className="bg-slate-900 border border-emerald-600/80 p-3 rounded-lg text-xs font-mono shadow-2xl space-y-1.5 max-w-xs">
                      <div className="flex items-center justify-between border-b border-slate-800 pb-1">
                        <span className="font-bold text-white">{data.day} ({data.date})</span>
                        <span className="text-[10px] px-1.5 py-0.2 bg-emerald-950 text-emerald-300 border border-emerald-800 rounded">
                          30-Day Model
                        </span>
                      </div>
                      <div className="space-y-1 text-[11px] pt-1">
                        <div className="flex justify-between">
                          <span className="text-slate-400">Cumulative Net Return:</span>
                          <span className="font-bold text-emerald-400">${data.cumulativeProfit.toLocaleString()}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-slate-400">Daily Incremental Net:</span>
                          <span className="font-bold text-cyan-300">${data.dailyProfit.toLocaleString()}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-slate-400">Optimistic Upper Bound:</span>
                          <span className="font-bold text-purple-300">${data.upperBound.toLocaleString()}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-slate-400">Conservative Lower Floor:</span>
                          <span className="font-bold text-amber-400">${data.lowerBound.toLocaleString()}</span>
                        </div>
                      </div>
                    </div>
                  );
                }
                return null;
              }}
            />
            <Area
              type="monotone"
              dataKey="upperBound"
              stroke="#a855f7"
              strokeWidth={1}
              strokeDasharray="2 2"
              fillOpacity={1}
              fill="url(#upperGrad)"
              name="Optimistic (+18%)"
            />
            <Area
              type="monotone"
              dataKey="cumulativeProfit"
              stroke="#10b981"
              strokeWidth={2.5}
              fillOpacity={1}
              fill="url(#cumulGrad)"
              name="Projected Net Return ($)"
            />
            <Line
              type="monotone"
              dataKey="lowerBound"
              stroke="#f59e0b"
              strokeWidth={1.5}
              strokeDasharray="4 4"
              dot={false}
              name="Conservative (-18%)"
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
