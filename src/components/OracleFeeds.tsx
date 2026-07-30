import React, { useState, useEffect } from "react";
import { useWebSocketWithBackoff } from "../hooks/useWebSocketWithBackoff";
import { Radio, AlertTriangle } from "lucide-react";

const ASSETS = [
  { symbol: "USDC", base: 1.0 },
  { symbol: "DAI", base: 1.0 },
  { symbol: "USDT", base: 1.0 },
  { symbol: "POL", base: 0.72 },
  { symbol: "WETH", base: 3450.21 },
  { symbol: "WBTC", base: 64230.5 },
  { symbol: "LINK", base: 14.8 },
  { symbol: "AAVE", base: 92.4 },
];

export default function OracleFeeds() {
  const [prices, setPrices] = useState<
    Record<string, { price: number; direction: "up" | "down" | "flat" }>
  >(() => {
    const init: Record<
      string,
      { price: number; direction: "up" | "down" | "flat" }
    > = {};
    ASSETS.forEach((a) => {
      init[a.symbol] = { price: a.base, direction: "flat" };
    });
    return init;
  });

  // Use our exponential backoff WS hook to satisfy robust connection requirement
  const wsProtocol =
    typeof window !== "undefined" && window.location.protocol === "https:"
      ? "wss:"
      : "ws:";
  const wsUrl =
    typeof window !== "undefined"
      ? `${wsProtocol}//${window.location.host}/api/oracle-stream`
      : "ws://localhost/api/oracle-stream";
  const { isConnected, errorCount, lastMessage } =
    useWebSocketWithBackoff(wsUrl);

  useEffect(() => {
    if (lastMessage && lastMessage.type === "oracle_prices") {
      setPrices(lastMessage.prices);
    }
  }, [lastMessage]);

  return (
    <div className="border border-[#1e2025] bg-[#0d0e12]/50 rounded-sm p-4 relative flex flex-col mt-2 glass-specular glass-inset">
      <div className="flex items-center justify-between border-b border-[#1e2025]/60 pb-2 mb-2 shrink-0">
        <div className="flex items-center gap-1.5 font-mono">
          <Radio
            size={12}
            className={isConnected ? "text-[#00f5a0]" : "text-yellow-500"}
          />
          <h3 className="text-[10px] uppercase tracking-wider font-bold text-white">
            DeFi Oracles
          </h3>
          <span
            className={`text-[7.5px] uppercase font-bold tracking-widest px-1 py-0.5 rounded-sm ml-1 ${isConnected ? "text-[#00f5a0] bg-[#00f5a0]/10 border border-[#00f5a0]/30" : "text-yellow-500 bg-yellow-500/10 border border-yellow-500/30"}`}
          >
            {isConnected ? "CHAINLINK SECURE" : `RECONNECTING (${errorCount})`}
          </span>
        </div>
      </div>

      {!isConnected && (
        <div className="flex items-center gap-2 mb-2 text-yellow-500 bg-yellow-500/5 border border-yellow-500/20 p-1.5 rounded-sm">
          <AlertTriangle size={10} />
          <span className="text-[9px] uppercase font-mono">
            WebSocket disconnected. Backoff retry active...
          </span>
        </div>
      )}

      <div className="grid grid-cols-2 gap-2 mt-1">
        {ASSETS.map((asset) => {
          const data = prices[asset.symbol];
          const color =
            data.direction === "up" ? "text-green-400" : "text-red-400";
          const formatPrice =
            data.price > 1000
              ? data.price.toFixed(2)
              : data.price > 1
                ? data.price.toFixed(3)
                : data.price.toFixed(4);

          return (
            <div
              key={asset.symbol}
              className="flex flex-col bg-[#070910]/40 border border-[#1e2025]/50 p-1.5 rounded-sm"
            >
              <span className="text-[9px] font-bold text-gray-500">
                {asset.symbol}/USD
              </span>
              <span className={`text-[11px] font-mono font-bold ${color}`}>
                ${formatPrice}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
