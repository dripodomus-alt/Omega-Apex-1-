import { useState, useEffect } from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend
} from "recharts";
import { Brain, Cpu, TrendingUp, Zap, Sparkles, RefreshCw, Play } from "lucide-react";

type Props = {
  client: any;
};

export function MLProgressWidget({ client }: Props) {
  const [history, setHistory] = useState<any[]>([]);
  const [status, setStatus] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [training, setTraining] = useState(false);
  const [error, setError] = useState("");
  const [successMsg, setSuccessMsg] = useState("");

  const fetchData = async () => {
    setLoading(true);
    setError("");
    try {
      const [historyRes, statusRes] = await Promise.all([
        client.getMlHistory(),
        client.getMlStatus()
      ]);
      if (historyRes.ok) setHistory(historyRes.history);
      if (statusRes.ok) setStatus(statusRes);
    } catch (err: any) {
      setError(err.message || "Failed to load ML model telemetry");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const runTrainingLoop = async () => {
    if (training) return;
    setTraining(true);
    setError("");
    setSuccessMsg("");
    try {
      // Simulate real-time training epoch run
      const res = await client.triggerMlTraining();
      if (res.ok) {
        setSuccessMsg(`Episode ${res.new_episode.episode} training completed!`);
        // Refresh telemetry
        const [historyRes, statusRes] = await Promise.all([
          client.getMlHistory(),
          client.getMlStatus()
        ]);
        if (historyRes.ok) setHistory(historyRes.history);
        if (statusRes.ok) setStatus(statusRes);
        
        // Clear message after 4s
        setTimeout(() => setSuccessMsg(""), 4000);
      }
    } catch (err: any) {
      setError(err.message || "Reinforcement learning execution failed");
    } finally {
      setTraining(false);
    }
  };

  const latest = history[history.length - 1] || {};

  return (
    <div 
      id="ml-progress-widget"
      className="bg-[#0b0f17] border border-[#1e293b] rounded-lg p-5 shadow-lg relative overflow-hidden"
    >
      {/* Visual background grid texture */}
      <div className="absolute inset-0 bg-[radial-gradient(#1e293b_1px,transparent_1px)] [background-size:16px_16px] opacity-10 pointer-events-none" />

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6 relative z-10">
        <div>
          <div className="flex items-center gap-2">
            <div className="p-1.5 bg-[#0f172a] border border-[#3b82f6] rounded-md text-[#3b82f6]">
              <Brain className="w-5 h-5 animate-pulse" />
            </div>
            <h3 className="text-sm font-bold text-slate-100 uppercase tracking-wider">
              ML Alpha Ranker Telemetry
            </h3>
            <span className="bg-[#10b981]/10 text-[#10b981] border border-[#10b981]/30 px-2 py-0.5 rounded text-[10px] font-extrabold">
              ONLINE
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Success Rate and Gas Routing Efficiency trajectory modeled over sequential trading episodes
          </p>
        </div>

        <div className="flex gap-2">
          <button
            onClick={fetchData}
            disabled={loading || training}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[#0f172a] hover:bg-[#1e293b] text-slate-300 border border-[#1e293b] rounded-md text-xs font-semibold cursor-pointer disabled:opacity-50 transition"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            Sync
          </button>

          <button
            onClick={runTrainingLoop}
            disabled={training}
            className="flex items-center gap-1.5 px-4 py-1.5 bg-[#2563eb] hover:bg-[#1d4ed8] text-white border border-[#3b82f6] rounded-md text-xs font-bold cursor-pointer disabled:opacity-50 transition shadow-[0_0_10px_rgba(59,130,246,0.2)]"
          >
            {training ? (
              <>
                <Cpu className="w-3.5 h-3.5 animate-spin" />
                Training...
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5" />
                Reinforce Engine
              </>
            )}
          </button>
        </div>
      </div>

      {/* Status Indicators & Alerts */}
      {error && (
        <div className="bg-[#451a1a] border border-[#991b1b] text-[#ff8080] text-xs px-3 py-2 rounded-md mb-4 relative z-10">
          {error}
        </div>
      )}

      {successMsg && (
        <div className="bg-[#064e3b] border border-[#10b981] text-[#34d399] text-xs px-3 py-2 rounded-md mb-4 flex items-center gap-2 relative z-10 animate-fade-in">
          <Sparkles className="w-4 h-4 text-[#34d399] shrink-0" />
          <span>{successMsg}</span>
        </div>
      )}

      {/* Interactive KPI Metrics Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6 relative z-10">
        <div className="bg-[#0f172a] border border-[#1e293b] p-3 rounded-lg flex flex-col justify-between">
          <span className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider block">
            Success Rate
          </span>
          <div className="flex items-baseline gap-1.5 mt-1.5">
            <span className="text-lg font-extrabold text-[#10b981]">
              {latest.success_rate ? `${latest.success_rate}%` : "—"}
            </span>
            <span className="text-[10px] text-slate-400">Target 95%+</span>
          </div>
          <div className="w-full bg-slate-800 h-1 rounded-full mt-2 overflow-hidden">
            <div 
              className="bg-[#10b981] h-1 rounded-full transition-all duration-1000"
              style={{ width: `${latest.success_rate || 0}%` }}
            />
          </div>
        </div>

        <div className="bg-[#0f172a] border border-[#1e293b] p-3 rounded-lg flex flex-col justify-between">
          <span className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider block">
            Gas Efficiency
          </span>
          <div className="flex items-baseline gap-1.5 mt-1.5">
            <span className="text-lg font-extrabold text-[#3b82f6]">
              {latest.gas_efficiency ? `${latest.gas_efficiency}%` : "—"}
            </span>
            <span className="text-[10px] text-slate-400">Target 98%+</span>
          </div>
          <div className="w-full bg-slate-800 h-1 rounded-full mt-2 overflow-hidden">
            <div 
              className="bg-[#3b82f6] h-1 rounded-full transition-all duration-1000"
              style={{ width: `${latest.gas_efficiency || 0}%` }}
            />
          </div>
        </div>

        <div className="bg-[#0f172a] border border-[#1e293b] p-3 rounded-lg flex flex-col justify-between">
          <span className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider block">
            Average Gas / Tx
          </span>
          <div className="flex items-baseline gap-1 mt-1.5">
            <span className="text-lg font-extrabold text-[#f59e0b]">
              {latest.avg_gas_used ? latest.avg_gas_used.toLocaleString() : "—"}
            </span>
            <span className="text-[10px] text-slate-400 font-mono">gas</span>
          </div>
          <span className="text-[9px] text-slate-500 mt-2 block">
            Lower is better (routing optimal)
          </span>
        </div>

        <div className="bg-[#0f172a] border border-[#1e293b] p-3 rounded-lg flex flex-col justify-between">
          <span className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider block">
            Current Loss
          </span>
          <div className="flex items-baseline gap-1.5 mt-1.5">
            <span className="text-lg font-extrabold text-purple-400">
              {latest.loss ? latest.loss.toFixed(3) : "—"}
            </span>
            <span className="text-[10px] text-slate-400">Epoch {latest.episode || 0}</span>
          </div>
          <span className="text-[9px] text-slate-500 mt-2 block">
            Minimizing risk-entropy surface
          </span>
        </div>
      </div>

      {/* Main Chart Section */}
      <div className="bg-[#080c14] border border-[#1e293b] rounded-lg p-3 relative z-10">
        <div className="flex items-center justify-between mb-3 px-1">
          <div className="flex items-center gap-1">
            <TrendingUp className="w-4 h-4 text-emerald-400" />
            <span className="text-xs font-bold text-slate-300">Learning Progress Over Time</span>
          </div>
          <span className="text-[10px] text-slate-400">
            Model: <strong className="text-slate-200 font-mono">{status?.model || "xgboost_v5"}</strong>
          </span>
        </div>

        <div className="w-full h-[240px]">
          {history.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={history}
                margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis 
                  dataKey="episode" 
                  stroke="#64748b" 
                  fontSize={10} 
                  tickLine={false}
                  label={{ value: "Episode (Blocks Scanned)", position: "insideBottom", offset: -5, fill: "#64748b", fontSize: 10 }}
                />
                <YAxis 
                  stroke="#64748b" 
                  fontSize={10} 
                  tickLine={false} 
                  domain={[60, 100]}
                />
                <Tooltip 
                  contentStyle={{ 
                    backgroundColor: "#0f172a", 
                    borderColor: "#1e293b", 
                    borderRadius: "6px" 
                  }}
                  itemStyle={{ fontSize: "12px" }}
                  labelStyle={{ color: "#94a3b8", fontSize: "11px", fontWeight: "bold" }}
                />
                <Legend 
                  wrapperStyle={{ fontSize: "10px", marginTop: "10px" }}
                  iconSize={8}
                />
                <Line
                  name="Success Rate (%)"
                  type="monotone"
                  dataKey="success_rate"
                  stroke="#10b981"
                  strokeWidth={2.5}
                  dot={{ r: 3, stroke: "#10b981", strokeWidth: 1, fill: "#0b0f17" }}
                  activeDot={{ r: 5 }}
                />
                <Line
                  name="Gas Efficiency (%)"
                  type="monotone"
                  dataKey="gas_efficiency"
                  stroke="#3b82f6"
                  strokeWidth={2.5}
                  dot={{ r: 3, stroke: "#3b82f6", strokeWidth: 1, fill: "#0b0f17" }}
                  activeDot={{ r: 5 }}
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="w-full h-full flex items-center justify-center text-xs text-slate-500">
              {loading ? "Loading telemetry charts..." : "No ML telemetry data loaded"}
            </div>
          )}
        </div>
      </div>

      {/* Extra Telemetry Footer */}
      <div className="mt-4 pt-4 border-t border-[#1e293b] flex flex-wrap justify-between items-center gap-2 text-[10px] text-slate-400 relative z-10">
        <div className="flex gap-4">
          <span>Active features: <strong className="text-slate-300">18 parameters</strong></span>
          <span>Last trained: <strong className="text-slate-300">Just now (Reinforced)</strong></span>
        </div>
        <div>
          <span>Targeting block limit: <strong className="text-[#3b82f6]">Polygon-Bor BorHead</strong></span>
        </div>
      </div>
    </div>
  );
}
