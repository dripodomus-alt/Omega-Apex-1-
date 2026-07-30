import React, { useState, useEffect } from "react";
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Cell,
} from "recharts";
import {
  BrainCircuit,
  TrendingUp,
  TrendingDown,
  Calendar,
  AlertTriangle,
  Zap,
  Rocket,
} from "lucide-react";

interface SentimentData {
  time: string;
  globalSentiment: number;
  fearAndGreed: number;
}

interface TokenLaunch {
  symbol: string;
  name: string;
  timeToLaunch: string;
  aiConfidence: number;
  predictedVolatility: string;
  mevOpportunity: string;
  status: "PENDING" | "LIVE" | "ANALYZING";
}

interface EconEvent {
  event: string;
  impact: "HIGH" | "MEDIUM" | "LOW";
  time: string;
  aiAssessment: string;
}

export default function EconomicSentimentWidget() {
  const [sentimentHistory, setSentimentHistory] = useState<SentimentData[]>([]);
  const [currentScore, setCurrentScore] = useState<number>(74);
  const [aiAssessmentLatest, setAiAssessmentLatest] = useState<string>("");

  const [launches, setLaunches] = useState<TokenLaunch[]>([
    {
      symbol: "EIGEN",
      name: "EigenLayer",
      timeToLaunch: "T-04:20:00",
      aiConfidence: 94,
      predictedVolatility: "EXTREME",
      mevOpportunity: "HIGH",
      status: "PENDING",
    },
    {
      symbol: "BERA",
      name: "Berachain",
      timeToLaunch: "T-12:00:00",
      aiConfidence: 88,
      predictedVolatility: "HIGH",
      mevOpportunity: "HIGH",
      status: "PENDING",
    },
    {
      symbol: "ZRO",
      name: "LayerZero",
      timeToLaunch: "LIVE (0m ago)",
      aiConfidence: 99,
      predictedVolatility: "EXTREME",
      mevOpportunity: "CRITICAL",
      status: "LIVE",
    },
    {
      symbol: "BLAST",
      name: "Blast",
      timeToLaunch: "T-48:00:00",
      aiConfidence: 75,
      predictedVolatility: "MEDIUM",
      mevOpportunity: "MEDIUM",
      status: "ANALYZING",
    },
  ]);
  const [events, setEvents] = useState<EconEvent[]>([
    {
      event: "FOMC Rate Decision",
      impact: "HIGH",
      time: "14:00 EST",
      aiAssessment:
        "Hawkish lean expected. Arbitrage spreads likely to widen +/- 400bps during event.",
    },
    {
      event: "CPI Print",
      impact: "HIGH",
      time: "08:30 EST",
      aiAssessment:
        "Market pricing in 3.1%. Deviations >0.2% will trigger high-frequency C1-C2 rebalancing.",
    },
    {
      event: "ECB Press Conference",
      impact: "MEDIUM",
      time: "08:45 EST",
      aiAssessment:
        "Monitor EUR/USD correlated pools. Moderate liquidity shifts expected.",
    },
  ]);

  useEffect(() => {
    setSentimentHistory([]);

    // Fetch live sentiment analysis specifically from backend
    const fetchSentiment = async () => {
      try {
        const res = await fetch("/api/sentiment");
        const data = await res.json();
        if (data.success) {
          setCurrentScore(data.score);
          if (data.aiAssessment) setAiAssessmentLatest(data.aiAssessment);
        }
      } catch (e) {
        console.error("Failed fetching sentiment:", e);
      }
    };

    fetchSentiment();
    // Refresh every 15 minutes
    const interval = setInterval(fetchSentiment, 15 * 60 * 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="h-full flex flex-col font-mono text-[10px] space-y-4">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-[#1e2025] pb-2 px-1">
        <BrainCircuit size={16} className="text-purple-400" />
        <h2 className="font-bold text-gray-300 uppercase tracking-wider text-sm flex-1">
          MACRO INTEL & AI SENTIMENT LAYER
        </h2>
        <div className="flex items-center gap-4 text-[9px] uppercase font-bold">
          <div className="flex items-center gap-1.5">
            <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />{" "}
            NETWORK NEURAL ENGINE: ONLINE
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 flex-1 min-h-0">
        {/* Left Column: AI Sentiment Graph */}
        <div className="lg:col-span-6 flex flex-col h-full bg-[#07080a] border border-[#1e2025] rounded-sm relative glass-specular glass-inset">
          <div className="absolute top-0 right-0 w-3 h-3 border-t border-r border-purple-500/50" />
          <div className="flex justify-between items-center p-3 border-b border-[#1e2025] bg-[#0d0e12]">
            <span className="font-bold text-white uppercase tracking-wider">
              Predictive Sentiment Oscillator
            </span>
            <div className="flex gap-4">
              <span className="flex items-center gap-1 text-purple-400">
                <div className="w-2 h-2 bg-purple-500 rounded-sm" /> Global
                Sentiment
              </span>
              <span className="flex items-center gap-1 text-orange-400">
                <div className="w-2 h-2 bg-orange-500 rounded-sm" /> Fear/Greed
                Index
              </span>
            </div>
          </div>
          <div className="flex-1 w-full p-4 h-[150px] min-h-[150px] relative">
            <ResponsiveContainer
              width="100%"
              height="100%"
              minWidth={1}
              minHeight={1}
            >
              <AreaChart
                data={sentimentHistory}
                margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
              >
                <defs>
                  <linearGradient
                    id="colorSentiment"
                    x1="0"
                    y1="0"
                    x2="0"
                    y2="1"
                  >
                    <stop offset="5%" stopColor="#a855f7" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#a855f7" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="colorFear" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#f97316" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#f97316" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid
                  strokeDasharray="2 2"
                  stroke="#1e2025"
                  vertical={false}
                />
                <XAxis
                  dataKey="time"
                  tick={{ fill: "#6b7280", fontSize: 9 }}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis
                  tick={{ fill: "#6b7280", fontSize: 9 }}
                  tickLine={false}
                  axisLine={false}
                  domain={[0, 100]}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#0b0c10",
                    borderColor: "#1e2025",
                    fontSize: "10px",
                  }}
                  itemStyle={{ fontSize: "10px" }}
                />
                <Area
                  type="monotone"
                  dataKey="globalSentiment"
                  stroke="#a855f7"
                  strokeWidth={2}
                  fill="url(#colorSentiment)"
                />
                <Area
                  type="monotone"
                  dataKey="fearAndGreed"
                  stroke="#f97316"
                  strokeWidth={2}
                  fill="url(#colorFear)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Center Column: Sentiment Gauge and API Keys Explanation */}
        <div className="lg:col-span-3 flex flex-col h-full bg-[#07080a] border border-[#1e2025] rounded-sm glass-specular glass-inset">
          <div className="p-3 border-b border-[#1e2025] bg-[#0d0e12] flex justify-between items-center">
            <span className="font-bold text-white uppercase tracking-wider">
              Net Volatility Vector
            </span>
          </div>
          <div className="flex-1 flex flex-col items-center justify-center p-4">
            {/* Radial Gauge SVG */}
            <div className="relative w-32 h-32 mb-4">
              <svg
                viewBox="0 0 100 100"
                className="w-full h-full transform -rotate-90"
              >
                <circle
                  cx="50"
                  cy="50"
                  r="40"
                  fill="transparent"
                  stroke="#1e2025"
                  strokeWidth="8"
                />
                <circle
                  cx="50"
                  cy="50"
                  r="40"
                  fill="transparent"
                  stroke="#8b5cf6"
                  strokeWidth="8"
                  strokeDasharray="251.2"
                  strokeDashoffset={251.2 * (1 - currentScore / 100)}
                  strokeLinecap="round"
                  className="drop-shadow-[0_0_8px_rgba(139,92,246,0.8)]"
                />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-2xl font-bold text-white">
                  {currentScore}
                  <span className="text-sm text-purple-400">%</span>
                </span>
                <span className="text-[8px] text-gray-500 uppercase">
                  {currentScore > 70 ? "High Vol" : "Stable"}
                </span>
              </div>
            </div>

            <div className="w-full bg-[#0b0c10] border border-[#1e2025] rounded p-2 overflow-y-auto max-h-[160px] custom-scrollbar">
              <h3 className="text-cyan-400 font-bold mb-1 border-b border-[#1e2025] pb-1 uppercase tracking-wider text-[8px]">
                Intelligence Configuration
              </h3>
              <div className="text-gray-400 text-[8px] leading-relaxed space-y-1">
                <p>
                  <strong className="text-gray-300">Required Keys:</strong>{" "}
                  <span className="font-mono bg-purple-500/10 text-purple-400 px-1 rounded">
                    NEWS_API_KEY
                  </span>{" "}
                  /{" "}
                  <span className="font-mono bg-blue-500/10 text-blue-400 px-1 rounded">
                    RSS
                  </span>{" "}
                  (Ingestion) +{" "}
                  <span className="font-mono bg-emerald-500/10 text-emerald-400 px-1 rounded">
                    GEMINI_API_KEY
                  </span>{" "}
                  (LLM Semantics) mapped in{" "}
                  <span className="font-mono bg-gray-500/10 text-gray-400 px-1 rounded">
                    .env
                  </span>
                  .
                </p>
                <p>
                  <strong className="text-gray-300">Update Rate:</strong> Pulled
                  via REST and analyzed by Gemini every{" "}
                  <span className="text-emerald-400">15 minutes</span>. The AI
                  learning model updates its semantic weightings passively
                  utilizing these sliding-window inference blocks.
                </p>
                {aiAssessmentLatest && (
                  <div className="mt-2 pt-2 border-t border-[#1e2025] text-purple-400">
                    <strong className="text-purple-500">LATEST INTEL: </strong>
                    {aiAssessmentLatest}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Right Column: Macro Economic Events */}
        <div className="lg:col-span-3 flex flex-col h-full bg-[#07080a] border border-[#1e2025] rounded-sm glass-specular glass-inset">
          <div className="p-3 border-b border-[#1e2025] bg-[#0d0e12] flex items-center gap-2">
            <Calendar size={12} className="text-cyan-400" />
            <span className="font-bold text-white uppercase tracking-wider">
              Economical Events (24H)
            </span>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-2 custom-scrollbar">
            {events.map((ev, i) => (
              <div
                key={i}
                className="border border-[#1e2025] bg-[#0b0c10] p-2.5 rounded-sm"
              >
                <div className="flex justify-between items-start mb-2">
                  <div className="font-bold text-gray-200">{ev.event}</div>
                  <div
                    className={`px-1.5 py-0.5 rounded-sm text-[8px] font-bold ${ev.impact === "HIGH" ? "bg-red-500/10 text-red-400 border border-red-500/30" : "bg-yellow-500/10 text-yellow-400 border border-yellow-500/30"}`}
                  >
                    {ev.impact} IMPACT
                  </div>
                </div>
                <div className="text-gray-500 mb-1.5 flex items-center gap-1.5">
                  <AlertTriangle size={10} className="text-gray-400" />{" "}
                  {ev.time}
                </div>
                <div className="text-purple-400/80 bg-purple-500/5 p-1.5 rounded border border-purple-500/10 leading-relaxed font-mono">
                  <span className="text-purple-500 font-bold mr-1">
                    AI INSIGHT:
                  </span>
                  {ev.aiAssessment}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Bottom Row: Token Launches */}
      <div className="flex flex-col flex-1 min-h-[0] bg-[#07080a] border border-[#1e2025] rounded-sm">
        <div className="p-3 border-b border-[#1e2025] bg-[#0d0e12] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Rocket size={12} className="text-emerald-400" />
            <span className="font-bold text-white uppercase tracking-wider">
              Predictive Token Launch Radar
            </span>
          </div>
          <span className="text-gray-500 text-[8px] uppercase">
            Tracking highest probability MEV generation events
          </span>
        </div>
        <div className="flex-1 overflow-y-auto p-0">
          <table className="w-full text-left border-collapse">
            <thead className="bg-[#121318] border-b border-[#1e2025] text-gray-500 text-[9px] uppercase sticky top-0">
              <tr>
                <th className="p-3 font-medium">Target Asset</th>
                <th className="p-3 font-medium">Status / T-Minus</th>
                <th className="p-3 font-medium">AI Confidence (Success)</th>
                <th className="p-3 font-medium">Vol Estimate</th>
                <th className="p-3 font-medium">MEV Opportunity</th>
                <th className="p-3 font-medium text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {launches.map((launch, i) => (
                <tr
                  key={i}
                  className="border-b border-[#1e2025] hover:bg-[#0b0c10] transition-colors"
                >
                  <td className="p-3">
                    <div className="flex items-center gap-2">
                      <div className="w-6 h-6 rounded-full bg-[#1e2025] flex items-center justify-center font-bold text-gray-300 select-none">
                        {launch.symbol[0]}
                      </div>
                      <div>
                        <div className="font-bold text-gray-200">
                          {launch.symbol}
                        </div>
                        <div className="text-gray-500 text-[9px]">
                          {launch.name}
                        </div>
                      </div>
                    </div>
                  </td>
                  <td className="p-3">
                    <span
                      className={`px-2 py-0.5 rounded-sm font-bold text-[9px] ${
                        launch.status === "LIVE"
                          ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 animate-pulse"
                          : launch.status === "ANALYZING"
                            ? "bg-blue-500/10 text-blue-400 border border-blue-500/30"
                            : "bg-gray-800 text-gray-400 border border-gray-700"
                      }`}
                    >
                      {launch.timeToLaunch}
                    </span>
                  </td>
                  <td className="p-3">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-1 bg-[#1e2025] rounded-full overflow-hidden w-24">
                        <div
                          className="h-full bg-purple-500"
                          style={{ width: `${launch.aiConfidence}%` }}
                        />
                      </div>
                      <span className="text-purple-400 font-bold">
                        {launch.aiConfidence}%
                      </span>
                    </div>
                  </td>
                  <td className="p-3 text-gray-300 font-bold">
                    <span
                      className={
                        launch.predictedVolatility === "EXTREME"
                          ? "text-red-400"
                          : "text-yellow-400"
                      }
                    >
                      {launch.predictedVolatility}
                    </span>
                  </td>
                  <td className="p-3">
                    <div className="flex items-center gap-1.5">
                      {launch.mevOpportunity === "CRITICAL" && (
                        <Zap
                          size={10}
                          className="text-emerald-400 fill-emerald-400"
                        />
                      )}
                      <span
                        className={
                          launch.mevOpportunity === "CRITICAL"
                            ? "text-emerald-400 font-bold"
                            : "text-gray-400"
                        }
                      >
                        {launch.mevOpportunity}
                      </span>
                    </div>
                  </td>
                  <td className="p-3 text-right">
                    <button className="px-3 py-1 bg-[#1e2025] hover:bg-[#2a2d35] text-cyan-400 border border-cyan-500/30 rounded flex items-center gap-1.5 ml-auto uppercase text-[9px] font-bold transition-colors">
                      Pre-Warm Sim
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

