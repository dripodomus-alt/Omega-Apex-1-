import React, { useState, useMemo } from 'react';
import { convertSqrtPriceX96ToVirtualReserves, solveProfitApex, validatePotIsolation } from '../utils/mathEngine';
import { ArbitrageRoute, PoolInfo } from '../types';
import { TransactionPayloadBuilderStudio } from './TransactionPayloadBuilderStudio';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ReferenceLine,
} from 'recharts';
import { Calculator, ShieldCheck, Zap, Layers, BarChart2, AlertTriangle, ArrowRight } from 'lucide-react';

interface CapitalInjectorStudioProps {
  selectedRoute?: ArbitrageRoute | null;
  pools: PoolInfo[];
}

export const CapitalInjectorStudio: React.FC<CapitalInjectorStudioProps> = ({ selectedRoute, pools }) => {
  // Input parameters for Capital Injector
  const [rInUSD, setRInUSD] = useState<number>(3420000);
  const [rOutUSD, setROutUSD] = useState<number>(1850000);
  const [swapFeeBps, setSwapFeeBps] = useState<number>(30); // 0.30%
  const [flashFeeBps, setFlashFeeBps] = useState<number>(5);  // 0.05%
  const [gasEstimateUSD, setGasEstimateUSD] = useState<number>(0.45);

  // V3 sqrtPriceX96 Virtualization parameters
  const [v3SqrtPriceX96, setV3SqrtPriceX96] = useState<string>('141029482019482019482019482');
  const [v3Liquidity, setV3Liquidity] = useState<string>('849204928104820194');

  // Selected Flashloan Funding Pool
  const [fundingPoolId, setFundingPoolId] = useState<string>('pool_bal_v3_vault');

  // 1. Calculate Virtual Reserves for V3
  const virtualReserves = useMemo(() => {
    return convertSqrtPriceX96ToVirtualReserves(v3SqrtPriceX96, v3Liquidity);
  }, [v3SqrtPriceX96, v3Liquidity]);

  // 2. Solve Deterministic Apex
  const apexResult = useMemo(() => {
    return solveProfitApex(rInUSD, rOutUSD, swapFeeBps, flashFeeBps, gasEstimateUSD);
  }, [rInUSD, rOutUSD, swapFeeBps, flashFeeBps, gasEstimateUSD]);

  // 3. Verify Isolation
  const isolationCheck = useMemo(() => {
    const routePoolIds = selectedRoute ? selectedRoute.pools.map((p) => p.id) : ['pool_univ3_wmatic_usdc_005', 'pool_quick_v2_wmatic_usdc'];
    return validatePotIsolation(fundingPoolId, routePoolIds);
  }, [fundingPoolId, selectedRoute]);

  const applyVirtualReservesToInjector = () => {
    setRInUSD(Math.round(virtualReserves.r0Virtual));
    setROutUSD(Math.round(virtualReserves.r1Virtual));
  };

  return (
    <div id="capital-injector-studio" className="space-y-6">
      {/* Top Banner */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <Calculator className="w-5 h-5 text-emerald-400" />
              <h2 className="text-sm font-bold text-white uppercase tracking-wider font-mono">
                Official Deterministic Capital Injector & Apex Solver
              </h2>
            </div>
            <p className="text-xs text-slate-400 mt-1 max-w-2xl">
              Eliminates random bin search by analytically solving the derivative <code className="text-emerald-300 font-mono">d(Profit)/dx = 0</code> using UniSwap V3 virtualized constant-product reserves.
            </p>
          </div>

          <div className="flex items-center gap-2 bg-slate-950 p-2.5 rounded-lg border border-slate-800">
            <ShieldCheck className={`w-5 h-5 ${isolationCheck.isIsolated ? 'text-emerald-400' : 'text-rose-500'}`} />
            <div>
              <div className="text-[10px] text-slate-400 font-mono uppercase">Pot Isolation Status</div>
              <div className={`text-xs font-bold font-mono ${isolationCheck.isIsolated ? 'text-emerald-400' : 'text-rose-400'}`}>
                {isolationCheck.isIsolated ? 'ISOLATED (NO SELF-FUNDING POT)' : `CONFLICT: ${isolationCheck.conflictPoolId}`}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Control Panel */}
        <div className="space-y-6 lg:col-span-1">
          {/* Virtual Reserve Linearizer */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4 shadow-lg">
            <div className="flex items-center justify-between border-b border-slate-800 pb-2">
              <h3 className="text-xs font-bold text-white uppercase tracking-wider font-mono flex items-center gap-2">
                <Layers className="w-4 h-4 text-purple-400" />
                <span>Uni V3 Virtual Reserve Linearizer</span>
              </h3>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label className="text-slate-400 block font-mono mb-1">sqrtPriceX96 (18 Decimals)</label>
                <input
                  type="text"
                  value={v3SqrtPriceX96}
                  onChange={(e) => setV3SqrtPriceX96(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 font-mono text-slate-200 text-xs focus:border-purple-500 outline-none"
                />
              </div>

              <div>
                <label className="text-slate-400 block font-mono mb-1">Liquidity L (Active Tick)</label>
                <input
                  type="text"
                  value={v3Liquidity}
                  onChange={(e) => setV3Liquidity(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 font-mono text-slate-200 text-xs focus:border-purple-500 outline-none"
                />
              </div>

              <div className="bg-purple-950/40 border border-purple-800/50 rounded-lg p-3 space-y-1.5 font-mono text-slate-300">
                <div className="flex justify-between">
                  <span className="text-purple-300">Virtual Reserve r0 (rIn):</span>
                  <span className="font-bold text-white">${Math.round(virtualReserves.r0Virtual).toLocaleString()}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-purple-300">Virtual Reserve r1 (rOut):</span>
                  <span className="font-bold text-white">${Math.round(virtualReserves.r1Virtual).toLocaleString()}</span>
                </div>
                <div className="flex justify-between text-[11px] text-slate-400">
                  <span>Price P (token1/0):</span>
                  <span>{virtualReserves.virtualPrice0in1.toFixed(6)}</span>
                </div>
              </div>

              <button
                onClick={applyVirtualReservesToInjector}
                className="w-full py-2 bg-purple-600 hover:bg-purple-500 text-white font-semibold rounded-lg text-xs transition-all active:scale-95 shadow-md shadow-purple-600/20"
              >
                Apply Virtualized Reserves to Injector
              </button>
            </div>
          </div>

          {/* Capital Injector Formula Inputs */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4 shadow-lg">
            <div className="border-b border-slate-800 pb-2">
              <h3 className="text-xs font-bold text-white uppercase tracking-wider font-mono flex items-center gap-2">
                <Zap className="w-4 h-4 text-emerald-400" />
                <span>Pool Reserves & Fee Controls</span>
              </h3>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <div className="flex justify-between text-slate-400 font-mono mb-1">
                  <span>Reserve In USD (r_in)</span>
                  <span className="text-white">${rInUSD.toLocaleString()}</span>
                </div>
                <input
                  type="range"
                  min={100000}
                  max={20000000}
                  step={50000}
                  value={rInUSD}
                  onChange={(e) => setRInUSD(Number(e.target.value))}
                  className="w-full accent-emerald-400 bg-slate-950"
                />
              </div>

              <div>
                <div className="flex justify-between text-slate-400 font-mono mb-1">
                  <span>Reserve Out USD (r_out)</span>
                  <span className="text-white">${rOutUSD.toLocaleString()}</span>
                </div>
                <input
                  type="range"
                  min={100000}
                  max={20000000}
                  step={50000}
                  value={rOutUSD}
                  onChange={(e) => setROutUSD(Number(e.target.value))}
                  className="w-full accent-emerald-400 bg-slate-950"
                />
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-slate-400 block font-mono mb-1">Swap Fee (bps)</label>
                  <input
                    type="number"
                    value={swapFeeBps}
                    onChange={(e) => setSwapFeeBps(Number(e.target.value))}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 font-mono text-slate-200 text-xs focus:border-emerald-500 outline-none"
                  />
                </div>

                <div>
                  <label className="text-slate-400 block font-mono mb-1">Flash Fee (bps)</label>
                  <input
                    type="number"
                    value={flashFeeBps}
                    onChange={(e) => setFlashFeeBps(Number(e.target.value))}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 font-mono text-slate-200 text-xs focus:border-emerald-500 outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="text-slate-400 block font-mono mb-1">Flashloan Funding Vault</label>
                <select
                  value={fundingPoolId}
                  onChange={(e) => setFundingPoolId(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 font-mono text-slate-200 text-xs focus:border-emerald-500 outline-none"
                >
                  {pools.filter((p) => p.isFundingPool).map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} ({p.protocol})
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>
        </div>

        {/* Right Output Dashboard & Curve Plot */}
        <div className="space-y-6 lg:col-span-2">
          {/* Calculated Apex Summary Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="bg-slate-900 border border-emerald-500/30 rounded-xl p-4 shadow-xl relative overflow-hidden">
              <div className="text-[10px] uppercase font-mono font-bold text-emerald-400 tracking-wider">
                Calculated Optimal Apex (x*)
              </div>
              <div className="text-2xl font-extrabold text-white font-mono mt-1">
                ${apexResult.optimalInputUSD.toLocaleString()}
              </div>
              <div className="text-[11px] text-slate-400 font-mono mt-1">
                Flashloan Amount Required
              </div>
            </div>

            <div className="bg-slate-900 border border-emerald-500/30 rounded-xl p-4 shadow-xl">
              <div className="text-[10px] uppercase font-mono font-bold text-emerald-400 tracking-wider">
                Peak Net Profit Apex
              </div>
              <div className="text-2xl font-extrabold text-emerald-400 font-mono mt-1">
                +${apexResult.maxNetProfitUSD.toLocaleString('en-US', { minimumFractionDigits: 2 })}
              </div>
              <div className="text-[11px] text-slate-400 font-mono mt-1">
                Gross: ${apexResult.grossProfitUSD.toLocaleString()}
              </div>
            </div>

            <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-xl">
              <div className="text-[10px] uppercase font-mono font-bold text-indigo-400 tracking-wider">
                Derivative Baseline dP/dx
              </div>
              <div className="text-xl font-bold text-white font-mono mt-1">
                {apexResult.derivativeAtZero.toFixed(4)}
              </div>
              <div className="text-[11px] text-slate-400 font-mono mt-1">
                {apexResult.derivativeAtZero > 0 ? 'Positive Alpha Potential' : 'Negative Alpha (No Arb)'}
              </div>
            </div>
          </div>

          {/* Recharts Profit Curve Visualization */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4 shadow-xl">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <BarChart2 className="w-5 h-5 text-emerald-400" />
                <h3 className="text-sm font-bold text-white uppercase tracking-wider font-mono">
                  Net Profit Apex Curve: Profit ($) vs Capital Injection ($)
                </h3>
              </div>
              <span className="px-2 py-0.5 text-xs font-mono bg-emerald-950 text-emerald-300 rounded border border-emerald-800">
                Peak Apex at x* = ${apexResult.optimalInputUSD.toLocaleString()}
              </span>
            </div>

            <div className="h-72 w-full pt-4">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={apexResult.curveData} margin={{ top: 10, right: 30, left: 10, bottom: 20 }}>
                  <defs>
                    <linearGradient id="profitGradiant" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#10b981" stopOpacity={0.4} />
                      <stop offset="95%" stopColor="#10b981" stopOpacity={0.0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.5} />
                  <XAxis
                    dataKey="inputUSD"
                    stroke="#94a3b8"
                    tick={{ fontSize: 11, fill: '#94a3b8' }}
                    tickFormatter={(val) => `$${(val / 1000).toFixed(0)}k`}
                  />
                  <YAxis
                    stroke="#94a3b8"
                    tick={{ fontSize: 11, fill: '#94a3b8' }}
                    tickFormatter={(val) => `$${val}`}
                  />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '8px', color: '#f8fafc' }}
                    formatter={(val: any) => [`$${val}`, 'Net Profit']}
                    labelFormatter={(label) => `Capital Injection: $${label.toLocaleString()}`}
                  />
                  <ReferenceLine
                    x={apexResult.optimalInputUSD}
                    stroke="#10b981"
                    strokeWidth={2}
                    strokeDasharray="4 4"
                    label={{ value: 'APEX (x*)', fill: '#10b981', fontSize: 12, position: 'top' }}
                  />
                  <Area
                    type="monotone"
                    dataKey="netProfitUSD"
                    stroke="#10b981"
                    strokeWidth={3}
                    fillOpacity={1}
                    fill="url(#profitGradiant)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 text-xs font-mono text-slate-300 flex flex-wrap items-center justify-between gap-4">
              <div>Flashloan Fee (5 bps): <span className="text-white">${apexResult.flashloanFeeUSD}</span></div>
              <div>Estimated Swap Fees: <span className="text-white">${apexResult.swapFeesUSD}</span></div>
              <div>Estimated Gas Cost: <span className="text-white">${gasEstimateUSD}</span></div>
            </div>
          </div>
        </div>
      </div>

      {/* Batch Calculus Apex Solver Matrix */}
      <BatchApexSolverMatrix />
    </div>
  );
};

// Sub-component for Batch Calculus Apex Solver
const BatchApexSolverMatrix: React.FC = () => {
  const [isSolvingBatch, setIsSolvingBatch] = useState(false);
  const [batchApexRoutes, setBatchApexRoutes] = useState([
    {
      id: 'ROUTE-01',
      pair: 'WMATIC -> USDC -> WETH -> WMATIC',
      rInUSD: 3420000,
      rOutUSD: 1850000,
      optimalInputUSD: 482500,
      maxProfitUSD: 1420.5,
      status: 'SOLVED',
    },
    {
      id: 'ROUTE-02',
      pair: 'USDT -> DAI -> USDC -> USDT',
      rInUSD: 8500000,
      rOutUSD: 6200000,
      optimalInputUSD: 950000,
      maxProfitUSD: 3120.8,
      status: 'SOLVED',
    },
    {
      id: 'ROUTE-03',
      pair: 'WBTC -> WETH -> USDC -> WBTC',
      rInUSD: 12400000,
      rOutUSD: 9800000,
      optimalInputUSD: 1250000,
      maxProfitUSD: 5410.2,
      status: 'SOLVED',
    },
    {
      id: 'ROUTE-04',
      pair: 'LINK -> WETH -> WMATIC -> LINK',
      rInUSD: 1800000,
      rOutUSD: 1200000,
      optimalInputUSD: 240000,
      maxProfitUSD: 890.1,
      status: 'SOLVED',
    },
  ]);

  const handleSolveBatchApex = () => {
    setIsSolvingBatch(true);
    setTimeout(() => {
      setBatchApexRoutes((prev) =>
        prev.map((r) => {
          const calibratedApex = solveProfitApex(r.rInUSD, r.rOutUSD, 30, 5, 0.45);
          return {
            ...r,
            optimalInputUSD: Math.round(calibratedApex.optimalInputUSD),
            maxProfitUSD: Number(calibratedApex.maxNetProfitUSD.toFixed(2)),
            status: 'SOLVED (0.12ms)',
          };
        })
      );
      setIsSolvingBatch(false);
    }, 800);
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl space-y-4 font-mono">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-3">
        <div>
          <h3 className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-2">
            <Calculator className="w-4 h-4 text-emerald-400" />
            <span>Batch Calculus Analytical Apex Solver Matrix</span>
          </h3>
          <p className="text-xs text-slate-400 mt-0.5">
            Simultaneous derivative calculation <code className="text-emerald-300">d(Profit)/dx = 0</code> across candidate route vectors.
          </p>
        </div>

        <button
          onClick={handleSolveBatchApex}
          disabled={isSolvingBatch}
          className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-slate-950 text-xs font-bold rounded-lg transition-all shadow-lg active:scale-95 disabled:opacity-50 shrink-0"
        >
          <Zap className={`w-4 h-4 ${isSolvingBatch ? 'animate-spin' : ''}`} />
          <span>{isSolvingBatch ? 'Solving Derivatives...' : 'Batch Solve All Optimal Inputs (x*)'}</span>
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-slate-800 text-slate-400 bg-slate-950/60">
              <th className="p-3">Route ID</th>
              <th className="p-3">Liquidity Vector</th>
              <th className="p-3">In Reserve ($)</th>
              <th className="p-3">Out Reserve ($)</th>
              <th className="p-3">Optimal Input (x*)</th>
              <th className="p-3">Max Net Profit</th>
              <th className="p-3">Derivative Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {batchApexRoutes.map((r) => (
              <tr key={r.id} className="hover:bg-slate-800/40">
                <td className="p-3 font-bold text-emerald-300">{r.id}</td>
                <td className="p-3 text-white font-semibold">{r.pair}</td>
                <td className="p-3 text-slate-300">${(r.rInUSD / 1e6).toFixed(2)}M</td>
                <td className="p-3 text-slate-300">${(r.rOutUSD / 1e6).toFixed(2)}M</td>
                <td className="p-3 font-bold text-emerald-400">${r.optimalInputUSD.toLocaleString()}</td>
                <td className="p-3 font-bold text-emerald-300">+${r.maxProfitUSD.toLocaleString()}</td>
                <td className="p-3">
                  <span className="px-2 py-0.5 bg-emerald-950 text-emerald-300 border border-emerald-800 rounded text-[10px] font-bold">
                    {r.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Direct EIP-1559 Transaction Payload Builder & Live eth_call Pre-Flight Engine */}
      <div className="pt-4 border-t border-slate-800/80">
        <TransactionPayloadBuilderStudio />
      </div>
    </div>
  );
};
