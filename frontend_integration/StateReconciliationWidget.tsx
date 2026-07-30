import { useState, useEffect } from "react";

type Props = {
  client: any;
};

export function StateReconciliationWidget({ client }: Props) {
  const [report, setReport] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [driftFilter, setDriftFilter] = useState<"ALL" | "WARNINGS" | "RECONCILED">("ALL");

  const fetchReconciliation = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await client.getReconciliationReport();
      setReport(data);
    } catch (err: any) {
      setError(err.message || "Failed to load reconciliation report");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReconciliation();
    const interval = setInterval(fetchReconciliation, 12000);
    return () => clearInterval(interval);
  }, []);

  const summary = report?.summary;
  const transactions = report?.transactions || [];

  const filteredTxs = transactions.filter((t: any) => {
    if (driftFilter === "WARNINGS") return t.status !== "RECONCILED";
    if (driftFilter === "RECONCILED") return t.status === "RECONCILED";
    return true;
  });

  return (
    <div style={{ background: "#0c1015", border: "1px solid #252d37", borderRadius: 8, padding: 18 }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12, marginBottom: 16 }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <h2 style={{ margin: 0, color: "#f1f5f9", fontSize: 16, fontWeight: 700 }}>
              Automated State Delta Reconciliation Engine
            </h2>
            {summary?.drift_alert_active ? (
              <span style={{ background: "#451a1a", color: "#ff7373", border: "1px solid #991b1b", padding: "2px 8px", borderRadius: 4, fontSize: 11, fontWeight: 800 }}>
                ⚠️ PNL DRIFT WARNING ACTIVE
              </span>
            ) : (
              <span style={{ background: "#064e3b", color: "#34d399", border: "1px solid #059669", padding: "2px 8px", borderRadius: 4, fontSize: 11, fontWeight: 800 }}>
                ✓ FULLY RECONCILED
              </span>
            )}
          </div>
          <p style={{ margin: "4px 0 0", color: "#94a3b8", fontSize: 12 }}>
            Real-time verification comparing Expected State Delta against Realized Execution Delta to detect slippage & gas drift
          </p>
        </div>

        <button
          onClick={fetchReconciliation}
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
          {loading ? "Reconciling State..." : "Run State Delta Audit"}
        </button>
      </div>

      {error && (
        <div style={{ background: "#451a1a", border: "1px solid #991b1b", color: "#ff7373", padding: "8px 12px", borderRadius: 6, fontSize: 12, marginBottom: 14 }}>
          {error}
        </div>
      )}

      {/* KPI Cards */}
      {summary && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12, marginBottom: 18 }}>
          <div style={{ background: "#111720", border: "1px solid #1e293b", padding: 12, borderRadius: 6 }}>
            <span style={{ color: "#64748b", fontSize: 11, display: "block" }}>Expected State Delta</span>
            <strong style={{ color: "#38bdf8", fontSize: 16, display: "block", marginTop: 2 }}>
              ${summary.total_expected_pnl_usd.toFixed(2)}
            </strong>
          </div>

          <div style={{ background: "#111720", border: "1px solid #1e293b", padding: 12, borderRadius: 6 }}>
            <span style={{ color: "#64748b", fontSize: 11, display: "block" }}>Realized State Delta</span>
            <strong style={{ color: summary.total_realized_pnl_usd >= summary.total_expected_pnl_usd ? "#34d399" : "#fbbf24", fontSize: 16, display: "block", marginTop: 2 }}>
              ${summary.total_realized_pnl_usd.toFixed(2)}
            </strong>
          </div>

          <div style={{ background: "#111720", border: "1px solid #1e293b", padding: 12, borderRadius: 6 }}>
            <span style={{ color: "#64748b", fontSize: 11, display: "block" }}>Net PnL Drift</span>
            <strong style={{ color: summary.net_drift_usd < 0 ? "#ff7373" : "#34d399", fontSize: 16, display: "block", marginTop: 2 }}>
              {summary.net_drift_usd > 0 ? "+" : ""}${summary.net_drift_usd.toFixed(2)} ({summary.drift_percentage.toFixed(2)}%)
            </strong>
          </div>

          <div style={{ background: "#111720", border: "1px solid #1e293b", padding: 12, borderRadius: 6 }}>
            <span style={{ color: "#64748b", fontSize: 11, display: "block" }}>Gas Price Variance</span>
            <strong style={{ color: "#f59e0b", fontSize: 16, display: "block", marginTop: 2 }}>
              +${summary.total_gas_variance_usd.toFixed(2)}
            </strong>
          </div>

          <div style={{ background: "#111720", border: "1px solid #1e293b", padding: 12, borderRadius: 6 }}>
            <span style={{ color: "#64748b", fontSize: 11, display: "block" }}>Execution Slippage</span>
            <strong style={{ color: "#f43f5e", fontSize: 16, display: "block", marginTop: 2 }}>
              -${Math.abs(summary.total_slippage_usd).toFixed(2)}
            </strong>
          </div>
        </div>
      )}

      {/* Filter Tabs */}
      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        {(["ALL", "WARNINGS", "RECONCILED"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setDriftFilter(tab)}
            style={{
              background: driftFilter === tab ? "#1e293b" : "#0f172a",
              color: driftFilter === tab ? "#f8fafc" : "#64748b",
              border: `1px solid ${driftFilter === tab ? "#334155" : "#1e293b"}`,
              borderRadius: 4,
              padding: "4px 10px",
              fontSize: 11,
              fontWeight: 600,
              cursor: "pointer"
            }}
          >
            {tab === "ALL" ? `All Transactions (${transactions.length})` : tab === "WARNINGS" ? `Drift Alerts (${transactions.filter((t: any) => t.status !== "RECONCILED").length})` : `Reconciled (${transactions.filter((t: any) => t.status === "RECONCILED").length})`}
          </button>
        ))}
      </div>

      {/* Transactions List */}
      <div style={{ display: "grid", gap: 10 }}>
        {filteredTxs.map((t: any) => (
          <div
            key={t.tx_hash}
            style={{
              background: "#111720",
              border: `1px solid ${t.status !== "RECONCILED" ? "#7f1d1d" : "#1e293b"}`,
              borderRadius: 6,
              padding: 12
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span
                  style={{
                    background: t.status === "RECONCILED" ? "#064e3b" : "#451a1a",
                    color: t.status === "RECONCILED" ? "#34d399" : "#ff7373",
                    padding: "2px 6px",
                    borderRadius: 4,
                    fontSize: 10,
                    fontWeight: 800
                  }}
                >
                  {t.status}
                </span>
                <span style={{ color: "#38bdf8", fontSize: 11, fontWeight: 700 }}>{t.strategy}</span>
                <span style={{ color: "#94a3b8", fontSize: 12 }}>{t.route}</span>
              </div>

              <div style={{ display: "flex", gap: 12, alignItems: "center", fontSize: 12, fontFamily: "monospace" }}>
                <span>Expected: <strong style={{ color: "#94a3b8" }}>${t.expected_pnl_usd.toFixed(2)}</strong></span>
                <span>Realized: <strong style={{ color: "#34d399" }}>${t.realized_pnl_usd.toFixed(2)}</strong></span>
                <span>Drift: <strong style={{ color: t.pnl_drift_usd < 0 ? "#ff7373" : "#34d399" }}>${t.pnl_drift_usd.toFixed(2)} ({t.pnl_drift_pct.toFixed(2)}%)</strong></span>
              </div>
            </div>

            <div style={{ marginTop: 8, paddingTop: 8, borderTop: "1px solid #1e293b", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8, fontSize: 11, color: "#64748b" }}>
              <div style={{ display: "flex", gap: 14 }}>
                <span>Gas Variance: <strong style={{ color: "#f59e0b" }}>+${t.gas_variance_usd.toFixed(2)}</strong></span>
                <span>Slippage/Impact: <strong style={{ color: "#f43f5e" }}>-${Math.abs(t.slippage_impact_usd).toFixed(2)}</strong></span>
                <span>Fee Delta: <strong style={{ color: "#a855f7" }}>${t.fee_delta_usd.toFixed(2)}</strong></span>
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span>Block #{t.block_number}</span>
                <a
                  href={t.polygonscan_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ color: "#38bdf8", textDecoration: "none", fontWeight: 600 }}
                >
                  PolygonScan ↗
                </a>
              </div>
            </div>
          </div>
        ))}

        {!filteredTxs.length && (
          <div style={{ padding: 16, textAlign: "center", color: "#64748b", fontSize: 12 }}>
            No reconciliation records found for this filter.
          </div>
        )}
      </div>
    </div>
  );
}
