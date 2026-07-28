import React, { useState } from 'react';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
} from 'recharts';
import { TrendingUp, BarChart3, Filter, Sparkles, Zap, Layers, DollarSign } from 'lucide-react';
import { ArbitrageRoute } from '../types';

interface RouteProfitTrendChartProps {
  routes: ArbitrageRoute[];
  onSelectRoute?: (route: ArbitrageRoute) => void;
  selectedRouteIds?: Set<string>;
}

export const RouteProfitTrendChart: React.FC<RouteProfitTrendChartProps> = ({
  routes,
  onSelectRoute,
  selectedRouteIds,
}) => {
  const [sortMode, setSortMode] = useState<'PROFIT_CURVE' | 'SEQUENCE'>('PROFIT_CURVE');
  const [thresholdFilter, setThresholdFilter] = useState<number>(500);

  if (!routes || routes.length === 0) {
    return (
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 text-center text-slate-500 font-mono text-xs">
        No routes discovered to plot profit distribution trend.
      </div>
    );
  }

  // Sort routes according to view mode
  const processedRoutes = [...routes].sort((a, b) => {
    if (sortMode === 'PROFIT_CURVE') {
      return a.netProfitUSD - b.netProfitUSD;
    }
    return 0; // Maintain original array sequence
  });

  const chartData = processedRoutes.map((route, idx) => ({
    index: idx + 1,
    id: route.id,
    netProfit: Number(route.netProfitUSD.toFixed(2)),
    grossProfit: Number(route.grossProfitUSD.toFixed(2)),
    gasCost: Number(route.estimatedGasUSD.toFixed(2)),
    vqcScore: Number((route.vqcAlphaScore * 100).toFixed(1)),
    path: route.pathString,
    stage: route.stage,
    isHighYield: route.netProfitUSD >= thresholdFilter,
    route,
  }));

  // Cluster calculations
  const totalNetProfit = routes.reduce((sum, r) => sum + r.netProfitUSD, 0);
  const avgNetProfit = totalNetProfit / routes.length;
  const maxNetProfit = Math.max(...routes.map((r) => r.netProfitUSD));
  const highYieldCluster = routes.filter((r) => r.netProfitUSD >= thresholdFilter);
  const highYieldRatio = ((highYieldCluster.length / routes.length) * 100).toFixed(0);

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl font-mono space-y-4">
      {/* Header & Controls */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 border-b border-slate-800 pb-3">
        <div>
          <div className="flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-emerald-400" />
            <h3 className="text-xs font-bold text-white uppercase tracking-wider">
              Discovered Route Net Profit ($) Cluster Distribution Trend
            </h3>
            <span className="px-2 py-0.5 bg-emerald-950 text-emerald-300 border border-emerald-800 rounded text-[9px] font-bold">
              Recharts Analytics Engine
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Identify arbitrage density curves and high-yield clusters across all {routes.length} candidate paths.
          </p>
        </div>

        {/* View Mode & Threshold Control */}
        <div className="flex items-center gap-2 flex-wrap shrink-0">
          <div className="bg-slate-950 border border-slate-800 p-1 rounded-lg flex items-center gap-1">
            <button
              onClick={() => setSortMode('PROFIT_CURVE')}
              className={`px-2.5 py-1 text-xs font-bold rounded transition-all ${
                sortMode === 'PROFIT_CURVE'
                  ? 'bg-emerald-950 text-emerald-300 border border-emerald-800 shadow'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              Yield Curve (Asc)
            </button>
            <button
              onClick={() => setSortMode('SEQUENCE')}
              className={`px-2.5 py-1 text-xs font-bold rounded transition-all ${
                sortMode === 'SEQUENCE'
                  ? 'bg-emerald-950 text-emerald-300 border border-emerald-800 shadow'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              Scan Order
            </button>
          </div>

          <div className="flex items-center gap-1 bg-slate-950 border border-slate-800 px-2.5 py-1 rounded-lg text-xs">
            <Filter className="w-3.5 h-3.5 text-amber-400" />
            <span className="text-slate-400">Cluster Threshold:</span>
            <span className="text-amber-400 font-bold">${thresholdFilter}</span>
          </div>
        </div>
      </div>

      {/* Cluster Metrics Quick Stats Bar */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="bg-slate-950/80 border border-slate-800 p-3 rounded-lg shadow-inner">
          <div className="text-[10px] text-slate-500 uppercase font-semibold">Total Pipeline Yield</div>
          <div className="text-base font-black text-emerald-400 mt-0.5">
            ${totalNetProfit.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
        </div>

        <div className="bg-slate-950/80 border border-slate-800 p-3 rounded-lg shadow-inner">
          <div className="text-[10px] text-slate-500 uppercase font-semibold">Peak Route Profit</div>
          <div className="text-base font-black text-cyan-300 mt-0.5">
            ${maxNetProfit.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
        </div>

        <div className="bg-slate-950/80 border border-slate-800 p-3 rounded-lg shadow-inner">
          <div className="text-[10px] text-slate-500 uppercase font-semibold">Mean Net Yield / Route</div>
          <div className="text-base font-black text-slate-200 mt-0.5">
            ${avgNetProfit.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
        </div>

        <div className="bg-slate-950/80 border border-slate-800 p-3 rounded-lg shadow-inner">
          <div className="text-[10px] text-slate-500 uppercase font-semibold">
            High-Yield Cluster Density (&ge;${thresholdFilter})
          </div>
          <div className="text-base font-black text-amber-400 mt-0.5 flex items-center gap-1.5">
            <span>{highYieldCluster.length} Routes</span>
            <span className="text-xs font-normal text-amber-300/80">({highYieldRatio}%)</span>
          </div>
        </div>
      </div>

      {/* Recharts Area Trend Line Chart */}
      <div className="bg-slate-950/90 border border-slate-800/80 p-3 rounded-xl h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 15, right: 20, left: 10, bottom: 5 }}>
            <defs>
              <linearGradient id="profitGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#10b981" stopOpacity={0.4} />
                <stop offset="95%" stopColor="#10b981" stopOpacity={0.0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
            <XAxis
              dataKey="id"
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
              tickFormatter={(val) => `$${val}`}
            />
            <Tooltip
              content={({ active, payload }) => {
                if (active && payload && payload.length) {
                  const data = payload[0].payload;
                  return (
                    <div className="bg-slate-900 border border-emerald-600/80 p-3 rounded-lg text-xs font-mono shadow-2xl space-y-1.5 max-w-xs">
                      <div className="flex items-center justify-between border-b border-slate-800 pb-1">
                        <span className="font-bold text-emerald-300">{data.id}</span>
                        <span className="text-[10px] px-1.5 py-0.2 bg-slate-800 text-slate-300 rounded">
                          {data.stage}
                        </span>
                      </div>
                      <div className="text-[11px] text-slate-300 font-semibold truncate">{data.path}</div>
                      <div className="grid grid-cols-2 gap-2 text-[10px] pt-1">
                        <div>
                          <span className="text-slate-500">Net Profit:</span>
                          <div className="font-bold text-emerald-400">${data.netProfit.toLocaleString()}</div>
                        </div>
                        <div>
                          <span className="text-slate-500">Gross Yield:</span>
                          <div className="font-bold text-slate-200">${data.grossProfit.toLocaleString()}</div>
                        </div>
                        <div>
                          <span className="text-slate-500">Gas Overhead:</span>
                          <div className="font-bold text-amber-400">${data.gasCost}</div>
                        </div>
                        <div>
                          <span className="text-slate-500">VQC Win Score:</span>
                          <div className="font-bold text-purple-300">{data.vqcScore}%</div>
                        </div>
                      </div>
                    </div>
                  );
                }
                return null;
              }}
            />
            <ReferenceLine
              y={avgNetProfit}
              stroke="#94a3b8"
              strokeDasharray="4 4"
              label={{
                value: `Mean ($${avgNetProfit.toFixed(0)})`,
                fill: '#94a3b8',
                fontSize: 10,
                position: 'insideTopLeft',
              }}
            />
            <ReferenceLine
              y={thresholdFilter}
              stroke="#f59e0b"
              strokeDasharray="3 3"
              label={{
                value: `High Yield ($${thresholdFilter})`,
                fill: '#f59e0b',
                fontSize: 10,
                position: 'insideBottomRight',
              }}
            />
            <Area
              type="monotone"
              dataKey="netProfit"
              stroke="#10b981"
              strokeWidth={2.5}
              fillOpacity={1}
              fill="url(#profitGrad)"
              activeDot={{
                r: 6,
                fill: '#34d399',
                stroke: '#064e3b',
                strokeWidth: 2,
                onClick: (_, event: any) => {
                  if (event && event.payload && onSelectRoute) {
                    onSelectRoute(event.payload.route);
                  }
                },
              }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
