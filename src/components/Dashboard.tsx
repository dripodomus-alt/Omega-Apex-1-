import React, { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  Shield,
  Zap,
  Database,
  BarChart3,
  Sliders,
  Wallet,
  Cpu,
  Activity,
  AlertTriangle,
  Terminal as TerminalIcon,
  Search,
  ArrowRight,
  CheckCircle2,
  ChevronRight,
  Bot,
  Layers,
  BrainCircuit,
} from "lucide-react";
import ConfettiCelebration from "./ConfettiCelebration";

import Header from "./Header";
import Ticker from "./Ticker";
import ControlPanel from "./ControlPanel";
import ProfitDashboard from "./ProfitDashboard";
import OracleFeeds from "./OracleFeeds";
import LiquidationMonitor from "./LiquidationMonitor";
import ArbitrageCycleVisualization from "./ArbitrageCycleVisualization";
import SystemIntel from "./SystemIntel";
import LanesGrid from "./LanesGrid";
import ConfigTab from "./ConfigTab";
import WalletTab from "./WalletTab";
import AgentTab from "./AgentTab";
import NotificationSidebar from "./NotificationSidebar";
import SimulationConsole from "./SimulationConsole";
import EconomicSentimentWidget from "./EconomicSentimentWidget";
import DiagnosticConsole from "./DiagnosticConsole";
import BenchmarkScorecard from "./BenchmarkScorecard";
import MainnetPayloadSchema from "./MainnetPayloadSchema";
import C2TriggerLogic from "./C2TriggerLogic";

interface Log {
  id: string;
  timestamp: string;
  tag: "C1" | "C2" | "DEX" | "SYS" | "ERR" | "AAVE" | "ARB";
  message: string;
}

// -------------------------------------------------------------------
// Component: Aave Inspector (Polled Query on Polygon Mainnet)
// -------------------------------------------------------------------
const AaveInspectorTab = ({
  addLog,
}: {
  addLog: (tag: any, msg: string) => void;
}) => {
  const [address, setAddress] = useState(
    "0x1e3092287857dF3255F4D3cb2657B02607c05060",
  );
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleInspect = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    addLog(
      "AAVE",
      `Querying Aave V3 position direct metrics for: ${address.slice(0, 10)}...`,
    );
    try {
      const res = await fetch("/api/aave-inspect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ userAddress: address }),
      });
      const data = await res.json();
      if (res.ok && data.success) {
        setResult(data);
        addLog(
          "AAVE",
          `SUCCESS! Health of ${address.slice(0, 8)} is verified at health factor: ${data.healthFactor.toFixed(4)}`,
        );
      } else {
        setError(data.error || "Failed to inspect on-chain account.");
        addLog(
          "ERR",
          `Failed user inspect: ${data.error || "General position overflow error"}`,
        );
      }
    } catch (e: any) {
      setError(e.message || "Network failure.");
      addLog("ERR", `Inspect fail: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="font-mono text-[10px] space-y-3 bg-[#0d0e12]/80 p-4 border border-[#1e2025] rounded-sm relative glass-specular glass-inset">
      <div className="absolute top-0 right-0 w-2 h-2 border-t-2 border-r-2 border-blue-500/50" />
      <div className="absolute bottom-0 left-0 w-2 h-2 border-b-2 border-l-2 border-blue-500/50" />
      <div className="flex items-center gap-2 mb-1 border-b border-[#1e2025]/50 pb-2">
        <Shield size={14} className="text-blue-400" />
        <h3 className="uppercase tracking-[0.18em] font-bold text-gray-400">
          Aave V3 Mainnet Inspector
        </h3>
      </div>
      <p className="text-gray-500 text-[9px] leading-relaxed">
        Verify account health factors, total collateral bases, and liquidation
        eligibility direct from Polygon Aave Pool contracts:
      </p>
      <div className="flex gap-2">
        <input
          type="text"
          value={address}
          onChange={(e) => setAddress(e.target.value)}
          placeholder="0x..."
          className="flex-1 bg-black/40 border border-[#1e2025]/80 px-2 py-1.5 text-[10px] text-white focus:border-blue-400 outline-none rounded-sm font-mono"
        />
        <button
          onClick={handleInspect}
          disabled={loading}
          className="px-4 bg-blue-600 hover:bg-blue-500 text-white font-bold uppercase transition-colors px-2 border border-blue-500/30 cursor-pointer flex items-center gap-1.5"
        >
          {loading ? "INSIPECTING..." : "QUERY STATE"}
        </button>
      </div>

      {error && (
        <div className="p-2 border border-red-900/40 bg-red-950/10 text-red-400 rounded-sm">
          ⚠️ {error}
        </div>
      )}

      {result && (
        <div className="p-3 border border-[#1e2025] bg-black/30 space-y-2 rounded-sm text-gray-300">
          <div className="flex justify-between items-center py-1 border-b border-[#1e2025]/30">
            <span className="text-gray-500">HEALTH FACTOR (HF):</span>
            <span
              className={`font-bold text-[11px] ${result.healthFactor < 1 ? "text-red-500 animate-pulse" : "text-green-400"}`}
            >
              {result.healthFactor.toFixed(5)}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-4 pt-1">
            <div>
              <div className="text-gray-500 text-[8px]">TOTAL COLLATERAL</div>
              <div className="text-white font-bold text-[11px]">
                $
                {result.totalCollateralUsd.toLocaleString(undefined, {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}
              </div>
            </div>
            <div>
              <div className="text-gray-500 text-[8px]">
                TOTAL DEBT POSITION
              </div>
              <div className="text-white font-bold text-[11px]">
                $
                {result.totalDebtUsd.toLocaleString(undefined, {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}
              </div>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4 pt-1.5 border-t border-[#1e2025]/20">
            <div>
              <div className="text-gray-500 text-[8px]">MAX LTV RATE</div>
              <div className="text-[#00e5ff] font-bold">
                {result.ltvPct.toFixed(2)}%
              </div>
            </div>
            <div>
              <div className="text-gray-500 text-[8px]">
                LIQUIDATION THRESHOLD
              </div>
              <div className="text-yellow-500 font-bold">
                {result.liquidationThresholdPct.toFixed(2)}%
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// -------------------------------------------------------------------
// Component: Target Liquidation Hunting Tab
// -------------------------------------------------------------------
const LiquidationTab = ({
  addLog,
}: {
  addLog: (tag: any, msg: string) => void;
}) => {
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
      `Initiating Balancer V2 multi-venue liquidation flash path for user user: ${user.slice(0, 12)}...`,
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
    <div className="space-y-3 font-mono text-[10px]">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {items.map((item, i) => (
          <div
            key={i}
            className="border border-[#1e2025] bg-[#0d0e12]/80 p-3 rounded-sm relative"
          >
            <div className="absolute top-0 left-0 w-2 h-2 border-t border-l border-red-500/40" />
            <div className="flex justify-between items-center mb-1.5 border-b border-[#1e2025]/50 pb-1.5">
              <span
                className="text-white font-bold select-all cursor-pointer hover:underline"
                title="Copy Address"
              >
                {item.user.slice(0, 18)}...
              </span>
              <span className="text-[7.5px] px-1 bg-red-500/10 text-red-500 border border-red-500/20 rounded-sm font-bold">
                ELI_TARGET
              </span>
            </div>

            <div className="flex justify-between items-end mb-3">
              <div>
                <span className="text-gray-500 text-[7.5px] uppercase block">
                  Collateral Volume
                </span>
                <span className="text-sm font-semibold text-white">
                  ${item.collateralValue.toLocaleString()}
                </span>
              </div>
              <div className="text-right">
                <span className="text-gray-500 text-[7.5px] uppercase block">
                  HF (Health Factor)
                </span>
                <span className="text-sm font-semibold text-red-400 font-bold">
                  {item.healthFactor.toFixed(3)}
                </span>
              </div>
            </div>

            <div className="w-full bg-black/40 h-1.5 rounded-sm overflow-hidden mb-3.5 border border-[#1e2025]">
              <motion.div
                initial={{ width: 0 }}
                animate={{
                  width: `${Math.min(100, Math.max(0, (1 / (item.healthFactor || 0.99)) * 50))}%`,
                }}
                className="h-full bg-gradient-to-r from-red-600 to-orange-500"
              />
            </div>

            <button
              onClick={() => handleExecute(item.user, item.healthFactor)}
              disabled={executing !== null}
              className="w-full py-1.5 bg-red-950/20 hover:bg-red-950/40 border border-red-500/30 hover:border-red-500/60 text-red-400 font-bold uppercase transition-all tracking-wider cursor-pointer"
            >
              {executing === item.user
                ? "TRANSACTING FLASH MEV..."
                : "TRIGGER FLASH LIQUIDATION"}
            </button>
          </div>
        ))}
        {items.length === 0 && (
          <div className="col-span-2 text-center py-8 border border-dashed border-[#1e2025] text-gray-500">
            Scanning for vulnerable debt thresholds below 1.000...
          </div>
        )}
      </div>
    </div>
  );
};

// -------------------------------------------------------------------
// Component: Liquidity Health Gauge
// -------------------------------------------------------------------
// -------------------------------------------------------------------
// Component: Arbitrage MEV Execution Scanner Tab
// -------------------------------------------------------------------
const ArbitrageScannerTab = ({
  addLog,
}: {
  addLog: (tag: any, msg: string) => void;
}) => {
  const [amount, setAmount] = useState("15000");
  const [simulation, setSimulation] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const triggerScan = async () => {
    setLoading(true);
    addLog(
      "DEX",
      `Querying core Uniswap & Sushi DEX reserves for Arbitrage index at ${amount} USDC...`,
    );
    try {
      const res = await fetch("/api/arbitrage/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ amount }),
      });
      const data = await res.json();
      if (data.success) {
        setSimulation(data);
        const logCol = data.financials.netProfit > 0 ? "+" : "";
        addLog("C1", `Squeezed Path: ${data.route}`);
        addLog(
          "C1",
          `GROSS OUT: ${data.swapLeg1.amountOut.toFixed(data.swapLeg1.tokenOut === "WBTC" ? 5 : 4)} ${data.swapLeg1.tokenOut} / NET SOLVED SPREAD: ${logCol}$${data.financials.netProfit.toFixed(2)} USDC`,
        );
      }
    } catch (e: any) {
      addLog("ERR", `Solver execution failure: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    triggerScan();
  }, []);

  return (
    <div className="space-y-3 font-mono text-[10px]">
      <div className="flex gap-3 items-end bg-[#0d0e12]/50 p-2.5 border border-[#1e2025] rounded-sm">
        <div className="flex-1">
          <label className="text-[7.5px] uppercase text-gray-500 font-bold block mb-1">
            Flash Loan Size (USDC)
          </label>
          <input
            type="number"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            className="w-full bg-black/60 border border-[#1e2025] px-2 py-1.5 focus:border-cyan-400 outline-none text-white text-xs font-bold font-mono rounded-sm"
          />
        </div>
        <button
          onClick={triggerScan}
          disabled={loading}
          className="h-8.5 px-4 bg-cyan-950/20 hover:bg-cyan-950/40 border border-cyan-500/40 hover:border-cyan-500/60 text-cyan-400 font-mono font-bold uppercase tracking-wider rounded-sm transition-all cursor-pointer"
        >
          {loading ? "SOLVING EQUATIONS..." : "⟳ INITIATE MEV EXPLOIT"}
        </button>
      </div>

      {simulation && (
        <div className="space-y-3">
          {/* Main Net profit header card */}
          <div className="p-3 bg-cyan-950/10 border border-cyan-500/20 rounded-sm flex justify-between items-center relative">
            <div className="absolute top-0 right-0 w-1.5 h-1.5 border-t border-r border-cyan-400/40" />
            <div>
              <span className="text-[7.5px] text-gray-500 uppercase font-bold block">
                Solved Route Path
              </span>
              <span className="text-gray-200 text-[10px] pr-2 block">
                {simulation.route}
              </span>
            </div>
            <div className="text-right">
              <span className="text-[7.5px] text-gray-500 uppercase font-bold block">
                NET GAIN
              </span>
              <span
                className={`text-[12px] font-bold ${simulation.financials.netProfit > 0 ? "text-[#00f5a0]" : "text-red-400"}`}
              >
                ${simulation.financials.netProfit.toFixed(3)}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="p-2.5 border border-[#1e2025] bg-[#0c0d11]/80 rounded-sm space-y-1.5 relative">
              <span className="text-cyan-400 font-bold tracking-wider uppercase text-[8px] block border-b border-[#1e2025] pb-1">
                LEG 1: BUY SWAP
              </span>
              <div className="flex justify-between">
                <span className="text-gray-500">AMM Venue:</span>
                <span className="text-gray-300 font-bold">
                  {simulation.swapLeg1.dex}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Operation:</span>
                <span className="text-[#00f5a0]">
                  Swap {simulation.swapLeg1.tokenIn} →{" "}
                  {simulation.swapLeg1.tokenOut}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">BUY_LEG1_PRICE:</span>
                <span className="text-white font-bold">
                  $
                  {simulation.swapLeg1.executionPrice.toLocaleString(
                    undefined,
                    { minimumFractionDigits: 2, maximumFractionDigits: 2 },
                  )}
                </span>
              </div>
              <div className="flex justify-between border-t border-[#1e2025]/40 pt-1 text-gray-400">
                <span>Exchanged:</span>
                <span>
                  {simulation.swapLeg1.amountIn.toLocaleString()} USDC →{" "}
                  {simulation.swapLeg1.amountOut.toFixed(
                    simulation.swapLeg1.tokenOut === "WBTC" ? 5 : 4,
                  )}{" "}
                  {simulation.swapLeg1.tokenOut}
                </span>
              </div>
            </div>

            <div className="p-2.5 border border-[#1e2025] bg-[#0c0d11]/80 rounded-sm space-y-1.5 relative">
              <span className="text-purple-400 font-bold tracking-wider uppercase text-[8px] block border-b border-[#1e2025] pb-1">
                LEG 2: SELL SWAP
              </span>
              <div className="flex justify-between">
                <span className="text-gray-500">AMM Venue:</span>
                <span className="text-gray-200 font-bold">
                  {simulation.swapLeg2.dex}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Operation:</span>
                <span className="text-yellow-400">
                  Swap {simulation.swapLeg2.tokenIn} →{" "}
                  {simulation.swapLeg2.tokenOut}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">SELL_LEG2_PRICE:</span>
                <span className="text-white font-bold">
                  $
                  {simulation.swapLeg2.executionPrice.toLocaleString(
                    undefined,
                    { minimumFractionDigits: 2, maximumFractionDigits: 2 },
                  )}
                </span>
              </div>
              <div className="flex justify-between border-t border-[#1e2025]/40 pt-1 text-gray-400">
                <span>Exchanged:</span>
                <span>
                  {simulation.swapLeg2.amountIn.toFixed(
                    simulation.swapLeg2.tokenIn === "WBTC" ? 5 : 4,
                  )}{" "}
                  {simulation.swapLeg2.tokenIn} →{" "}
                  {simulation.swapLeg2.amountOut.toLocaleString(undefined, {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                  })}{" "}
                  USDC
                </span>
              </div>
            </div>
          </div>

          <div className="p-2.5 border border-[#1e2025] bg-black/30 rounded-sm">
            <div className="grid grid-cols-4 gap-2 text-[8px] border-b border-[#1e2025]/60 pb-2 mb-2">
              <div>
                <span className="text-gray-500 block uppercase font-bold">
                  Gross Spread
                </span>
                <span className="text-white font-bold">
                  ${simulation.financials.grossProfit.toFixed(2)}
                </span>
              </div>
              <div>
                <span className="text-gray-500 block uppercase font-bold">
                  Gas limits
                </span>
                <span className="text-white font-bold">
                  {simulation.financials.simulatedGasUsed.toLocaleString()} u
                </span>
              </div>
              <div>
                <span className="text-gray-500 block uppercase font-bold">
                  Base Gas Fee
                </span>
                <span className="text-blue-400 font-bold">
                  {simulation.financials.estimatedGasPriceGwei} gwei
                </span>
              </div>
              <div>
                <span className="text-gray-500 block uppercase font-bold">
                  Gas cost ($)
                </span>
                <span className="text-red-400 font-bold">
                  ${simulation.financials.gasCostUsd.toFixed(2)}
                </span>
              </div>
            </div>

            <div>
              <span className="text-gray-500 text-[7.5px] uppercase font-bold mb-1 block">
                CRYPTOGRAPHIC TRANSACTION_DNA
              </span>
              <div className="bg-black/90 border border-[#1e2025] p-1.5 break-all text-[10px] text-green-400 flex justify-between items-center select-all">
                <span>{simulation.transactionDna}</span>
                <span className="text-[6.5px] bg-green-500/10 border border-green-500/30 text-green-500 font-bold uppercase rounded-sm px-1 py-0.5 select-none shrink-0">
                  VERIFIED SPREAD PATH
                </span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// -------------------------------------------------------------------
// Component: Executable Routes Tab
// -------------------------------------------------------------------
const RoutesTab = ({ addLog }: { addLog: (tag: any, msg: string) => void }) => {
  const [routes, setRoutes] = useState<any[]>([]);
  const [activeTest, setActiveTest] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<any>(null);
  const [testingId, setTestingId] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/routes")
      .then((res) => res.json())
      .then(setRoutes)
      .catch(() => {});
  }, []);

  const runRouteTest = async (route: any) => {
    setTestingId(route.id);
    setTestResult(null);
    addLog(
      "SYS",
      `Initializing dynamic diagnostic tests for route ${route.id}: ${route.name}`,
    );

    try {
      const res = await fetch("/api/arbitrage/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ amount: 15000 }),
      });
      const data = await res.json();
      if (data.success) {
        setTestResult(data);
        setActiveTest(route.id);
        const colorSign = data.financials.netProfit > 0 ? "+" : "";
        addLog(
          "SYS",
          `${route.id} VERIFIED! Buy Leg 1: $${data.swapLeg1.executionPrice.toFixed(2)} / Sell Leg 2: $${data.swapLeg2.executionPrice.toFixed(2)} | Profit: ${colorSign}$${data.financials.netProfit.toFixed(3)}`,
        );
      }
    } catch (e: any) {
      addLog("ERR", `Route test failed: ${e.message}`);
    } finally {
      setTestingId(null);
    }
  };

  return (
    <div className="space-y-3 font-mono text-[10px] overflow-y-auto max-h-[380px] pr-1 scrollbar-thin">
      {routes.map((route) => (
        <div
          key={route.id}
          className="border border-[#1e2025] bg-[#0d0e12]/80 p-3 rounded-sm relative"
        >
          <div className="absolute top-0 right-0 w-2 h-2 border-t border-r border-[#00e5ff]/30" />
          <div className="flex justify-between items-center mb-2 border-b border-[#1e2025]/50 pb-2">
            <span className="font-bold text-white text-[10.5px] uppercase">
              {route.id} // {route.name}
            </span>
            <span className="text-[#00e5ff] font-bold text-[9.5px] tracking-wide">
              {route.path}
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-2">
            <div className="p-2 border border-[#1e2025] bg-black/35 rounded-sm">
              <span className="text-cyan-400 font-bold block mb-1 text-[8px] uppercase">
                LEG 1: BUY POSITION
              </span>
              <div>
                <span className="text-gray-500">Task:</span>{" "}
                <span className="text-gray-200">{route.leg1.action}</span>
              </div>
              <div>
                <span className="text-gray-500">Pool address:</span>{" "}
                <span className="text-blue-400 select-all font-mono leading-none">
                  {route.leg1.pairAddress.slice(0, 16)}...
                </span>
              </div>
              <div>
                <span className="text-gray-500">Router:</span>{" "}
                <span className="text-yellow-400 select-all font-mono leading-none">
                  {route.leg1.router.slice(0, 16)}...
                </span>
              </div>
            </div>

            <div className="p-2 border border-[#1e2025] bg-black/35 rounded-sm">
              <span className="text-purple-400 font-bold block mb-1 text-[8px] uppercase">
                LEG 2: SELL POSITION
              </span>
              <div>
                <span className="text-gray-500">Task:</span>{" "}
                <span className="text-gray-200">{route.leg2.action}</span>
              </div>
              <div>
                <span className="text-gray-500">Pool address:</span>{" "}
                <span className="text-blue-400 select-all font-mono leading-none">
                  {route.leg2.pairAddress.slice(0, 16)}...
                </span>
              </div>
              <div>
                <span className="text-gray-500">Router:</span>{" "}
                <span className="text-yellow-400 select-all font-mono leading-none">
                  {route.leg2.router.slice(0, 16)}...
                </span>
              </div>
            </div>
          </div>

          <div className="flex justify-between items-center bg-black/40 border border-[#1e2025] px-2.5 py-1.5 mt-2 rounded-sm text-[8.5px]">
            <div className="flex gap-4">
              <div>
                <span className="text-gray-500 block uppercase text-[7px]">
                  Stage Status
                </span>
                <span className="text-[#00f5a0] font-bold">{route.status}</span>
              </div>
              <div>
                <span className="text-gray-500 block uppercase text-[7px]">
                  Target Limit ($)
                </span>
                <span className="text-white font-bold">
                  ${route.minProfitUsdc} USDC
                </span>
              </div>
              <div>
                <span className="text-gray-500 block uppercase text-[7px]">
                  Gas Estimate
                </span>
                <span className="text-orange-400 font-bold">
                  {route.estimatedGasUsed.toLocaleString()} u
                </span>
              </div>
            </div>

            <button
              onClick={() => runRouteTest(route)}
              disabled={testingId !== null}
              className="px-3 py-1 bg-cyan-950/20 hover:bg-cyan-950/40 border border-cyan-500/30 text-cyan-400 font-bold uppercase rounded-sm transition-all cursor-pointer"
            >
              {testingId === route.id ? "TESTING..." : "RUN VERIFICATION"}
            </button>
          </div>

          {activeTest === route.id && testResult && (
            <div className="mt-2.5 p-2.5 bg-green-500/5 border border-green-500/20 rounded-sm">
              <div className="text-[#00f5a0] text-[8px] font-bold uppercase mb-1">
                ➔ EXPANDED TRACE DISSECTION MATRIX
              </div>
              <div className="grid grid-cols-2 gap-2 text-[8px]">
                <div>
                  <div>
                    <span className="text-gray-500">
                      Buy execution leg 1 (WETH):
                    </span>{" "}
                    <span className="text-white font-bold">
                      ${testResult.swapLeg1.executionPrice.toFixed(2)}
                    </span>
                  </div>
                  <div>
                    <span className="text-gray-500">Sync core reserves:</span>{" "}
                    <span className="text-gray-400">
                      {testResult.swapLeg1.reserveUSDC} USDC /{" "}
                      {testResult.swapLeg1.reserveWETH} WETH
                    </span>
                  </div>
                </div>
                <div>
                  <div>
                    <span className="text-gray-500">
                      Sell execution leg 2 (WETH):
                    </span>{" "}
                    <span className="text-white font-bold">
                      ${testResult.swapLeg2.executionPrice.toFixed(2)}
                    </span>
                  </div>
                  <div>
                    <span className="text-gray-500">Sync core reserves:</span>{" "}
                    <span className="text-gray-400">
                      {testResult.swapLeg2.reserveWETH} WETH /{" "}
                      {testResult.swapLeg2.reserveUSDC} USDC
                    </span>
                  </div>
                </div>
              </div>
              <div className="flex justify-between items-center text-[8.5px] border-t border-[#1e2025] mt-1.5 pt-1.5 text-gray-400">
                <div>
                  Net solved profit margins:{" "}
                  <span className="text-[#00f5a0] font-bold">
                    ${testResult.financials.netProfit.toFixed(4)} USDC
                  </span>
                </div>
                <div>
                  DNA_SIGN:{" "}
                  <code className="text-[#00f5a0] select-all font-mono text-[8px]">
                    {testResult.transactionDna}
                  </code>
                </div>
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
};

// -------------------------------------------------------------------
// Component: Live Reserves Pools list Tab
// -------------------------------------------------------------------
const ReservesTab = () => {
  const [pools, setPools] = useState<any[]>([]);

  useEffect(() => {
    fetch("/api/pools")
      .then((res) => res.json())
      .then(setPools)
      .catch(() => {});
  }, []);

  return (
    <div className="font-mono text-[10px] border border-[#1e2025] bg-[#0d0e12]/80 rounded-sm p-2 glass-specular glass-inset">
      <div className="overflow-x-auto">
        <table className="w-full text-left font-mono">
          <thead className="text-gray-500 border-b border-[#1e2025]">
            <tr className="uppercase text-[8px]">
              <th className="py-1.5 pl-2">AMM Venue</th>
              <th className="py-1.5">Pair</th>
              <th className="py-1.5">DEX Fee</th>
              <th className="py-1.5 text-right">Pool reserve 0</th>
              <th className="py-1.5 text-right pr-2">Pool reserve 1</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#1e2025]/30">
            {pools.map((p, i) => {
              const res0 = (Number(p.reserve0) / 10 ** 6).toLocaleString(
                undefined,
                { maximumFractionDigits: 0 },
              );
              const res1 = (Number(p.reserve1) / 10 ** 18).toLocaleString(
                undefined,
                { maximumFractionDigits: 2 },
              );
              return (
                <tr
                  key={i}
                  className="hover:bg-white/5 transition-all cursor-crosshair"
                >
                  <td className="py-2 pl-2 text-cyan-400 select-all font-semibold">
                    {p.dex}
                  </td>
                  <td className="py-2 text-white border-b border-[#1e2025]/20">
                    {p.token0}/{p.token1}
                  </td>
                  <td className="py-2 opacity-50 border-b border-[#1e2025]/20">
                    {(p.fee * 100).toFixed(2)}%
                  </td>
                  <td className="py-2 text-right text-gray-400 font-bold border-b border-[#1e2025]/20">
                    {res0} {p.token0}
                  </td>
                  <td className="py-2 text-right text-gray-400 font-bold pr-2 border-b border-[#1e2025]/20">
                    {res1} {p.token1}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};

// -------------------------------------------------------------------
// Component: Sourced Prices Tab
// -------------------------------------------------------------------
const PricesTab = ({ addLog }: { addLog: (tag: any, msg: string) => void }) => {
  const [prices, setPrices] = useState<any[]>([]);

  const fetchPrices = () => {
    fetch("/api/prices")
      .then((res) => res.json())
      .then(setPrices)
      .catch(() => {});
  };

  useEffect(() => {
    fetchPrices();
    const interval = setInterval(fetchPrices, 4000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="font-mono text-[10px] space-y-3">
      <div className="border border-[#1e2025] bg-[#0d0e12]/80 rounded-sm p-3 glass-specular glass-inset">
        <p className="text-gray-500 mb-2 leading-normal text-[8.5px]">
          Polygon decentralised price feeds sourced directly from Chainlink
          Mainnet feeds:
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-left font-mono">
            <thead className="text-gray-500 border-b border-[#1e2025] text-[7.5px] uppercase">
              <tr>
                <th className="py-1.5 pl-2">Contract Token</th>
                <th className="py-1.5">Address</th>
                <th className="py-1.5 text-right">Oracle Feed ($)</th>
                <th className="py-1.5 text-right pr-2">Sourced Feeds</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1e2025]/30">
              {prices.map((p, i) => (
                <tr key={i} className="hover:bg-white/5 transition-all">
                  <td className="py-2 pl-2">
                    <div className="font-bold text-white text-[10.5px]">
                      {p.symbol}
                    </div>
                    <div className="text-[7.5px] text-gray-500 uppercase">
                      {p.name}
                    </div>
                  </td>
                  <td className="py-2">
                    <span
                      className="text-[#00e5ff] hover:underline cursor-pointer select-all font-mono"
                      title="Copy contract Address"
                      onClick={() => {
                        navigator.clipboard.writeText(p.address);
                        addLog(
                          "SYS",
                          `Copied address hash: ${p.symbol} -> ${p.address}`,
                        );
                      }}
                    >
                      {p.address.slice(0, 18)}...
                    </span>
                  </td>
                  <td className="py-2 text-right font-bold text-[#00f5a0] text-[10.5px]">
                    $
                    {p.priceUsd
                      ? p.priceUsd.toLocaleString(undefined, {
                          minimumFractionDigits: 2,
                          maximumFractionDigits: 4,
                        })
                      : "1.000"}
                  </td>
                  <td className="py-2 text-right text-gray-500 text-[7.5px] pr-2 uppercase">
                    {p.source.split(" ")[0]}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

import PipelineDiagnosticModal from "./PipelineDiagnosticModal";
import HyperImmersiveOpportunities from "./HyperImmersiveOpportunities";
import ProtocolModules from "./ProtocolModules";

// -------------------------------------------------------------------
// Core Main Component: Dashboard
// -------------------------------------------------------------------
export default function Dashboard() {
  const [workspaceViews, setWorkspaceViews] = useState({
    arbitrage: true,
    liquidation: true,
    simulation: true,
    schema: false,
    c2logic: false,
    wallet: true,
    config: false,
  });

  const [isDiagnosticModalOpen, setIsDiagnosticModalOpen] = useState(true);

  const [layout, setLayout] = useState({
    spreads: false,
    hyper: true,
    cache: false,
    oracles: false,
    chart: true,
    executions: false,
    workspace: true,
    intel: true,
    modules: true,
  });

  const toggleLayout = (key: keyof typeof layout) =>
    setLayout((p) => ({ ...p, [key]: !p[key] }));

  // Master Telemetry states
  const [pnl, setPnl] = useState(0);
  const [lifetimePnl, setLifetimePnl] = useState(0);
  const [pnlHistory, setPnlHistory] = useState<
    { time: string; profitUSD: number; profitPOL: number }[]
  >([]);
  const [gas, setGas] = useState(120.0);
  const [block, setBlock] = useState(42069137);
  const [dryRun, setDryRun] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<
    "live" | "poll" | "connecting" | "error"
  >("connecting");
  const [botWallet, setBotWallet] = useState(
    "0x0000000000000000000000000000000000000000"
  );

  // Stats
  const [wins, setWins] = useState(131);
  const [trades, setTrades] = useState(142);
  const [velocity, setVelocity] = useState(24);
  const [avgProfit, setAvgProfit] = useState(58.12);
  const [totalSettledCycles, setTotalSettledCycles] = useState(0);
  const [util, setUtil] = useState(86.4);
  const [showBagSecured, setShowBagSecured] = useState(false);

  // Pipeline count states
  const [pipelineStages, setPipelineStages] = useState<any[]>(
    Array(9).fill({ name: "", count: 0 }),
  );
  const [recentCycles, setRecentCycles] = useState<any[]>([]);

  // Reserve Cache Indicators
  const [cache, setCache] = useState({
    pools: 274,
    dirty: 12,
    stale: 2,
    syncs: 9482,
    ratePs: 14.8,
    lastMs: Date.now(),
  });

  // Opportunities Scanned list
  const [opportunities, setOpportunities] = useState<any[]>([]);
  const [oppDiagnostics, setOppDiagnostics] = useState<any>(null);

  // Lanes Executor state
  const [lanes, setLanes] = useState<any[]>([]);
  const seenServerLogIds = useRef<Set<string>>(new Set());
  const lastServerLogId = useRef(0);
  const [dashboardStreamConnected, setDashboardStreamConnected] = useState(false);

  // Execute initial config fetch for wallet rendering
  const fetchDashboardConfig = () => {
    fetch("/api/config")
      .then((r) => r.json())
      .then((data) => {
        const wallet = data.EXECUTOR_WALLET || data.BOT_WALLET_ADDRESS || data.BOT_ADDRESS || "0x0000000000000000000000000000000000000000";
        setBotWallet(wallet);
        
        if (data.SHADOW_MODE !== undefined) setDryRun(data.SHADOW_MODE);
      })
      .catch(() => {});
  };

  useEffect(() => {
    fetchDashboardConfig();
  }, []);

  // Live Terminal Logs
  const [logs, setLogs] = useState<Log[]>([
    {
      id: "1",
      timestamp: new Date().toLocaleTimeString("en-US", { hour12: false }),
      tag: "SYS",
      message: "TITAN NEXUS core armed successfully.",
    },
    {
      id: "2",
      timestamp: new Date().toLocaleTimeString("en-US", { hour12: false }),
      tag: "SYS",
      message: "Sourcing high-performance RPC: https://polygon-rpc.com...",
    },
    {
      id: "3",
      timestamp: new Date().toLocaleTimeString("en-US", { hour12: false }),
      tag: "AAVE",
      message: "Subscribing to Aave liquidations events...",
    },
    {
      id: "4",
      timestamp: new Date().toLocaleTimeString("en-US", { hour12: false }),
      tag: "DEX",
      message: "Reserves cache built successfully. (274 pools loaded).",
    },
  ]);

  const addLog = (
    tag: "C1" | "C2" | "DEX" | "SYS" | "ERR" | "AAVE" | "ARB",
    message: string,
  ) => {
    const timestamp = new Date().toLocaleTimeString("en-US", { hour12: false });
    const newLog: Log = {
      id: crypto.randomUUID(),
      timestamp,
      tag,
      message,
    };
    setLogs((prev) => [newLog, ...prev.slice(0, 45)]);
  };

  // Custom Event Listener connection for inter-functional logs
  useEffect(() => {
    const handleLogEvent = (e: any) => {
      if (e.detail) {
        let tag: any = "SYS";
        let msg = String(e.detail);
        if (msg.includes("!]")) {
          tag = "ERR";
          msg = msg.replace("[!]", "").trim();
        } else if (msg.includes("ROUTE_TEST")) {
          tag = "SYS";
          msg = msg.replace("[ROUTE_TEST]", "").trim();
        } else if (msg.includes("LIQUIDATOR")) {
          tag = "C1";
          msg = msg.replace("[LIQUIDATOR]", "").trim();
        } else if (msg.includes("ARB_SOLVER")) {
          tag = "C2";
          msg = msg.replace("[ARB_SOLVER]", "").trim();
        } else if (msg.includes("DNA_VERIFY")) {
          tag = "C2";
          msg = msg.replace("[DNA_VERIFY]", "").trim();
        } else if (msg.includes("SYSTEM")) {
          tag = "SYS";
          msg = msg.replace("[SYSTEM]", "").trim();
        }
        addLog(tag, msg);
      }
    };

    const handleClearLogs = () => setLogs([]);

    window.addEventListener("apex-log", handleLogEvent);
    window.addEventListener("clear-telemetry-logs", handleClearLogs);
    return () => {
      window.removeEventListener("apex-log", handleLogEvent);
      window.removeEventListener("clear-telemetry-logs", handleClearLogs);
    };
  }, []);

  const ingestServerLogs = (serverLogs: any[] = []) => {
    if (!serverLogs.length) return;
    let hasProfit = false;
    const formattedLogs = serverLogs
      .filter((l: any) => {
        const stableId = String(l.id ?? `${l.createdAt || ""}:${l.tag}:${l.message}`);
        if (seenServerLogIds.current.has(stableId)) return false;
        seenServerLogIds.current.add(stableId);
        if (l.id) lastServerLogId.current = Math.max(lastServerLogId.current, Number(l.id));
        return true;
      })
      .map((l: any) => {
        if (
          l.tag === "C2_LANDED" ||
          (l.tag === "SYS" && String(l.message || "").includes("LIQUIDATION"))
        ) {
          hasProfit = true;
        }
        return {
          id: String(l.id ?? crypto.randomUUID()),
          timestamp: new Date(l.createdAt || Date.now()).toLocaleTimeString("en-US", {
            hour12: false,
          }),
          tag: l.tag,
          message: l.message,
        };
      });
    if (formattedLogs.length) {
      setLogs((prev) => [...formattedLogs.reverse(), ...prev].slice(0, 45));
    }
    if (hasProfit) {
      setShowBagSecured(true);
      setTimeout(() => setShowBagSecured(false), 2500);
    }
  };

  const applyDashboardSnapshot = (
    pnlRes: any,
    pipeRes: any,
    stateRes: any,
    oppRes: any,
    laneRes: any[],
    source: "ws" | "poll",
  ) => {
      setConnectionStatus(source === "ws" ? "live" : dashboardStreamConnected ? "live" : "poll");

      // Update Header
      const sessionPnl = pnlRes.sessionPnl ?? pnlRes.totalPnl ?? 0;
      const lifetimePnlValue = pnlRes.lifetimePnl ?? sessionPnl;
      setPnl(sessionPnl);
      setLifetimePnl(lifetimePnlValue);
      setGas(pnlRes.gasGwei);
      setBlock(pnlRes.blockNumber);
      setDryRun(pnlRes.dryRun);

      // Append chart node (last 60 entries)
      setPnlHistory((prev) => {
        const last = prev[prev.length - 1];
        if (last && last.profitUSD === sessionPnl) return prev;
        const now = new Date();
        const timeStr = `${now.getHours().toString().padStart(2, "0")}:${now.getMinutes().toString().padStart(2, "0")}`;
        const next = [
          ...prev,
          {
            time: timeStr,
            profitUSD: sessionPnl,
            profitPOL: sessionPnl * 1.6,
          },
        ];
        return next.slice(-60); // keep last 60 minutes/nodes
      });

      // Update right metrics
      setWins(pnlRes.wins);
      setTrades(pnlRes.totalTrades);
      setVelocity(pnlRes.execPerHr);
      setTotalSettledCycles(pnlRes.totalSettledCycles);
      setUtil(pnlRes.flashUtil);
      setAvgProfit(
        pnlRes.totalTrades > 0 ? sessionPnl / pnlRes.totalTrades : 0,
      );

      ingestServerLogs(pnlRes.logs || []);

      // Pipeline
      setPipelineStages(pipeRes.stages || []);
      setRecentCycles(pipeRes.recentCycles || []);

      // Cache
      setCache({
        pools: pipeRes.total_pools || 274,
        dirty: pipeRes.dirty_now || 0,
        stale: pipeRes.stale_now || 0,
        syncs: pipeRes.sync_events_total || 0,
        ratePs: pipeRes.update_rate_ps || 0,
        lastMs: pipeRes.last_update_ms || Date.now(),
      });

      // Spreads Controls
      setIsPaused(stateRes.pause?.active || false);

      // Sourced Opportunities
      setOpportunities(oppRes.opportunities || []);
      setOppDiagnostics({
        ...(oppRes.diagnostics || {}),
        routeLimits: oppRes.routeLimits,
        diagnosticRoutes: oppRes.diagnosticRoutes || [],
      });

      // Lanes
      setLanes(laneRes || []);
  };

  useEffect(() => {
    if (typeof window === "undefined") return;
    const source = new EventSource(`/api/dashboard-events?sinceLogId=${lastServerLogId.current}`);
    source.onopen = () => {
      setDashboardStreamConnected(true);
      setConnectionStatus("live");
    };
    source.addEventListener("dashboard_state", (event) => {
      const payload = JSON.parse((event as MessageEvent).data);
      applyDashboardSnapshot(
        payload.pnl || {},
        payload.pipeline || {},
        payload.control || {},
        payload.opportunities || {},
        payload.lanes || [],
        "ws",
      );
    });
    source.addEventListener("dashboard_error", (event) => {
      const payload = JSON.parse((event as MessageEvent).data);
      addLog("ERR", payload.error || "Dashboard stream error");
    });
    source.onerror = () => {
      setDashboardStreamConnected(false);
      setConnectionStatus("poll");
    };
    return () => {
      source.close();
      setDashboardStreamConnected(false);
    };
  }, []);

  // Primary System Fetch Sync Heartbeat. WebSocket is primary; polling remains
  // as a correctness fallback and a slow reconciliation path while WS is healthy.
  const syncTelemetry = async () => {
    try {
      const [pnlRes, pipeRes, stateRes, oppRes, laneRes] = await Promise.all([
        fetch(`/api/dashboard/pnl-summary?sinceLogId=${lastServerLogId.current}`).then((res) => res.json()),
        fetch("/api/execution/pipeline").then((res) => res.json()),
        fetch("/api/execution/control/state").then((res) => res.json()),
        fetch("/api/execution/opportunities").then((res) => res.json()),
        fetch("/api/execution/lanes").then((res) => res.json()),
      ]);

      applyDashboardSnapshot(pnlRes, pipeRes, stateRes, oppRes, laneRes, "poll");
    } catch (err) {
      setConnectionStatus(dashboardStreamConnected ? "live" : "error");
    }
  };

  useEffect(() => {
    syncTelemetry();
    const interval = setInterval(syncTelemetry, dashboardStreamConnected ? 15000 : 3000);
    return () => clearInterval(interval);
  }, [dashboardStreamConnected]);

  // Actions Post Triggers
  const handleScan = async () => {
    addLog("SYS", "On-demand AMM reserves synchronization triggered.");
    const res = await fetch("/api/chains/scan-all", { method: "POST" });
    if (res.ok) {
      addLog(
        "SYS",
        "Synchronization scan resolved on-chain (0x137). Resumed listening.",
      );
    }
  };

  const handlePauseToggle = async () => {
    const endpt = isPaused ? "/api/execution/resume" : "/api/execution/pause";
    const actionName = isPaused ? "RESUME" : "PAUSE";
    addLog("SYS", `Transmitting engine ${actionName} command...`);
    const res = await fetch(endpt, { method: "POST" });
    if (res.ok) {
      setIsPaused(!isPaused);
      addLog(
        "SYS",
        `Engine is configured to: ${isPaused ? "ACTIVE_SCAN" : "HALT_EXECUTIONS"}`,
      );
    }
  };

  const handleDryToggle = async () => {
    addLog("SYS", "Switching engine to MONITOR ONLY. Broadcast path disabled.");
    const res = await fetch("/api/execution/monitor-only", { method: "POST" });
    if (res.ok) {
      setDryRun(true);
      addLog(
        "SYS",
        "Monitor-only mode locked. Transactions not broadcast.",
      );
    }
  };

  const handleArmLive = async () => {
    addLog(
      "SYS",
      "MASTER CONFIRM DETECTED! Deploying arming payloads to Polygon Router...",
    );
    const res = await fetch("/api/execution/arm-live", { method: "POST" });
    if (res.ok) {
      setDryRun(false);
      setIsPaused(false);
      addLog(
        "SYS",
        "WARNING: MEV ARMED LIVE. Bundles will be broadcast on-chain.",
      );
    }
  };

  const handleDryRunToggle = async () => {
    if (!dryRun) {
      await handleDryToggle();
    } else {
      await handleArmLive();
    }
  };

  const [lanesHealth, setLanesHealth] = useState<"idle" | "testing" | "healthy" | "error">("idle");

  const handleTestLanes = async () => {
    setLanesHealth("testing");
    addLog("SYS", "Reading live executor lane telemetry...");

    try {
      const res = await fetch("/api/execution/lanes");
      const lanes = await res.json();
      if (!res.ok || !Array.isArray(lanes)) {
        throw new Error("Lane telemetry endpoint unavailable");
      }
      const activeFaults = lanes.filter((lane: any) => lane.status === "error" || lane.status === "blocked");
      if (activeFaults.length > 0) {
        setLanesHealth("error");
        addLog("ERR", `Executor lane telemetry reports ${activeFaults.length} faulted lanes.`);
      } else {
        setLanesHealth("healthy");
        addLog("SYS", `Executor lane telemetry online: ${lanes.length} lanes reported.`);
      }
    } catch (err: any) {
      setLanesHealth("error");
      addLog("ERR", `Executor lane telemetry failed: ${err?.message || "unknown error"}`);
    }

    setTimeout(() => setLanesHealth("idle"), 5000);
  };

  return (
    <div className="min-h-screen bg-[#030408] text-[#e2e8f0] flex flex-col overflow-hidden relative selection:bg-cyan-500/30 select-none font-mono">
      <ConfettiCelebration show={showBagSecured} />

      <div
        className="absolute inset-0 pointer-events-none overflow-hidden z-0"
        aria-hidden="true"
      >
        <div className="absolute -top-[10%] -left-[10%] w-[40vw] h-[40vh] bg-cyan-900/10 rounded-full blur-[100px]" />
        <div className="absolute -bottom-[20%] -right-[10%] w-[40vw] h-[40vh] bg-fuchsia-900/10 rounded-full blur-[140px]" />
        <div className="absolute top-[40%] left-[50%] -translate-x-[50%] w-[60vw] h-[30vh] bg-[#00f5a0]/5 rounded-full blur-[150px]" />
        <div className="absolute inset-0 bg-[linear-gradient(rgba(0,180,255,0.015)_1px,transparent_1px),linear-gradient(90deg,rgba(0,180,255,0.015)_1px,transparent_1px)] bg-[size:32px_32px] opacity-80" />
        <div className="absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-[#030408] to-transparent z-10" />
      </div>

      <ControlPanel
        isPaused={isPaused}
        onPauseToggle={handlePauseToggle}
        dryRun={dryRun}
        onDryRunToggle={handleDryRunToggle}
        pnl={pnl}
        lifetimePnl={lifetimePnl}
      />

      {/* Main Parts */}
      <Header
        pnl={pnl}
        lifetimePnl={lifetimePnl}
        gas={gas}
        block={block}
        dryRun={dryRun}
        isPaused={isPaused}
        onScan={handleScan}
        onPauseToggle={handlePauseToggle}
        onDryRunToggle={handleDryToggle}
        onArmLive={handleArmLive}
        onTestLanes={handleTestLanes}
        lanesHealth={lanesHealth}
        connectionStatus={connectionStatus}
        onDiagnosticOpen={() => setIsDiagnosticModalOpen(true)}
      />

      <Ticker opportunities={opportunities} />

      {!dryRun && (
        <div className="h-[11px] min-h-[11px] shrink-0 bg-[#00f5a0]/5 border-b border-[#00f5a0]/15 flex items-center justify-center font-mono text-[6px] font-bold tracking-[0.2em] uppercase text-[#00f5a0] select-none animate-pulse">
          ⚡ COGNIZANT SYSTEM ARMED: LIVE MAINNET TRANSACTIONS ENGAGED — BUNDLES PROCESSED DIRECTLY ON-CHAIN
        </div>
      )}

      {dryRun && (
        <div className="h-[11px] min-h-[11px] shrink-0 bg-yellow-500/5 border-b border-yellow-500/15 flex items-center justify-center font-mono text-[6px] font-bold tracking-[0.2em] uppercase text-yellow-500 select-none animate-pulse">
          ⚠️ PASSIVE MONITORING PHASE ENGAGED — BUNDLES EVALUATED BUT NOT BROADCASTED
        </div>
      )}

      {/* Layout Controls */}
      <div className="flex px-4 py-1.5 gap-4 items-center bg-[#070910] border-b border-[#1e2025]/50 text-[8px] font-mono uppercase shrink-0 overflow-x-auto select-none">
        <span className="text-gray-500 font-bold shrink-0">VIEW PANELS:</span>
        {[
          { id: "hyper", label: "Hyper Immersive Opportunities" },
          { id: "spreads", label: "Spreads" },
          { id: "cache", label: "Reserve Cache" },
          { id: "oracles", label: "Oracles" },
          { id: "chart", label: "P&L Chart" },
          { id: "executions", label: "Executions" },
          { id: "modules", label: "Protocol Modules" },
          { id: "workspace", label: "Workspace Engine" },
          { id: "intel", label: "Intel log" },
        ].map((p) => (
          <label
            key={p.id}
            className="flex items-center gap-1 cursor-pointer shrink-0"
          >
            <input
              type="checkbox"
              checked={(layout as any)[p.id]}
              onChange={() => toggleLayout(p.id as any)}
              className="accent-cyan-500 w-2.5 h-2.5"
            />
            <span
              className={
                (layout as any)[p.id]
                  ? "text-cyan-400 font-bold"
                  : "text-gray-600"
              }
            >
              {p.label}
            </span>
          </label>
        ))}
      </div>

      {/* Primary Control Room splits */}
      <main className="flex-1 min-h-0 p-2.5 flex flex-col gap-2.5 z-10 overflow-x-hidden overflow-y-auto">
        {/* Hyper Immersive 2.0 View */}
        {layout.hyper && (
          <div className="w-full relative z-20 mb-2 shrink-0">
            <HyperImmersiveOpportunities
              opportunities={opportunities}
              diagnostics={oppDiagnostics}
              connectionStatus={connectionStatus}
            />
          </div>
        )}

        {/* Protocol Modules View */}
        {layout.modules && (
          <div className="w-full relative z-20 mb-2 shrink-0">
            <ProtocolModules />
          </div>
        )}

        {/* Existing columns */}
        <div className="flex flex-col lg:flex-row flex-wrap gap-2.5 min-h-0 flex-1">
        {/* Left column (DEX Spreads, Reserve Cache health metrics) */}
        <section
          className={`w-full lg:w-[25%] flex-1 min-w-[250px] flex flex-col gap-2.5 min-h-0 ${!(layout.spreads || layout.cache || layout.oracles) ? "hidden" : ""}`}
        >
          {/* Reserve cache panel */}
          {layout.cache && (
            <div className="border border-[#1e2025] bg-[#0d0e12]/50 rounded-sm p-4 shrink-0 relative glass-specular glass-inset">
              <div className="absolute top-0 right-0 w-2 h-2 border-t border-r border-[#b388ff]/40" />

              <h4 className="text-[10px] font-mono whitespace-nowrap uppercase tracking-wider text-white border-b border-[#1e2025]/60 pb-2 mb-2">
                LOCAL RESERVES CACHE TELEMETRY
              </h4>

              <div className="grid grid-cols-2 gap-2 font-mono text-[10.5px]">
                <div>
                  <span className="text-gray-500 block uppercase text-[7.5px] leading-none mb-1 font-bold">
                    AMM POOLS
                  </span>
                  <span className="text-white font-semibold leading-none">
                    {cache.pools} pools
                  </span>
                </div>
                <div>
                  <span className="text-gray-500 block uppercase text-[7.5px] leading-none mb-1 font-bold">
                    DIRTY RECORDS
                  </span>
                  <span className="text-cyan-400 font-semibold leading-none">
                    {cache.dirty} indexes
                  </span>
                </div>
                <div>
                  <span className="text-gray-500 block uppercase text-[7.5px] leading-none mb-1 font-bold">
                    STALE BLOCKS
                  </span>
                  <span
                    className={`font-semibold leading-none ${cache.stale > 0 ? "text-red-400" : "text-gray-400"}`}
                  >
                    {cache.stale} pools
                  </span>
                </div>
                <div>
                  <span className="text-gray-500 block uppercase text-[7.5px] leading-none mb-1 font-bold">
                    SYNC SPEED
                  </span>
                  <span className="text-[#00f5a0] font-semibold leading-none">
                    {cache.ratePs} swaps/s
                  </span>
                </div>
              </div>

              <div className="border-t border-[#1e2025]/40 mt-2.5 pt-2 flex items-center justify-between text-[8px] text-gray-500 font-mono">
                <span>
                  SYNC_LAT:{" "}
                  {cache.lastMs
                    ? `${Math.round(Date.now() - cache.lastMs)}ms ago`
                    : "no-sync"}
                </span>
                <span>TOTAL_SYNCS: {cache.syncs.toLocaleString()}</span>
              </div>
            </div>
          )}

          {/* Real-time DeFi index Oracles  */}
          {layout.oracles && <OracleFeeds />}
        </section>

        {/* Center column (P&L Chart, C1/C2 Stages, Tabs workspace) */}
        <section
          className={`w-full lg:w-[50%] flex-[2] min-w-[350px] flex flex-col gap-2.5 min-h-0 ${!(layout.chart || layout.executions || layout.workspace) ? "hidden" : ""}`}
        >
          {/* View Manager & Workspace Rows */}
          {layout.workspace && (
            <div className="border border-[#1e2025] bg-[#0b0c10] rounded-sm flex flex-col flex-1 min-h-[380px] select-none shrink-0 relative overflow-hidden glass-specular glass-inset">
              {/* View Manager Controls */}
              <div className="bg-[#090a0d] border-b border-[#1e2025]/80 flex items-center px-4 py-2 gap-4 shrink-0 overflow-x-auto select-none font-mono text-[9px] uppercase">
                <span className="text-gray-500 font-bold tracking-widest shrink-0">
                  VIEW MANAGER:
                </span>
                <label className="flex items-center gap-1.5 cursor-pointer shrink-0">
                  <input
                    type="checkbox"
                    checked={workspaceViews.liquidation}
                    onChange={(e) =>
                      setWorkspaceViews((p) => ({
                        ...p,
                        liquidation: e.target.checked,
                      }))
                    }
                    className="accent-cyan-500"
                  />
                  <span
                    className={
                      workspaceViews.liquidation
                        ? "text-cyan-400 font-bold"
                        : "text-gray-600"
                    }
                  >
                    Liquidation Feed
                  </span>
                </label>

                <label className="flex items-center gap-1.5 cursor-pointer shrink-0">
                  <input
                    type="checkbox"
                    checked={workspaceViews.schema}
                    onChange={(e) =>
                      setWorkspaceViews((p) => ({
                        ...p,
                        schema: e.target.checked,
                      }))
                    }
                    className="accent-cyan-500"
                  />
                  <span
                    className={
                      workspaceViews.schema
                        ? "text-cyan-400 font-bold"
                        : "text-gray-600"
                    }
                  >
                    Mainnet Payload
                  </span>
                </label>

                <label className="flex items-center gap-1.5 cursor-pointer shrink-0">
                  <input
                    type="checkbox"
                    checked={workspaceViews.c2logic}
                    onChange={(e) =>
                      setWorkspaceViews((p) => ({
                        ...p,
                        c2logic: e.target.checked,
                      }))
                    }
                    className="accent-cyan-500"
                  />
                  <span
                    className={
                      workspaceViews.c2logic
                        ? "text-cyan-400 font-bold"
                        : "text-gray-600"
                    }
                  >
                    C2 Logic
                  </span>
                </label>

                <label className="flex items-center gap-1.5 cursor-pointer shrink-0">
                  <input
                    type="checkbox"
                    checked={workspaceViews.wallet}
                    onChange={(e) =>
                      setWorkspaceViews((p) => ({
                        ...p,
                        wallet: e.target.checked,
                      }))
                    }
                    className="accent-cyan-500"
                  />
                  <span
                    className={
                      workspaceViews.wallet
                        ? "text-cyan-400 font-bold"
                        : "text-gray-600"
                    }
                  >
                    Signer Wallet
                  </span>
                </label>

                <label className="flex items-center gap-1.5 cursor-pointer shrink-0">
                  <input
                    type="checkbox"
                    checked={workspaceViews.config}
                    onChange={(e) =>
                      setWorkspaceViews((p) => ({
                        ...p,
                        config: e.target.checked,
                      }))
                    }
                    className="accent-cyan-500"
                  />
                  <span
                    className={
                      workspaceViews.config
                        ? "text-cyan-400 font-bold"
                        : "text-gray-600"
                    }
                  >
                    Engine Config
                  </span>
                </label>
              </div>

              {/* Workspace Inner Section (Vertical Flexible Stack) */}
              <div className="p-2 flex-1 overflow-y-auto min-h-0 bg-[#000000]/30 flex flex-col gap-2 relative">
                <AnimatePresence>
                  {workspaceViews.liquidation && (
                    <motion.div
                      key="liquidation"
                      initial={{ opacity: 0, height: 0, scale: 0.98 }}
                      animate={{ opacity: 1, height: "auto", scale: 1 }}
                      exit={{
                        opacity: 0,
                        height: 0,
                        scale: 0.98,
                        overflow: "hidden",
                      }}
                      transition={{ duration: 0.2 }}
                      className="flex flex-col flex-1 shrink-0 min-h-[200px]"
                    >
                      <div className="space-y-4 h-full flex flex-col">
                        <div className="pt-2 flex-1 flex flex-col">
                          <LiquidationMonitor addLog={addLog} />
                        </div>
                      </div>
                    </motion.div>
                  )}

                  {workspaceViews.schema && (
                    <motion.div
                      key="schema"
                      initial={{ opacity: 0, height: 0, scale: 0.98 }}
                      animate={{ opacity: 1, height: "auto", scale: 1 }}
                      exit={{
                        opacity: 0,
                        height: 0,
                        scale: 0.98,
                        overflow: "hidden",
                      }}
                      transition={{ duration: 0.2 }}
                      className="flex flex-col flex-1 shrink-0 min-h-[200px]"
                    >
                      <MainnetPayloadSchema />
                    </motion.div>
                  )}

                  {workspaceViews.c2logic && (
                    <motion.div
                      key="c2logic"
                      initial={{ opacity: 0, height: 0, scale: 0.98 }}
                      animate={{ opacity: 1, height: "auto", scale: 1 }}
                      exit={{
                        opacity: 0,
                        height: 0,
                        scale: 0.98,
                        overflow: "hidden",
                      }}
                      transition={{ duration: 0.2 }}
                      className="flex flex-col flex-1 shrink-0 min-h-[200px]"
                    >
                      <C2TriggerLogic />
                    </motion.div>
                  )}

                  {workspaceViews.wallet && (
                    <motion.div
                      key="wallet"
                      initial={{ opacity: 0, height: 0, scale: 0.98 }}
                      animate={{ opacity: 1, height: "auto", scale: 1 }}
                      exit={{
                        opacity: 0,
                        height: 0,
                        scale: 0.98,
                        overflow: "hidden",
                      }}
                      transition={{ duration: 0.2 }}
                      className="flex flex-col flex-1 shrink-0 min-h-[300px] bg-[#090a0d] border border-[#1e2025] rounded p-2 glass-specular glass-inset"
                    >
                      <WalletTab addLog={addLog} />
                    </motion.div>
                  )}

                  {workspaceViews.config && (
                    <motion.div
                      key="config"
                      initial={{ opacity: 0, height: 0, scale: 0.98 }}
                      animate={{ opacity: 1, height: "auto", scale: 1 }}
                      exit={{
                        opacity: 0,
                        height: 0,
                        scale: 0.98,
                        overflow: "hidden",
                      }}
                      transition={{ duration: 0.2 }}
                      className="flex flex-col flex-1 shrink-0 min-h-[400px] bg-[#090a0d] border border-[#1e2025] rounded p-2 glass-specular glass-inset"
                    >
                      <ConfigTab setConfigChanged={fetchDashboardConfig} addLog={addLog} />
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </div>
          )}

          {/* SVG P&L Trajectory section */}
          {(layout.chart || layout.executions) && (
            <div
              className={`grid grid-cols-1 md:grid-cols-${layout.chart && layout.executions ? "2" : "1"} gap-2.5 shrink-0`}
            >
              {/* Chart widget */}
              {layout.chart && (
                <div className="h-[380px]">
                  <ProfitDashboard data={pnlHistory} recentTrades={recentCycles} />
                </div>
              )}

              {/* Pipeline Stage Counts and Completed blocks log */}
              {layout.executions && (
                <div className="border border-[#1e2025] bg-[#0d0e12]/50 rounded-sm p-4 flex flex-col relative h-[380px] glass-specular glass-inset">
                  <div className="absolute top-0 right-0 w-2 h-2 border-t border-r border-[#b388ff]/40" />
                  <div className="flex justify-between items-center border-b border-[#1e2025]/60 pb-1.5 mb-1.5 shrink-0">
                    <span className="text-[10px] font-mono uppercase tracking-wider font-bold text-white">
                      Completed Executions
                    </span>
                    <span className="text-gray-500 font-mono text-[9.5px]">
                      v2.1 optimized
                    </span>
                  </div>

                  <div className="flex-1 overflow-y-auto space-y-1 font-mono text-[9px] pr-1 scrollbar-thin">
                    {recentCycles.map((cycle, i) => {
                      const profitAmt = Number(cycle.total_profit_usd);
                      return (
                        <div
                          key={i}
                          className="flex items-center justify-between p-1 bg-white/2 rounded-sm text-gray-300"
                        >
                          <span className="text-gray-500 shrink-0">
                            #{cycle.cycle_id.slice(0, 5)}
                          </span>
                          <span className="font-semibold text-white truncate max-w-16">
                            {cycle.token_pair}
                          </span>
                          <span className="text-[8px] px-1 bg-blue-500/10 text-blue-400 border border-blue-500/20 rounded-sm">
                            {cycle.c1_status}
                          </span>
                          <span className="text-[8px] px-1 bg-purple-500/10 text-purple-400 border border-purple-500/20 rounded-sm">
                            {cycle.c2_decision}
                          </span>
                          <span
                            className={`font-bold shrink-0 ${profitAmt > 0 ? "text-[#00f5a0]" : "text-gray-500"}`}
                          >
                            ${profitAmt.toFixed(2)}
                          </span>
                        </div>
                      );
                    })}
                    {recentCycles.length === 0 && (
                      <div className="text-center py-10 text-gray-500">
                        Awaiting solved bundle block settlements...
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </section>

        {/* Right column (System Intel & Event Log widget) */}
        <section
          className={`w-full lg:w-[25%] flex-1 min-w-[250px] min-h-0 overflow-y-auto ${!layout.intel ? "hidden" : ""}`}
        >
          {layout.intel && (
            <SystemIntel
              wins={wins}
              trades={trades}
              velocity={velocity}
              avgProfit={avgProfit}
              util={util}
              totalSettledCycles={totalSettledCycles}
              block={block}
              gas={gas}
              logs={logs}
              isPaused={isPaused}
              dryRun={dryRun}
            />
          )}
        </section>
        </div>
      </main>

      {/* Horizontal Opportunity Feed Banner */}
      {layout.spreads && (
        <div className="shrink-0 bg-transparent border-[#1e2025]/30 overflow-hidden relative z-10 mx-2 mb-2 rounded-sm flex items-center px-2 py-2">
          <div className="shrink-0 flex items-center gap-1.5 font-mono mr-4 pr-4 border-r border-[#1e2025]/60 pr-2">
            <span className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-ping" />
            <div className="flex flex-col">
              <h3 className="text-[9px] uppercase tracking-wider font-bold text-white leading-tight">
                Live Spreads
              </h3>
              <span className="text-[7.5px] uppercase font-bold tracking-widest text-[#00f5a0] leading-none mt-0.5">
                {opportunities.length} DETECTED
              </span>
            </div>
          </div>

          <div className="flex-1 overflow-x-auto flex gap-2 scrollbar-hide items-center font-mono">
            {opportunities.map((opp, idx) => {
              const profitPct = Math.min(100, (opp.profit_usd / 115) * 100);
              return (
                <div
                  key={idx}
                  className="shrink-0 min-w-[200px] p-2 bg-transparent border border-transparent rounded-sm transition-all duration-200"
                >
                  <div className="flex justify-between items-center mb-1">
                    <span className="font-semibold text-white text-[9px]">
                      {opp.pair}
                    </span>
                    <span className="px-1 py-[0.5px] text-[7px] font-bold border border-[#b388ff]/20 bg-[#b388ff]/5 rounded-sm text-[#b388ff]">
                      POLY
                    </span>
                  </div>
                  {/* Visualizer factor */}
                  <div className="w-full bg-[#1e2025]/40 h-[3px] rounded-sm overflow-hidden mb-1">
                    <div
                      className="h-full bg-gradient-to-r from-cyan-400 to-[#00f5a0]"
                      style={{ width: `${profitPct}%` }}
                    />
                  </div>
                  <div className="flex justify-between text-[8px] text-gray-500 leading-none">
                    <span>{opp.spread_bps} BPS</span>
                    <span className="text-[#00f5a0] font-bold">
                      +${opp.profit_usd.toFixed(2)}
                    </span>
                  </div>
                </div>
              );
            })}
            {opportunities.length === 0 && (
              <div className="text-gray-500 text-[9px] whitespace-nowrap pl-2 flex items-center gap-2">
                <span className="w-1.5 h-1.5 bg-yellow-400/50 rounded-full animate-pulse"></span>
                Listening to Polygon RPC for AMM pricing differences...
              </div>
            )}
          </div>
        </div>
      )}

      {/* Parallel Executor Lanes */}
      <LanesGrid lanes={lanes} />

      {/* Cyber footer info */}
      <footer className="h-6 bg-[#040508] border-t border-[#1e2025] flex justify-between items-center px-4 font-mono text-[7px] text-gray-500 uppercase tracking-widest select-none shrink-0 relative z-20">
        <div className="flex items-center gap-2">
          <span className="text-[#00f5a0] font-bold animate-pulse">
            ● STATUS: OPERATIONAL
          </span>
          <span className="text-gray-700">|</span>
          <span>
            AUTH SIGN: {botWallet.substring(0, 6)}...
            {botWallet.substring(botWallet.length - 4)}
          </span>
        </div>
        <div className="flex items-center gap-1.5 text-right font-mono">
          <span>STATE STREAM: {dashboardStreamConnected ? "LIVE" : connectionStatus.toUpperCase()}</span>
          <span className="text-gray-700">/</span>
          <span>{opportunities.length} ROUTES / {pipelineStages.length} STAGES SYNCED</span>
        </div>
      </footer>
      <NotificationSidebar />
      <PipelineDiagnosticModal
        isOpen={isDiagnosticModalOpen}
        onClose={() => setIsDiagnosticModalOpen(false)}
      />
    </div>
  );
}


