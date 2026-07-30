import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  Shield,
  Zap,
  Search,
  Activity,
  ExternalLink,
  AlertTriangle,
} from "lucide-react";

export default function LiquidationMonitor({
  addLog,
}: {
  addLog: (tag: any, msg: string) => void;
}) {
  const [items, setItems] = useState<any[]>([]);
  const [executing, setExecuting] = useState<string | null>(null);

  const fetchLiquidations = () => {
    fetch("/api/liquidations")
      .then((res) => res.json())
      .then(setItems)
      .catch(() => {});
  };

  useEffect(() => {
    fetchLiquidations();
    const interval = setInterval(fetchLiquidations, 6000);
    return () => clearInterval(interval);
  }, []);

  const handleExecute = async (user: string, healthFactor: number) => {
    setExecuting(user);
    addLog(
      "C1",
      `Initiating Balancer V2 multi-venue liquidation flash path for user: ${user.slice(0, 12)}...`,
    );
    addLog(
      "C1",
      `Borrowing Flash-liquidity limit caps... Health factor: ${healthFactor}`,
    );

    try {
      const res = await fetch("/api/liquidations/execute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user, healthFactor }),
      });
      const data = await res.json();
      if (data.success) {
        addLog(
          "C2",
          `LIQUIDATION SUCCESSFUL! Purged user position. Solved profit: +$${data.profit} USDC | Gas used: ${data.gasUsed}`,
        );
        addLog("C2", `VERIFICATION DNA: ${data.txHash.toUpperCase()}`);
        fetchLiquidations();
      } else {
        addLog("ERR", `Execution fail: ${data.message}`);
      }
    } catch (e: any) {
      addLog("ERR", `Liquidation trigger crash: ${e.message}`);
    } finally {
      setExecuting(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 mb-2">
        <Activity className="text-red-500" size={14} />
        <h3 className="font-mono text-xs uppercase tracking-wider text-red-500 font-bold">
          Live Intersect: Aave V3 Polygon Pools
        </h3>
      </div>
      <div className="border border-[#1e2025] rounded-sm bg-[#090a0d] overflow-hidden glass-specular glass-inset">
        <table className="w-full text-left border-collapse text-[11px] font-mono">
          <thead>
            <tr className="border-b border-[#1e2025]/60 bg-[#0d0e12]/80 text-gray-500 uppercase tracking-wider text-[9px]">
              <th className="p-3">Target Address</th>
              <th className="p-3">Collateral</th>
              <th className="p-3">Debt</th>
              <th className="p-3">Value (USD)</th>
              <th className="p-3">Health Factor</th>
              <th className="p-3 text-right">Action</th>
            </tr>
          </thead>
          <tbody>
            <AnimatePresence>
              {items.map((item, idx) => (
                <motion.tr
                  key={item.user}
                  initial={{ opacity: 0, y: -5 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  className="border-b border-[#1e2025]/30 hover:bg-[#1e2025]/20 group transition-colors"
                >
                  <td className="p-3 text-gray-300">
                    <div className="flex items-center gap-2">
                      <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
                      <span className="select-all hover:text-white cursor-text">
                        {item.user.slice(0, 18)}...
                      </span>
                      <a
                        href={`https://polygonscan.com/address/${item.user}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-gray-600 hover:text-white"
                      >
                        <ExternalLink size={10} />
                      </a>
                    </div>
                  </td>
                  <td className="p-3 text-gray-400 font-semibold">
                    {item.collateral}
                  </td>
                  <td className="p-3 text-gray-400 font-semibold">
                    {item.debt}
                  </td>
                  <td className="p-3">
                    <span className="text-white">
                      ${item.collateralValue.toLocaleString()}
                    </span>
                  </td>
                  <td className="p-3">
                    <div className="flex items-center gap-2">
                      <span className="text-red-400 font-bold">
                        {item.healthFactor.toFixed(3)}
                      </span>
                      <div className="w-16 bg-black h-1 rounded-sm overflow-hidden border border-[#1e2025]">
                        <div
                          className="h-full bg-red-500"
                          style={{
                            width: `${Math.min(100, Math.max(0, (1 / (item.healthFactor || 0.99)) * 50))}%`,
                          }}
                        />
                      </div>
                    </div>
                  </td>
                  <td className="p-3 text-right">
                    <button
                      onClick={() =>
                        handleExecute(item.user, item.healthFactor)
                      }
                      disabled={executing !== null}
                      className="px-3 py-1.5 bg-red-950/20 hover:bg-red-950/40 border border-red-500/30 hover:border-red-500/60 text-red-500 uppercase tracking-widest text-[9px] font-bold rounded-sm disabled:opacity-50 transition-all flex items-center justify-end gap-2 ml-auto"
                    >
                      {executing === item.user ? (
                        <>
                          <span className="animate-spin text-red-500">●</span>
                          FLASH MEV...
                        </>
                      ) : (
                        <>
                          <AlertTriangle size={10} />
                          LIQUIDATE
                        </>
                      )}
                    </button>
                  </td>
                </motion.tr>
              ))}
            </AnimatePresence>
            {items.length === 0 && (
              <tr>
                <td
                  colSpan={6}
                  className="p-6 text-center text-gray-600 text-xs tracking-wider"
                >
                  SCANNING MEMPOOL FOR VULNERABLE DEBT POSITIONS...
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="pt-2 border-t border-[#1e2025]/50 mt-4">
        <div className="flex items-center gap-2 mb-2">
          <AlertTriangle className="text-yellow-500" size={14} />
          <h3 className="font-mono text-xs uppercase tracking-wider text-yellow-500 font-bold">
            Alert Feed: Approaching Liquidation
          </h3>
        </div>
        <div className="border border-[#1e2025] bg-[#0d0e12]/80 rounded-sm p-3 max-h-[140px] overflow-y-auto space-y-1 scrollbar-thin font-mono text-[10px]">
          <AnimatePresence>
            {items
              .filter((i) => i.healthFactor > 1.0 && i.healthFactor < 1.05)
              .map((item) => (
                <motion.div
                  key={item.user + "-alert"}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  className="flex items-center justify-between bg-yellow-500/5 border border-yellow-500/20 px-2 py-1.5 rounded-sm"
                >
                  <span className="text-yellow-400/80">
                    ⚠️ WARNING: Position{" "}
                    <span className="text-white">
                      {item.user.slice(0, 8)}...
                    </span>{" "}
                    dipping.
                  </span>
                  <span className="text-gray-400 uppercase tracking-widest shrink-0 ml-2">
                    HF:{" "}
                    <span className="text-yellow-400 font-bold">
                      {item.healthFactor.toFixed(3)}
                    </span>
                  </span>
                </motion.div>
              ))}
            {items.filter((i) => i.healthFactor > 1.0 && i.healthFactor < 1.05)
              .length === 0 && (
              <div className="text-gray-500 text-center py-2 uppercase tracking-wide text-[9px]">
                No accounts currently in warning zone (1.00 - 1.05).
              </div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
