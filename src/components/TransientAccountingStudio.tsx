import React, { useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Hash,
  Lock,
  ShieldCheck,
  Unlock,
  XCircle,
  Zap,
  Activity,
  Database,
  BarChart2,
} from 'lucide-react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { ArbitrageRoute, ExecutionType, TransientLeg, TransientLegPhase } from '../types';
import { computeLegLedger } from '../utils/transientAccounting';
import { TRANSIENT_EPSILON_USD_MAX } from '../config/chainConfig';

interface TransientAccountingStudioProps {
  routes: ArbitrageRoute[];
}

// ── Helpers ─────────────────────────────────────────────────────────────────

const PHASE_LABELS: Record<TransientLegPhase, string> = {
  BALANCER_VAULT_UNLOCK: 'Balancer Vault UNLOCK',
  SWAP: 'AMM Swap',
  AAVE_LIQUIDATION: 'Aave Liquidation',
  BALANCER_VAULT_SETTLE: 'Balancer Vault SETTLE',
};

const PHASE_COLORS: Record<TransientLegPhase, string> = {
  BALANCER_VAULT_UNLOCK: 'text-purple-300 bg-purple-950 border-purple-800',
  SWAP: 'text-cyan-300 bg-cyan-950 border-cyan-800',
  AAVE_LIQUIDATION: 'text-rose-300 bg-rose-950 border-rose-800',
  BALANCER_VAULT_SETTLE: 'text-emerald-300 bg-emerald-950 border-emerald-800',
};

const EXEC_TYPE_LABELS: Record<ExecutionType, string> = {
  C1_ARBITRAGE: 'C1 — Forward Arbitrage',
  C2_ARBITRAGE: 'C2 — Reverse/Mirror Arbitrage',
  LIQUIDATION: 'Aave V3 Liquidation',
};

const EXEC_TYPE_COLORS: Record<ExecutionType, string> = {
  C1_ARBITRAGE: 'text-emerald-300 bg-emerald-950 border-emerald-700',
  C2_ARBITRAGE: 'text-cyan-300 bg-cyan-950 border-cyan-700',
  LIQUIDATION: 'text-rose-300 bg-rose-950 border-rose-700',
};

// ── Formatting helpers ────────────────────────────────────────────────────────

/** Formats a USD value to 2 decimal places with locale-aware thousands separator. */
const fmtUSD = (v: number) => `$${v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
/** Formats a USD fee or cost to 4 significant decimal places. */
const fmtFee = (v: number) => `$${v.toFixed(4)}`;
/** Formats a per-leg residual ε to 6 decimal places. */
const fmtResidual = (v: number) => `$${v.toFixed(6)}`;

/** Number of columns in the per-leg trace table. Update here if columns change. */
const TRACE_TABLE_COLS = 10;

// ── Component ────────────────────────────────────────────────────────────────

export const TransientAccountingStudio: React.FC<TransientAccountingStudioProps> = ({
  routes,
}) => {
  const [selectedRouteId, setSelectedRouteId] = useState<string>(routes[0]?.id ?? '');
  const [expandedLegIndex, setExpandedLegIndex] = useState<number | null>(null);

  const handleRouteSelect = (routeId: string) => {
    setSelectedRouteId(routeId);
    setExpandedLegIndex(null);
  };

  const selectedRoute = routes.find((r) => r.id === selectedRouteId) ?? routes[0];

  // Compute or reuse existing trace
  const trace = selectedRoute
    ? selectedRoute.transientTrace ?? computeLegLedger(selectedRoute)
    : null;

  const allLegsPass = trace ? trace.legs.every((l) => l.passed) : false;
  const failingLegs = trace ? trace.legs.filter((l) => !l.passed) : [];
  const maxResidual = trace
    ? Math.max(...trace.legs.map((l) => l.residualUSD))
    : 0;

  // Build Recharts timeline data (skip UNLOCK phase at index 0)
  const chartData = trace
    ? trace.legs.map((leg, idx) => ({
        name: `L${idx}`,
        phase: PHASE_LABELS[leg.phase],
        B: Number(leg.amountOut.toFixed(4)),
        D: Number(trace.debtWithFee.toFixed(4)),
        F: Number(leg.feeUSD.toFixed(4)),
        residual: Number(leg.residualUSD.toFixed(6)),
      }))
    : [];

  return (
    <div id="transient-accounting-studio" className="space-y-6 font-mono">
      {/* Header */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <Database className="w-5 h-5 text-purple-400" />
              <h2 className="text-sm font-bold text-white uppercase tracking-wider">
                EIP-1153 Transient Accounting Studio
              </h2>
            </div>
            <p className="text-xs text-slate-400 mt-1 max-w-2xl font-sans">
              Off-chain simulation of the EIP-1153 transient storage ledger — Balancer Vault
              UNLOCK → swap/liquidation legs → SETTLE — with per-leg conservation checks and
              integrity hash commitment. Validates C1, C2, and Liquidation routes.
            </p>
          </div>

          <div className="flex items-center gap-3 shrink-0">
            <div className="flex items-center gap-1.5 text-xs text-slate-400">
              <span>ε_allowed:</span>
              <span className="text-amber-300 font-bold">${TRANSIENT_EPSILON_USD_MAX.toFixed(2)} USD</span>
            </div>
            {trace && (
              <span
                className={`px-2.5 py-1 rounded text-xs font-bold border flex items-center gap-1 ${
                  allLegsPass
                    ? 'bg-emerald-950 text-emerald-300 border-emerald-800'
                    : 'bg-rose-950 text-rose-300 border-rose-800'
                }`}
              >
                {allLegsPass ? (
                  <><ShieldCheck className="w-3.5 h-3.5" /> ALL LEGS VERIFIED</>
                ) : (
                  <><XCircle className="w-3.5 h-3.5" /> {failingLegs.length} MISMATCH(ES)</>
                )}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Route Selector */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-xl space-y-3">
        <label className="text-[11px] text-slate-400 font-bold uppercase block">
          Select Route for Transient Trace Analysis:
        </label>
        <select
          value={selectedRouteId}
          onChange={(e) => handleRouteSelect(e.target.value)}
          className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white font-mono focus:outline-none focus:border-purple-500"
        >
          {routes.map((r) => (
            <option key={r.id} value={r.id}>
              [{r.executionType ?? 'C1_ARBITRAGE'}] {r.id} — {r.pathString.slice(0, 60)}…
            </option>
          ))}
        </select>

        {trace && selectedRoute && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-1 text-xs">
            <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 space-y-1">
              <div className="text-[10px] text-slate-400 uppercase font-bold">Execution Type</div>
              <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${EXEC_TYPE_COLORS[trace.executionType]}`}>
                {EXEC_TYPE_LABELS[trace.executionType]}
              </span>
            </div>
            <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 space-y-1">
              <div className="text-[10px] text-slate-400 uppercase font-bold">Borrowed (D₀)</div>
              <div className="text-emerald-400 font-bold">${trace.borrowedAmount.toLocaleString()} {trace.borrowedToken}</div>
              <div className="text-[10px] text-slate-500">Balancer Vault (0% fee)</div>
            </div>
            <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 space-y-1">
              <div className="text-[10px] text-slate-400 uppercase font-bold">Max |ε_j|</div>
              <div className={`font-bold ${maxResidual <= TRANSIENT_EPSILON_USD_MAX ? 'text-emerald-400' : 'text-rose-400'}`}>
                ${maxResidual.toFixed(6)}
              </div>
              <div className="text-[10px] text-slate-500">Limit: ${TRANSIENT_EPSILON_USD_MAX}</div>
            </div>
            <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 space-y-1">
              <div className="text-[10px] text-slate-400 uppercase font-bold">Final SETTLE</div>
              <div className={`font-bold flex items-center gap-1 ${trace.finalRepaymentPassed ? 'text-emerald-400' : 'text-rose-400'}`}>
                {trace.finalRepaymentPassed
                  ? <><CheckCircle2 className="w-3.5 h-3.5" /> PASSED</>
                  : <><XCircle className="w-3.5 h-3.5" /> FAILED</>}
              </div>
              <div className="text-[10px] text-slate-500">D₀ repayment verified</div>
            </div>
          </div>
        )}
      </div>

      {trace && (
        <>
          {/* Accounting Mismatch Alert */}
          {!allLegsPass && (
            <div className="bg-rose-950/80 border border-rose-700 rounded-xl p-4 flex items-start gap-3 text-xs text-rose-200 animate-fadeIn">
              <AlertTriangle className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
              <div>
                <div className="font-black text-rose-300 mb-1">TRANSIENT_LEG_ACCOUNTING_MISMATCH</div>
                <div className="font-sans">
                  {failingLegs.length} leg(s) exceed the ε_allowed threshold of ${TRANSIENT_EPSILON_USD_MAX.toFixed(2)} USD.
                  Legs: {failingLegs.map((l) => `L${l.legIndex}`).join(', ')}.
                  In the on-chain contract this would trigger a revert.
                  Re-verify pool reserves and input sizing.
                </div>
              </div>
            </div>
          )}

          {/* B_j / D_j / F_j Timeline Chart */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl space-y-3">
            <div className="flex items-center gap-2 text-xs font-bold text-white uppercase tracking-wider">
              <BarChart2 className="w-4 h-4 text-purple-400" />
              <span>Transient Inventory B_j · Debt D_j · Fee F_j Timeline</span>
            </div>
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 10 }} />
                <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} tickFormatter={(v) => `$${v.toLocaleString()}`} />
                <Tooltip
                  contentStyle={{ background: '#0f172a', border: '1px solid #334155', fontSize: 11 }}
                  formatter={(value: number, name: string) => [`$${value.toLocaleString()}`, name]}
                />
                <ReferenceLine y={trace.debtWithFee} stroke="#f59e0b" strokeDasharray="4 2" label={{ value: 'D₀', fill: '#f59e0b', fontSize: 10 }} />
                <Line type="monotone" dataKey="B" stroke="#10b981" strokeWidth={2} dot={{ r: 3 }} name="B_j (Inventory)" />
                <Line type="monotone" dataKey="D" stroke="#f59e0b" strokeWidth={1.5} strokeDasharray="4 2" dot={false} name="D_j (Debt)" />
                <Line type="monotone" dataKey="F" stroke="#818cf8" strokeWidth={1.5} dot={{ r: 2 }} name="F_j (Fee)" />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Per-Leg Table */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl space-y-3">
            <div className="flex items-center gap-2 text-xs font-bold text-white uppercase tracking-wider">
              <Activity className="w-4 h-4 text-cyan-400" />
              <span>Per-Leg Accounting Trace</span>
              <span className="text-slate-500 font-normal normal-case">({trace.legs.length} phases)</span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-400 bg-slate-950/60">
                    <th className="p-3">Leg</th>
                    <th className="p-3">Phase</th>
                    <th className="p-3">Pool Role</th>
                    <th className="p-3">Token In → Out</th>
                    <th className="p-3">Amount In</th>
                    <th className="p-3">Amount Out</th>
                    <th className="p-3">Fee USD</th>
                    <th className="p-3">|ε_j|</th>
                    <th className="p-3">Status</th>
                    <th className="p-3">Details</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {trace.legs.map((leg) => (
                    <React.Fragment key={leg.legIndex}>
                      <tr className={`hover:bg-slate-800/30 transition-colors ${!leg.passed ? 'bg-rose-950/20' : ''}`}>
                        <td className="p-3 font-bold text-slate-300">L{leg.legIndex}</td>
                        <td className="p-3">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${PHASE_COLORS[leg.phase]}`}>
                            {PHASE_LABELS[leg.phase]}
                          </span>
                        </td>
                        <td className="p-3 text-slate-400 text-[11px]">{leg.poolCategory}</td>
                        <td className="p-3 text-white font-semibold">
                          {leg.tokenIn} → {leg.tokenOut}
                        </td>
                        <td className="p-3 text-slate-300">{fmtUSD(leg.amountIn)}</td>
                        <td className="p-3 text-emerald-400 font-bold">{fmtUSD(leg.amountOut)}</td>
                        <td className="p-3 text-slate-400">{fmtFee(leg.feeUSD)}</td>
                        <td className={`p-3 font-bold ${leg.residualUSD <= TRANSIENT_EPSILON_USD_MAX ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {fmtResidual(leg.residualUSD)}
                        </td>
                        <td className="p-3">
                          {leg.passed ? (
                            <span className="flex items-center gap-1 text-emerald-400 font-bold text-[10px]">
                              <CheckCircle2 className="w-3.5 h-3.5" /> PASS
                            </span>
                          ) : (
                            <span className="flex items-center gap-1 text-rose-400 font-bold text-[10px]">
                              <XCircle className="w-3.5 h-3.5" /> FAIL
                            </span>
                          )}
                        </td>
                        <td className="p-3">
                          <button
                            onClick={() => setExpandedLegIndex(expandedLegIndex === leg.legIndex ? null : leg.legIndex)}
                            className="text-slate-400 hover:text-white transition-colors"
                          >
                            {expandedLegIndex === leg.legIndex
                              ? <ChevronUp className="w-4 h-4" />
                              : <ChevronDown className="w-4 h-4" />}
                          </button>
                        </td>
                      </tr>

                      {/* Expanded reserve breakdown */}
                      {expandedLegIndex === leg.legIndex && (
                        <tr key={`detail-${leg.legIndex}`}>
                          <td colSpan={TRACE_TABLE_COLS} className="p-0">
                            <div className="bg-slate-950 border-t border-slate-800 p-4 grid grid-cols-2 sm:grid-cols-5 gap-3 text-xs">
                              {[
                                { label: 'Gas Reserve (G_j)', value: leg.gasReserveUSD, color: 'text-amber-300' },
                                { label: 'Builder Tip (T_j)', value: leg.tipUSD, color: 'text-purple-300' },
                                { label: 'Risk Reserve (R_j)', value: leg.riskReserveUSD, color: 'text-rose-300' },
                                { label: 'Model Reserve (M_j)', value: leg.modelReserveUSD, color: 'text-indigo-300' },
                                { label: 'Protocol (F_j)', value: leg.feeUSD, color: 'text-cyan-300' },
                              ].map((item) => (
                                <div key={item.label} className="bg-slate-900 p-2.5 rounded-lg border border-slate-800 space-y-1">
                                  <div className="text-[10px] text-slate-400 uppercase font-bold">{item.label}</div>
                                  <div className={`font-bold ${item.color}`}>${item.value.toFixed(6)}</div>
                                </div>
                              ))}
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Integrity Hash & Debt Repayment Summary */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Integrity Hash */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-xl space-y-3">
              <div className="flex items-center gap-2 text-xs font-bold text-white uppercase">
                <Hash className="w-4 h-4 text-indigo-400" />
                <span>Route Integrity Hash (H_j)</span>
              </div>
              <div className="bg-slate-950 p-3 rounded-lg border border-indigo-800/60 space-y-1">
                <div className="text-[10px] text-slate-400 font-bold uppercase">TSTORE(INTEGRITY_SLOT, H_j)</div>
                <code className="text-indigo-300 text-[11px] break-all">{trace.integrityHash}</code>
              </div>
              <p className="text-[11px] text-slate-400 font-sans">
                Deterministic commitment over routeId, pool addresses, feeBps, and amounts.
                Written to transient slot H_j before each leg and verified by the contract.
              </p>
            </div>

            {/* Debt Repayment Summary */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-xl space-y-3">
              <div className="flex items-center gap-2 text-xs font-bold text-white uppercase">
                {trace.finalRepaymentPassed
                  ? <Lock className="w-4 h-4 text-emerald-400" />
                  : <Unlock className="w-4 h-4 text-rose-400" />}
                <span>Balancer Vault SETTLE — Debt Repayment</span>
              </div>
              <div className="space-y-2 text-xs">
                {[
                  { label: 'D₀ (Debt to Repay)', value: `$${trace.debtWithFee.toLocaleString()}`, color: 'text-amber-300' },
                  { label: 'Flash Fee Rate', value: '0.00% (Balancer Vault)', color: 'text-slate-300' },
                  { label: 'Final Inventory (B_final)', value: `$${(trace.legs[trace.legs.length - 1]?.amountIn ?? 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}`, color: 'text-emerald-300' },
                  { label: 'Net Profit Released', value: `$${(trace.legs[trace.legs.length - 1]?.amountOut ?? 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}`, color: 'text-emerald-400' },
                ].map((row) => (
                  <div key={row.label} className="flex justify-between items-center border-b border-slate-800/60 pb-1">
                    <span className="text-slate-400">{row.label}:</span>
                    <span className={`font-bold ${row.color}`}>{row.value}</span>
                  </div>
                ))}
                <div className="pt-1">
                  {trace.finalRepaymentPassed ? (
                    <div className="flex items-center gap-2 text-emerald-400 font-bold">
                      <CheckCircle2 className="w-4 h-4" />
                      <span>SETTLE PASSED — D₀ fully repaid to Balancer Vault</span>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2 text-rose-400 font-bold">
                      <XCircle className="w-4 h-4" />
                      <span>SETTLE FAILED — insufficient balance to repay D₀</span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Pool Role Legend */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-xl">
            <div className="flex items-center gap-2 text-xs font-bold text-white uppercase mb-3">
              <Zap className="w-4 h-4 text-yellow-400" />
              <span>Pool Role Awareness — Route Leg Classification</span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs font-sans">
              {[
                {
                  role: 'FUNDING_FLASHLOAN',
                  label: 'Balancer Vault (UNLOCK / SETTLE)',
                  description: 'Dual V2/V3-compatible vault. Opens D₀ at UNLOCK; verifies repayment at SETTLE. Zero flash fee on Polygon.',
                  color: 'border-purple-800/60 bg-purple-950/20',
                  icon: <Unlock className="w-3.5 h-3.5 text-purple-400" />,
                },
                {
                  role: 'SWAPPABLE_EXECUTION',
                  label: 'Swap Pool (AMM Hop)',
                  description: 'C1/C2 swap legs using V2 CPMM, V3/Algebra CLMM, Curve StableSwap, or Balancer weighted pools.',
                  color: 'border-cyan-800/60 bg-cyan-950/20',
                  icon: <Activity className="w-3.5 h-3.5 text-cyan-400" />,
                },
                {
                  role: 'LIQUIDATION_TARGET',
                  label: 'Aave V3 Liquidation',
                  description: 'Repays unhealthy borrower debt, seizes collateral + 7.5% liquidation bonus. Used in LIQUIDATION execution type.',
                  color: 'border-rose-800/60 bg-rose-950/20',
                  icon: <ShieldCheck className="w-3.5 h-3.5 text-rose-400" />,
                },
              ].map((item) => (
                <div key={item.role} className={`rounded-lg border p-3 space-y-2 ${item.color}`}>
                  <div className="flex items-center gap-1.5 font-bold text-white text-[11px]">
                    {item.icon}
                    <span>{item.label}</span>
                  </div>
                  <div className="text-[11px] text-slate-300 font-mono text-[10px] uppercase tracking-wide">{item.role}</div>
                  <p className="text-slate-400 text-[11px]">{item.description}</p>
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      {!trace && (
        <div className="text-center py-12 text-slate-500 text-sm">
          No routes available. Discover routes in the Live Pipeline and execute them to generate transient accounting traces.
        </div>
      )}
    </div>
  );
};
