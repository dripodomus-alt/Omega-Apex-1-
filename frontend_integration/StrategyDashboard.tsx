import { useState, useEffect } from "react";

type Props = {
  client: any;
};

export function StrategyDashboard({ client }: Props) {
  const [intel, setIntel] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selectedStrat, setSelectedStrat] = useState<string>("ALL");

  const fetchStrategyIntelligence = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await client.getStrategyIntelligence();
      setIntel(data);
    } catch (err: any) {
      setError(err.message || "Failed to load strategy intelligence");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStrategyIntelligence();
    const interval = setInterval(fetchStrategyIntelligence, 10000);
    return () => clearInterval(interval);
  }, []);

  const strategies = intel?.strategies || [];
  const filteredStrategies = selectedStrat === "ALL"
    ? strategies
    : strategies.filter((s: any) => s.id === selectedStrat);

  return (
    <div style={{ background: "#0c1015", border: "1px solid #252d37", borderRadius: 8, padding: 18 }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12, marginBottom: 16 }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <h2 style={{ margin: 0, color: "#f1f5f9", fontSize: 16, fontWeight: 700 }}>
              Strategy Intelligence & Per-Strategy Profit Breakdown
            </h2>
            <span style={{ background: "#0f172a", color: "#38bdf8", border: "1px solid #0284c7", padding: "2px 8px", borderRadius: 4, fontSize: 11, fontWeight: 800 }}>
              3 STRATEGY MODULES ACTIVE
            </span>
          </div>
          <p style={{ margin: "4px 0 0", color: "#94a3b8", fontSize: 12 }}>
            Categorized performance analytics for C1 Aggressor, C2 Surgeon, and Aave V3 Liquidation Engines
          </p>
        </div>

        <button
          onClick={fetchStrategyIntelligence}
          disabled={loading}
          style={{
            background: "#0284c7",
            color: "#ffffff",
            border: "1px solid #38bdf8",
            borderRadius: 6,
            padding: "8px 14px",
            fontSize: 12,
            fontWeight: 700,
            cursor: loading ? "not-allowed" : "pointer"
          }}
        >
          {loading ? "Refreshing..." : "Refresh Intelligence"}
        </button>
      </div>

      {error && (
        <div style={{ background: "#451a1a", border: "1px solid #991b1b", color: "#ff7373", padding: "8px 12px", borderRadius: 6, fontSize: 12, marginBottom: 14 }}>
          {error}
        </div>
      )}

      {/* Overview Aggregate Banner */}
      {intel && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12, marginBottom: 18 }}>
          <div style={{ background: "#111720", border: "1px solid #1e293b", padding: 12, borderRadius: 6 }}>
            <span style={{ color: "#64748b", fontSize: 11, display: "block" }}>Aggregate Realized Net Profit</span>
            <strong style={{ color: "#34d399", fontSize: 18, display: "block", marginTop: 2 }}>
              ${intel.aggregate_net_profit_usd.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </strong>
          </div>

          <div style={{ background: "#111720", border: "1px solid #1e293b", padding: 12, borderRadius: 6 }}>
            <span style={{ color: "#64748b", fontSize: 11, display: "block" }}>Highest Yield Strategy</span>
            <strong style={{ color: "#38bdf8", fontSize: 15, display: "block", marginTop: 4 }}>
              {intel.highest_yield_strategy === "C1_AGGRESSOR" ? "C1 Cross-DEX Aggressor" : "C2 Rescan Surgeon"}
            </strong>
          </div>

          <div style={{ background: "#111720", border: "1px solid #1e293b", padding: 12, borderRadius: 6 }}>
            <span style={{ color: "#64748b", fontSize: 11, display: "block" }}>Polygon Mainnet Block</span>
            <strong style={{ color: "#f59e0b", fontSize: 16, display: "block", marginTop: 2 }}>
              #{intel.block_number}
            </strong>
          </div>
        </div>
      )}

      {/* Filter Tabs */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <button
          onClick={() => setSelectedStrat("ALL")}
          style={{
            background: selectedStrat === "ALL" ? "#1e293b" : "#0f172a",
            color: selectedStrat === "ALL" ? "#f8fafc" : "#64748b",
            border: `1px solid ${selectedStrat === "ALL" ? "#334155" : "#1e293b"}`,
            borderRadius: 4,
            padding: "5px 12px",
            fontSize: 11,
            fontWeight: 600,
            cursor: "pointer"
          }}
        >
          All Strategies (3)
        </button>
        {strategies.map((s: any) => (
          <button
            key={s.id}
            onClick={() => setSelectedStrat(s.id)}
            style={{
              background: selectedStrat === s.id ? "#1e293b" : "#0f172a",
              color: selectedStrat === s.id ? "#f8fafc" : "#64748b",
              border: `1px solid ${selectedStrat === s.id ? "#334155" : "#1e293b"}`,
              borderRadius: 4,
              padding: "5px 12px",
              fontSize: 11,
              fontWeight: 600,
              cursor: "pointer"
            }}
          >
            {s.name}
          </button>
        ))}
      </div>

      {/* Strategy Cards Grid */}
      <div style={{ display: "grid", gap: 16 }}>
        {filteredStrategies.map((s: any) => (
          <div
            key={s.id}
            style={{
              background: "#111720",
              border: "1px solid #1e293b",
              borderRadius: 8,
              padding: 16
            }}
          >
            {/* Strategy Title & Status */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10, marginBottom: 12 }}>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <h3 style={{ margin: 0, color: "#f8fafc", fontSize: 15, fontWeight: 700 }}>{s.name}</h3>
                  <span
                    style={{
                      background: s.id === "C1_AGGRESSOR" ? "#0369a1" : s.id === "C2_SURGEON" ? "#6b21a8" : "#9a3412",
                      color: "#f8fafc",
                      padding: "2px 8px",
                      borderRadius: 4,
                      fontSize: 10,
                      fontWeight: 800
                    }}
                  >
                    {s.type}
                  </span>
                </div>
                <p style={{ margin: "4px 0 0", color: "#64748b", fontSize: 12 }}>{s.description}</p>
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span
                  style={{
                    background: s.status === "ACTIVE_SCANNING" ? "#064e3b" : "#1e293b",
                    color: s.status === "ACTIVE_SCANNING" ? "#34d399" : "#38bdf8",
                    border: "1px solid #10b981",
                    padding: "3px 8px",
                    borderRadius: 4,
                    fontSize: 10,
                    fontWeight: 800
                  }}
                >
                  ● {s.status}
                </span>
              </div>
            </div>

            {/* Metrics Breakdown Bar */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: 10, background: "#090d12", padding: 12, borderRadius: 6, marginBottom: 12 }}>
              <div>
                <span style={{ color: "#64748b", fontSize: 10 }}>Total Executions</span>
                <strong style={{ color: "#f8fafc", fontSize: 14, display: "block" }}>{s.total_trades}</strong>
              </div>

              <div>
                <span style={{ color: "#64748b", fontSize: 10 }}>Win Rate</span>
                <strong style={{ color: "#34d399", fontSize: 14, display: "block" }}>{s.win_rate_pct}%</strong>
              </div>

              <div>
                <span style={{ color: "#64748b", fontSize: 10 }}>Gross Profit</span>
                <strong style={{ color: "#94a3b8", fontSize: 14, display: "block" }}>${s.gross_profit_usd.toFixed(2)}</strong>
              </div>

              <div>
                <span style={{ color: "#64748b", fontSize: 10 }}>Net Profit ($)</span>
                <strong style={{ color: "#38bdf8", fontSize: 14, display: "block" }}>${s.net_profit_usd.toFixed(2)}</strong>
              </div>

              <div>
                <span style={{ color: "#64748b", fontSize: 10 }}>Avg Profit / Trade</span>
                <strong style={{ color: "#a855f7", fontSize: 14, display: "block" }}>${s.avg_profit_per_trade_usd.toFixed(2)}</strong>
              </div>

              <div>
                <span style={{ color: "#64748b", fontSize: 10 }}>Avg Gas Used</span>
                <strong style={{ color: "#f59e0b", fontSize: 14, display: "block" }}>{s.avg_gas_used.toLocaleString()}</strong>
              </div>

              <div>
                <span style={{ color: "#64748b", fontSize: 10 }}>Execution Speed</span>
                <strong style={{ color: "#38bdf8", fontSize: 14, display: "block" }}>{s.avg_execution_latency_ms}ms</strong>
              </div>
            </div>

            {/* Strategy Special Attributes */}
            {s.top_pairs && (
              <div style={{ fontSize: 11, color: "#64748b", marginBottom: 10 }}>
                Top Active Pair Routes: <strong style={{ color: "#cbd5e1" }}>{s.top_pairs.join("  •  ")}</strong>
              </div>
            )}

            {s.top_decisions && (
              <div style={{ fontSize: 11, color: "#64748b", marginBottom: 10 }}>
                C2 Decision Ratios: MIRROR (<strong style={{ color: "#34d399" }}>{s.top_decisions.MIRROR}</strong>)  •  REVERSE (<strong style={{ color: "#a855f7" }}>{s.top_decisions.REVERSE}</strong>)  •  NO_OP (<strong style={{ color: "#f43f5e" }}>{s.top_decisions.NO_OP}</strong>)
              </div>
            )}

            {s.positions_monitored && (
              <div style={{ fontSize: 11, color: "#64748b", marginBottom: 10 }}>
                Lending Positions Scanned: <strong style={{ color: "#cbd5e1" }}>{s.positions_monitored} active accounts</strong>  |  Alert HF Threshold: <strong style={{ color: "#ff7373" }}>&lt; {s.alert_health_factor}</strong>
              </div>
            )}

            {/* Recent Strategy Opportunities */}
            {s.recent_opportunities && s.recent_opportunities.length > 0 && (
              <div>
                <span style={{ color: "#475569", fontSize: 11, fontWeight: 700, display: "block", marginBottom: 6 }}>
                  Recent Opportunities & Executions:
                </span>
                <div style={{ display: "grid", gap: 6 }}>
                  {s.recent_opportunities.map((opp: any) => (
                    <div
                      key={opp.id}
                      style={{
                        background: "#090d12",
                        border: "1px solid #1e293b",
                        borderRadius: 4,
                        padding: "6px 10px",
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        fontSize: 11
                      }}
                    >
                      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                        <span style={{ color: "#64748b", fontWeight: 700 }}>#{opp.block_number}</span>
                        <span style={{ color: "#e2e8f0" }}>{opp.route || `${opp.debt} / ${opp.collateral}`}</span>
                        {opp.decision && (
                          <span style={{ background: "#1e293b", color: "#38bdf8", padding: "1px 5px", borderRadius: 3, fontWeight: 700 }}>
                            {opp.decision}
                          </span>
                        )}
                      </div>

                      <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                        <strong style={{ color: opp.net_pnl_usd > 0 ? "#34d399" : "#64748b" }}>
                          +${opp.net_pnl_usd.toFixed(2)}
                        </strong>
                        {opp.tx_hash ? (
                          <a
                            href={`https://polygonscan.com/tx/${opp.tx_hash}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{ color: "#38bdf8", textDecoration: "none", fontWeight: 600 }}
                          >
                            PolygonScan ↗
                          </a>
                        ) : (
                          <span style={{ color: "#64748b" }}>Terminated</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
