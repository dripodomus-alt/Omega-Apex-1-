import React, { useState, useEffect } from "react";
import { motion } from "motion/react";
import { Wallet, Search, AlertTriangle, CheckCircle2 } from "lucide-react";

export default function WalletTab({
  addLog,
}: {
  addLog: (tag: any, msg: string) => void;
}) {
  const [address, setAddress] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/config")
      .then((r) => r.json())
      .then((data) => {
        const wallet = data.EXECUTOR_WALLET || data.BOT_WALLET_ADDRESS || data.BOT_ADDRESS;
        if (wallet) {
          setAddress(wallet);
        }
      })
      .catch(() => {});
  }, []);

  const fetchBalance = async () => {
    if (!address || address.length !== 42 || !address.startsWith("0x")) {
      setError(
        "Invalid EVM address format. Must be 42 characters and start with 0x.",
      );
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);
    addLog(
      "SYS",
      `Querying Live Web3 Balance for: ${address.substring(0, 8)}...`,
    );

    try {
      const response = await fetch(`/api/wallet/balance?address=${address}`);
      const data = await response.json();
      if (!data.success) {
        throw new Error(data.error || "Failed to fetch balance");
      }
      setResult(data);
      addLog(
        "SYS",
        `Web3 Sync: Confirmed ${data.balance.substring(0, 6)} ${data.symbol}`,
      );
    } catch (err: any) {
      setError(err.message);
      addLog("ERR", `Web3 connection failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="bg-[#090a0d] border border-[#1e2025] rounded-sm p-4 glass-specular glass-inset">
        <h3 className="text-gray-300 font-mono text-[11px] uppercase flex items-center gap-2 mb-4">
          <Wallet size={13} className="text-[#00f5a0]" />
          Live Web3 Wallet Connection
        </h3>

        <p className="text-gray-500 text-xs mb-4">
          Establish an on-chain connection via JSON-RPC to read real balances
          directly from Polygon Mainnet using public node infrastructure. Confirm
          connection authenticity before dispatching network executions.
        </p>

        <div className="flex gap-2">
          <input
            type="text"
            className="flex-1 bg-black border border-[#1e2025] p-2 text-xs font-mono text-gray-300 rounded-sm focus:outline-none focus:border-[#00f5a0]/50"
            placeholder="0xYourPublicWalletAddress..."
            value={address}
            onChange={(e) => setAddress(e.target.value)}
          />
          <button
            onClick={fetchBalance}
            disabled={loading}
            className="bg-[#1e2025] hover:bg-[#1e2025]/80 text-white p-2 px-4 rounded-sm font-mono text-xs uppercase flex items-center gap-2"
          >
            {loading ? (
              <span className="animate-spin text-[#00f5a0]">●</span>
            ) : (
              <Search size={13} />
            )}
            {loading ? "Reading Chain..." : "Query Wallet"}
          </button>
        </div>

        {error && (
          <motion.div
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            className="mt-4 p-3 bg-red-900/10 border border-red-500/20 text-red-400 font-mono text-xs rounded-sm flex items-start gap-2"
          >
            <AlertTriangle size={14} className="shrink-0 mt-0.5" />
            <div>
              <div className="font-bold mb-1">Web3 Connection Error</div>
              <div className="text-red-500/80">{error}</div>
            </div>
          </motion.div>
        )}

        {result && (
          <motion.div
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            className="mt-4 p-4 border border-[#00f5a0]/20 bg-[#00f5a0]/5 font-mono rounded-sm"
          >
            <div className="flex items-center gap-2 text-[#00f5a0] mb-3 border-b border-[#00f5a0]/10 pb-2">
              <CheckCircle2 size={14} />
              <span className="text-[10px] uppercase font-bold tracking-wider">
                Live On-Chain Node Synced
              </span>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <span className="block text-[9px] text-gray-500 uppercase mb-1">
                  Target Address
                </span>
                <span className="text-white text-xs break-all">
                  {result.address}
                </span>
              </div>
              <div>
                <span className="block text-[9px] text-gray-500 uppercase mb-1">
                  Network Base Asset
                </span>
                <div className="flex items-end gap-1">
                  <span className="text-white text-lg font-bold">
                    {parseFloat(result.balance).toFixed(4)}
                  </span>
                  <span className="text-gray-400 text-xs mb-1">
                    {result.symbol}
                  </span>
                </div>
              </div>
              <div className="col-span-2 mt-2 pt-2 border-t border-[#1e2025]">
                <span className="block text-[9px] text-gray-500 uppercase mb-1">
                  RPC Source
                </span>
                <span className="text-[#00f5a0]/60 text-xs truncate block">
                  {result.source}
                </span>
              </div>
            </div>
          </motion.div>
        )}
      </div>
    </div>
  );
}
