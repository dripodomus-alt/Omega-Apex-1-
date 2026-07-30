import React, { useState, useEffect } from "react";
import { ToggleLeft, ToggleRight, Wallet, Activity, X } from "lucide-react";

interface ControlPanelProps {
  isPaused: boolean;
  onPauseToggle: () => void;
  dryRun: boolean;
  onDryRunToggle: () => void;
  pnl: number;
  lifetimePnl: number;
}

export default function ControlPanel({
  isPaused,
  onPauseToggle,
  dryRun,
  onDryRunToggle,
  pnl,
  lifetimePnl,
}: ControlPanelProps) {
  const [walletBalance, setWalletBalance] = useState<string>("0");
  const [nativeBalance, setNativeBalance] = useState<string>("0");
  const [profitAsset, setProfitAsset] = useState<string>("PROFIT ASSET");
  const [sweepsEnabled, setSweepsEnabled] = useState<boolean>(true);
  const [isHidden, setIsHidden] = useState<boolean>(false);

  useEffect(() => {
    const fetchProfitReceiverSnapshot = async () => {
      try {
        const res = await fetch("/api/wallet/profit-receiver/snapshot");
        const data = await res.json();
        if (data.success) {
          setWalletBalance(data.profitAssetBalance || "0");
          setNativeBalance(data.nativeBalanceMatic || "0");
          setProfitAsset(data.profitAsset || "PROFIT ASSET");
        }
      } catch (err) {
        // telemetry only; never mutate P&L from wallet balance reads
      }
    };
    fetchProfitReceiverSnapshot();
    const intId = setInterval(fetchProfitReceiverSnapshot, 3000);
    return () => clearInterval(intId);
  }, []);

  if (isHidden) {
    return (
      <button
        onClick={() => setIsHidden(false)}
        className="fixed bottom-4 right-4 z-50 bg-[#0d0e12] border border-[#1e2025] rounded-xl shadow-2xl p-3 text-cyan-400 hover:text-cyan-300 shadow-[0_0_15px_rgba(0,0,0,0.6)] backdrop-blur-xl transition-all outline-none focus:outline-none"
        title="Show System Controls"
      >
        <Activity size={20} className="animate-pulse" />
      </button>
    );
  }

  return (
    <div className="fixed bottom-4 right-4 z-50 bg-[#0d0e12] border border-[#1e2025] rounded-xl p-4 w-[280px] text-white font-mono shadow-[inset_0_1px_0_rgba(255,255,255,0.07),inset_0_0_32px_rgba(0,0,0,0.38),0_0_30px_rgba(0,0,0,0.6)] glass-specular backdrop-blur-xl">
      <div className="flex justify-between items-center mb-4 border-b border-[#1e2025]/60 pb-2">
        <h3 className="text-[10px] font-bold text-cyan-400 uppercase tracking-widest flex items-center gap-2">
          <Activity size={12} className="text-cyan-400 animate-pulse" />
          System Controls
        </h3>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <span className="text-[8px] text-gray-500 tracking-wider">SYNC</span>
            <div className="w-1.5 h-1.5 rounded-full bg-green-500 shadow-[0_0_8px_#22c55e] animate-pulse" />
          </div>
          <button
            onClick={() => setIsHidden(true)}
            className="text-gray-500 hover:text-gray-300 transition-colors cursor-pointer outline-none focus:outline-none"
            title="Hide System Controls"
          >
            <X size={12} />
          </button>
        </div>
      </div>

      <div className="space-y-4">
        {/* Toggles */}
        <div className="bg-[#0a0b0e]/80 border border-[#1e2025]/80 rounded p-3 flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold text-gray-300 tracking-wider">
              AUTO_EXECUTE
            </span>
            <button
              onClick={onPauseToggle}
              className="transition-colors outline-none focus:outline-none"
            >
              {!isPaused ? (
                <ToggleRight
                  size={26}
                  className="text-[#00f5a0] drop-shadow-[0_0_5px_#00f5a0]"
                  fill="currentColor"
                  fillOpacity={0.2}
                />
              ) : (
                <ToggleLeft size={26} className="text-gray-600" />
              )}
            </button>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold text-gray-300 tracking-wider">
              LIVE_TRADING_ENABLED
            </span>
            <button
              onClick={onDryRunToggle}
              className="transition-colors outline-none focus:outline-none"
            >
              {!dryRun ? (
                <ToggleRight
                  size={26}
                  className="text-pink-500 drop-shadow-[0_0_5px_#ec4899]"
                  fill="currentColor"
                  fillOpacity={0.2}
                />
              ) : (
                <ToggleLeft size={26} className="text-gray-600" />
              )}
            </button>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold text-gray-300 tracking-wider">
              AUTO_PROFIT_SWEEPS
            </span>
            <button
              onClick={() => setSweepsEnabled(!sweepsEnabled)}
              className="transition-colors outline-none focus:outline-none"
            >
              {sweepsEnabled ? (
                <ToggleRight
                  size={26}
                  className="text-purple-500 drop-shadow-[0_0_5px_#a855f7]"
                  fill="currentColor"
                  fillOpacity={0.2}
                />
              ) : (
                <ToggleLeft size={26} className="text-gray-600" />
              )}
            </button>
          </div>
        </div>

        {/* Floating Wallet & Execution Ticker */}
        <div className="bg-[#070910] p-3 rounded border border-cyan-900/30 flex flex-col relative overflow-hidden group hover:border-cyan-500/50 transition-colors">
          <div className="absolute top-0 right-0 w-16 h-16 bg-gradient-to-bl from-cyan-500/10 to-transparent rounded-bl-full pointer-events-none" />

          <div className="flex flex-col gap-1 z-10 block">
            <div className="flex items-center gap-1.5 text-[9px] text-cyan-500/80 uppercase tracking-widest font-bold">
              <Wallet size={10} />
              Profit Receiver
            </div>
            <span className="text-[14px] font-bold text-white tracking-widest">
              {walletBalance} {profitAsset.slice(0, 6)}
            </span>
            <span className="text-[8px] text-gray-500 tracking-wider break-all">
              {nativeBalance} POL telemetry only
            </span>
          </div>

          <div className="mt-3 pt-3 border-t border-[#1e2025]/80 flex flex-col gap-1 relative z-10 block">
            <div className="flex items-center gap-1.5 text-[9px] text-[#ffc840]/80 uppercase tracking-widest font-bold">
              <Activity size={10} />
              Execution Ticker
            </div>
            <div className="flex items-baseline justify-between overflow-hidden relative">
              <span
                className={`text-[12px] font-bold tracking-widest flex items-center gap-1 ${pnl >= 0 ? "text-[#00f5a0]" : "text-red-400"}`}
              >
                {pnl >= 0 ? "▲" : "▼"}{" "}
                {pnl.toLocaleString(undefined, {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}{" "}
                USD
              </span>
              <span className="text-[7px] text-gray-500 uppercase tracking-widest">
                SESSION
              </span>
            </div>
            <div className="flex items-baseline justify-between overflow-hidden relative text-[8px] text-gray-500 uppercase tracking-widest">
              <span>Lifetime</span>
              <span className={lifetimePnl >= 0 ? "text-[#00f5a0]" : "text-red-400"}>
                ${lifetimePnl.toLocaleString(undefined, {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}


