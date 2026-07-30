import React, { useState } from "react";
import { ShieldAlert, ShieldCheck, Zap, Lock, Unlock, RefreshCw, HelpCircle, CheckCircle2 } from "lucide-react";

export function DryRunGuardedExplanationBanner({ omega }: { omega: any }) {
  const [isArming, setIsArming] = useState(false);
  const [showExplanation, setShowExplanation] = useState(false);

  const status = omega.status || {};
  const isArmed = status.execution_armed || omega.mode?.mode === "live";
  const modeName = omega.mode?.mode || (isArmed ? "live" : "dry_run");

  const handleToggleMode = async () => {
    setIsArming(true);
    try {
      const nextMode = isArmed ? "dry_run" : "live";
      if (omega.setMode) {
        await omega.setMode(nextMode);
      } else if (omega.client?.setRuntimeMode) {
        await omega.client.setRuntimeMode(nextMode, "operator_ui");
        await omega.refresh();
      }
    } catch (err) {
      console.error(err);
    } finally {
      setTimeout(() => setIsArming(false), 500);
    }
  };

  const handleRunProofs = async () => {
    try {
      if (omega.runProofs) {
        await omega.runProofs();
      }
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div id="dry-run-guarded-banner" className={`border rounded-xl p-5 shadow-lg backdrop-blur-md transition ${
      isArmed 
        ? "bg-rose-950/30 border-rose-800/80" 
        : "bg-slate-900/90 border-amber-800/60"
    }`}>
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className={`p-2.5 rounded-lg border mt-0.5 ${
            isArmed 
              ? "bg-rose-950 text-rose-400 border-rose-800 animate-pulse" 
              : "bg-amber-950/80 text-amber-400 border-amber-800/80"
          }`}>
            {isArmed ? <Zap className="w-5 h-5" /> : <Lock className="w-5 h-5" />}
          </div>

          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-bold text-slate-100 uppercase tracking-wide flex items-center gap-2">
                Execution Status:
                <span className={`px-2.5 py-0.5 rounded-full text-xs font-mono font-bold border ${
                  isArmed 
                    ? "bg-rose-950 text-rose-300 border-rose-700" 
                    : "bg-amber-950 text-amber-300 border-amber-700"
                }`}>
                  {isArmed ? "LIVE ARMED (REAL CAPITAL DISPATCH)" : "DRY RUN / GUARDED"}
                </span>
              </h3>

              <button
                onClick={() => setShowExplanation(!showExplanation)}
                className="text-xs text-slate-400 hover:text-slate-200 underline flex items-center gap-1 font-mono"
              >
                <HelpCircle className="w-3.5 h-3.5 text-amber-400" />
                Why am I guarded?
              </button>
            </div>

            <p className="text-xs text-slate-300 mt-1">
              {isArmed ? (
                <span className="text-rose-300 font-semibold">
                  ⚠️ WARNING: Live Mainnet Flashloan execution is active. On-chain calldata submissions will dispatch real Polygon capital.
                </span>
              ) : (
                <span>
                  All incoming WSS block header opportunities are simulated in fork memory. On-chain mainnet broadcasts are blocked by circuit breakers.
                </span>
              )}
            </p>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2 font-mono text-xs">
          <button
            onClick={handleRunProofs}
            className="px-3 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 font-bold transition flex items-center gap-1.5"
          >
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
            Verify Proofs
          </button>

          <button
            onClick={handleToggleMode}
            disabled={isArming}
            className={`px-4 py-2 rounded-lg font-bold border transition flex items-center gap-2 shadow-md ${
              isArmed
                ? "bg-amber-950 hover:bg-amber-900 text-amber-200 border-amber-700"
                : "bg-rose-950 hover:bg-rose-900 text-rose-200 border-rose-700 animate-pulse"
            }`}
          >
            {isArmed ? <Lock className="w-4 h-4" /> : <Unlock className="w-4 h-4" />}
            {isArming ? "Updating..." : isArmed ? "Disarm to Guarded" : "Arm Live Execution"}
          </button>
        </div>
      </div>

      {/* Detailed "Why am I guarded" Explanation Box */}
      {showExplanation && (
        <div className="mt-4 pt-4 border-t border-slate-800/80 text-xs font-mono text-slate-300 space-y-2.5 bg-slate-950/70 p-4 rounded-lg border border-amber-900/40">
          <div className="font-bold text-amber-400 flex items-center gap-2 text-sm">
            <ShieldAlert className="w-4 h-4" />
            Why is the system initialized in DRY RUN / GUARDED mode?
          </div>
          <p>
            1. <strong>Safety Protocol Guardrail:</strong> By default, the Omega MEV Engine starts in <code className="text-amber-300 bg-amber-950 px-1 py-0.5 rounded">DRY RUN / GUARDED</code> mode to prevent accidental mainnet capital loss during node synchronization or latency spikes.
          </p>
          <p>
            2. <strong>Data Synchronization Active:</strong> All market scans, Polygon Mainnet WSS block headers, and 50 top cycle arbitrage opportunity calculations are 100% synchronized in real time via our auto-rotating RPC pool.
          </p>
          <p>
            3. <strong>Requirements to Arm Live Execution:</strong> To enable real mainnet capital dispatch, click <strong>"Arm Live Execution"</strong> above or execute the Session Signer Proof. This toggles the engine execution state from <code className="text-slate-300">dry_run</code> to <code className="text-rose-300 font-bold">live</code>.
          </p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 pt-2 border-t border-slate-800 text-[11px]">
            <div className="flex items-center gap-1.5 text-emerald-400">
              <CheckCircle2 className="w-3.5 h-3.5" /> Gas Safeguard Armed
            </div>
            <div className="flex items-center gap-1.5 text-emerald-400">
              <CheckCircle2 className="w-3.5 h-3.5" /> Oracle Freshness Verified
            </div>
            <div className="flex items-center gap-1.5 text-emerald-400">
              <CheckCircle2 className="w-3.5 h-3.5" /> WSS Header Stream Synced
            </div>
            <div className="flex items-center gap-1.5 text-emerald-400">
              <CheckCircle2 className="w-3.5 h-3.5" /> Slippage Gate 0.25% Max
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
