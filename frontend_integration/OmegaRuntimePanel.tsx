import { useState } from "react";
import { useOmegaRuntime } from "./useOmegaRuntime";

type Props = {
  apiBaseUrl: string;
  apiToken?: string;
};

function money(value: unknown) {
  const n = Number(value || 0);
  return n.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 2 });
}

function shortAddress(value: unknown) {
  const text = String(value || "");
  return text.length > 14 ? `${text.slice(0, 8)}...${text.slice(-6)}` : text || "-";
}

function riskColor(level: string) {
  if (level === "critical") return "#ff7373";
  if (level === "warning") return "#ffd37a";
  return "#9cc9ff";
}

function countMap(value: unknown) {
  if (!value || typeof value !== "object") return "-";
  return Object.entries(value as Record<string, unknown>)
    .map(([key, val]) => `${key}:${String(val)}`)
    .join("  ");
}

export function OmegaRuntimePanel({ apiBaseUrl, apiToken = "" }: Props) {
  const omega = useOmegaRuntime(apiBaseUrl, apiToken);
  const [executeTop, setExecuteTop] = useState(5);
  const [printTopRoutes, setPrintTopRoutes] = useState(50);
  const [canaryMode, setCanaryMode] = useState(false);
  const [pipelineResult, setPipelineResult] = useState<any>(null);

  const mode = omega.mode?.mode || "unknown";
  const status = omega.status;
  const pnl = omega.pnl;
  const liquidations = omega.liquidations;
  const oraclePrices = omega.oraclePrices;
  const sessionProof = omega.sessionProof;
  const runtimeAlignment = omega.runtimeAlignment;
  const finalizer = omega.finalizer;
  const latestPoolScan = status?.latest_pool_scan || {};
  const statusDiscovery = status?.discovery || {};
  const statusDiscoveryHasData = Boolean(
    statusDiscovery?.factory?.promoted ||
    statusDiscovery?.dynamic_pool_registry?.promoted ||
    statusDiscovery?.curve_pool_registry?.promoted ||
    statusDiscovery?.polygon_token_list?.runtime_added,
  );
  const discovery = statusDiscoveryHasData ? statusDiscovery : latestPoolScan?.discovery || {};
  const factory = discovery.factory || {};
  const dynamicPools = discovery.dynamic_pool_registry || {};
  const curvePools = discovery.curve_pool_registry || {};
  const tokenList = discovery.polygon_token_list || {};
  const subgraph = discovery.subgraph_pool_intel || {};
  const latestLiquidity = latestPoolScan?.liquidity || {};

  return (
    <div style={{ display: "grid", gap: 16, color: "#e8edf2", background: "#0e1116", padding: 20 }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 24 }}>Omega V5 Runtime</h1>
          <div style={{ color: "#a9b4c0" }}>Chain 137 backend control surface</div>
        </div>
        <strong style={{ color: status?.execution_armed ? "#ff7373" : "#52d69a" }}>
          {status?.execution_armed ? "LIVE ARMED" : "DRY RUN / GUARDED"}
        </strong>
      </header>

      {omega.error && (
        <section style={{ border: "1px solid #9f3d3d", padding: 12, borderRadius: 8 }}>
          Backend error: {omega.error}
        </section>
      )}

      <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 12 }}>
        <div style={cardStyle}>
          <h2 style={h2Style}>Runtime</h2>
          <Row label="Mode" value={mode} />
          <Row label="Redis" value={status?.redis?.detail || "-"} />
          <Row label="Rust engine" value={status?.rust_engine?.ready ? "ready" : "not ready"} />
          <Row label="Execution armed" value={String(!!status?.execution_armed)} />
          <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
            <button style={buttonStyle} onClick={() => omega.setMode("dry_run")}>Dry Run</button>
            <button style={dangerButtonStyle} onClick={() => omega.setMode("live")}>Live</button>
          </div>
        </div>

        <div style={cardStyle}>
          <h2 style={h2Style}>Cycle</h2>
          <label style={labelStyle}>Execute top</label>
          <select value={executeTop} onChange={(e) => setExecuteTop(Number(e.target.value))} style={inputStyle}>
            <option value={5}>5</option>
            <option value={10}>10</option>
            <option value={15}>15</option>
          </select>
          <label style={labelStyle}>Print top routes</label>
          <input value={printTopRoutes} onChange={(e) => setPrintTopRoutes(Number(e.target.value))} style={inputStyle} />
          <label style={{ display: "flex", gap: 8, marginTop: 10 }}>
            <input type="checkbox" checked={canaryMode} onChange={(e) => setCanaryMode(e.target.checked)} />
            Canary cap
          </label>
          <button
            style={buttonStyle}
            onClick={() => omega.updateSettings({ execute_top: executeTop, print_top_routes: printTopRoutes, canary_mode: canaryMode })}
          >
            Apply
          </button>
        </div>

        <div style={cardStyle}>
          <h2 style={h2Style}>Proofs</h2>
          <Row label="Runtime alignment" value={runtimeAlignment?.status || "missing"} />
          <Row label="Session signer" value={sessionProof?.status || "missing"} />
          <Row label="Finalizer verdict" value={finalizer?.verdict || "missing"} />
          <Row label="Blockers" value={(finalizer?.mainnet_blocker_register || []).length} />
          <Row label="WaaS execute" value={sessionProof?.definition_of_done?.external_waas_prepare_execute_proven ? "proven" : "not configured"} />
          <button style={buttonStyle} onClick={() => omega.runProofs()}>Run Proofs</button>
        </div>
      </section>

      <section style={cardStyle}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
          <h2 style={h2Style}>Pool Discovery Coverage</h2>
          <strong style={{ color: curvePools?.promoted ? "#52d69a" : "#ffd37a" }}>
            {curvePools?.promoted ?? 0} Curve staged
          </strong>
        </div>
        <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>
          <div>
            <Row label="Factory promoted" value={`${factory?.promoted ?? 0} / ${factory?.live_candidates ?? 0} live`} />
            <Row label="Factory protocols" value={countMap(factory?.promoted_by_protocol)} />
            <Row label="V2 anchor" value={factory?.v2_anchor || "-"} />
          </div>
          <div>
            <Row label="Dynamic rows" value={dynamicPools?.rows ?? 0} />
            <Row label="Dynamic staged" value={dynamicPools?.promoted ?? 0} />
            <Row label="Dynamic protocols" value={countMap(dynamicPools?.by_protocol)} />
          </div>
          <div>
            <Row label="Curve rows" value={curvePools?.rows ?? 0} />
            <Row label="Curve staged" value={curvePools?.promoted ?? 0} />
            <Row label="Curve families" value={countMap(curvePools?.by_family)} />
          </div>
          <div>
            <Row label="Token-list staged" value={tokenList?.runtime_added ?? 0} />
            <Row label="Subgraph promoted" value={subgraph?.promoted ?? 0} />
            <Row label="Subgraph hints" value={subgraph?.candidate_count ?? 0} />
          </div>
          <div>
            <Row label="Latest loaded pools" value={latestPoolScan?.pools_loaded ?? "-"} />
            <Row label="Latest protocols" value={countMap(latestPoolScan?.protocol_counts)} />
            <Row label="Executable liquidity" value={money(latestLiquidity?.sum_positive_usd)} />
          </div>
        </section>
        {(pipelineResult?.stdout || pipelineResult?.output) && (
          <pre style={preStyle}>
            {String(pipelineResult.stdout || pipelineResult.output)
              .split("\n")
              .filter((line) =>
                /pools_loaded=|factory_discovery_stats=|verified_pool_registry_rows=|rate_pairs=|cycles_detected=|payload_ok=|pipeline_validation=/.test(line),
              )
              .join("\n")}
          </pre>
        )}
      </section>

      <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 12 }}>
        <div style={cardStyle}>
          <h2 style={h2Style}>Dry-Run PnL</h2>
          <Row label="C1" value={money(pnl?.dry_run?.C1?.display_pnl_usd)} />
          <Row label="C2" value={money(pnl?.dry_run?.C2?.display_pnl_usd)} />
          <Row label="Combined" value={money(pnl?.dry_run?.combined?.display_pnl_usd)} />
        </div>
        <div style={cardStyle}>
          <h2 style={h2Style}>Live PnL</h2>
          <Row label="C1" value={money(pnl?.live?.C1?.display_pnl_usd)} />
          <Row label="C2" value={money(pnl?.live?.C2?.display_pnl_usd)} />
          <Row label="Combined" value={money(pnl?.live?.combined?.display_pnl_usd)} />
        </div>
      </section>

      <section style={cardStyle}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
          <h2 style={h2Style}>Oracle Feeds</h2>
          <strong style={{ color: oraclePrices?.healthy ? "#52d69a" : "#ff7373" }}>
            {oraclePrices?.healthy ? `${oraclePrices?.count ?? 0} live prices` : "unhealthy"}
          </strong>
        </div>
        {oraclePrices?.error && <div style={{ color: "#ff7373", marginTop: 10 }}>{oraclePrices.error}</div>}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: 10, marginTop: 12 }}>
          {(oraclePrices?.prices || []).slice(0, 16).map((row: any) => (
            <div key={row.symbol} style={{ border: "1px solid #2a323d", borderRadius: 6, padding: 10, background: "#10151b" }}>
              <div style={{ color: "#a9b4c0", fontSize: 12 }}>{row.symbol}/USD</div>
              <strong>{money(row.price_usd)}</strong>
              <div style={{ color: "#7e8b99", fontSize: 11 }}>{row.source}</div>
            </div>
          ))}
        </div>
      </section>

      <section style={cardStyle}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
          <h2 style={h2Style}>Liquidation Tracker</h2>
          <strong style={{ color: liquidations?.liquidatable_count ? "#ff7373" : "#52d69a" }}>
            {liquidations?.alert_count ?? 0} alerts
          </strong>
        </div>
        <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12 }}>
          <Row label="Aave pool" value={shortAddress(liquidations?.aave_pool)} />
          <Row label="Block" value={liquidations?.block_number || "-"} />
          <Row label="Alert HF" value={liquidations?.alert_health_factor || "1.10"} />
          <Row label="Scanned" value={liquidations?.borrowers_scanned ?? 0} />
          <Row label="Liquidatable" value={liquidations?.liquidatable_count ?? 0} />
          <Row label="Near threshold" value={liquidations?.near_threshold_count ?? 0} />
        </section>
        {liquidations?.error && <div style={{ color: "#ff7373", marginTop: 10 }}>{liquidations.error}</div>}
        <div style={{ overflowX: "auto", marginTop: 12 }}>
          <table style={tableStyle}>
            <thead>
              <tr>
                <th style={thStyle}>Risk</th>
                <th style={thStyle}>Borrower</th>
                <th style={thStyle}>Health</th>
                <th style={thStyle}>Debt</th>
                <th style={thStyle}>Collateral</th>
                <th style={thStyle}>Debt USD</th>
                <th style={thStyle}>Collateral USD</th>
              </tr>
            </thead>
            <tbody>
              {(liquidations?.rows || []).slice(0, 12).map((row: any) => (
                <tr key={`${row.borrower}-${row.health_factor}`}>
                  <td style={{ ...tdStyle, color: riskColor(row.risk_level), fontWeight: 700 }}>{row.status}</td>
                  <td style={tdStyle}><code>{shortAddress(row.borrower)}</code></td>
                  <td style={tdStyle}>{Number(row.health_factor).toFixed(4)}</td>
                  <td style={tdStyle}>{(row.debt_symbols || []).join(", ") || "-"}</td>
                  <td style={tdStyle}>{(row.collateral_symbols || []).join(", ") || "-"}</td>
                  <td style={tdStyle}>{money(row.total_debt_usd)}</td>
                  <td style={tdStyle}>{money(row.total_collateral_usd)}</td>
                </tr>
              ))}
              {!(liquidations?.rows || []).length && (
                <tr>
                  <td style={tdStyle} colSpan={7}>No Aave borrowers at or below the configured alert health factor.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section style={cardStyle}>
        <h2 style={h2Style}>Validation</h2>
        <button
          style={buttonStyle}
          onClick={async () => setPipelineResult(await omega.validatePipeline())}
        >
          Validate Pipeline
        </button>
        {pipelineResult && (
          <pre style={preStyle}>{JSON.stringify(pipelineResult, null, 2)}</pre>
        )}
      </section>

      <section style={cardStyle}>
        <h2 style={h2Style}>Recent Traces</h2>
        <div style={{ display: "grid", gap: 8 }}>
          {omega.traces.slice(0, 10).map((trace: any) => (
            <div key={trace.trace_hash} style={{ borderBottom: "1px solid #2a323d", paddingBottom: 8 }}>
              <strong>{trace.stage}</strong> {trace.status}{" "}
              <code style={{ color: "#9cc9ff" }}>{String(trace.trace_hash || "").slice(0, 24)}</code>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function Row({ label, value }: { label: string; value: unknown }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12, padding: "6px 0" }}>
      <span style={{ color: "#a9b4c0" }}>{label}</span>
      <strong style={{ overflowWrap: "anywhere", textAlign: "right" }}>{String(value ?? "-")}</strong>
    </div>
  );
}

const cardStyle: React.CSSProperties = {
  background: "#171c23",
  border: "1px solid #2a323d",
  borderRadius: 8,
  padding: 16,
};

const h2Style: React.CSSProperties = {
  marginTop: 0,
  fontSize: 16,
};

const buttonStyle: React.CSSProperties = {
  background: "#243142",
  color: "#edf3f8",
  border: "1px solid #3b4654",
  borderRadius: 6,
  padding: "9px 11px",
  marginTop: 10,
  cursor: "pointer",
};

const dangerButtonStyle: React.CSSProperties = {
  ...buttonStyle,
  background: "#532527",
  borderColor: "#a34545",
};

const labelStyle: React.CSSProperties = {
  display: "block",
  color: "#a9b4c0",
  marginTop: 8,
};

const inputStyle: React.CSSProperties = {
  width: "100%",
  background: "#222a34",
  color: "#edf3f8",
  border: "1px solid #3b4654",
  borderRadius: 6,
  padding: "9px 11px",
  boxSizing: "border-box",
};

const preStyle: React.CSSProperties = {
  background: "#0b0e12",
  border: "1px solid #29313b",
  borderRadius: 8,
  padding: 12,
  overflow: "auto",
  maxHeight: 320,
};

const tableStyle: React.CSSProperties = {
  width: "100%",
  borderCollapse: "collapse",
  fontSize: 13,
};

const thStyle: React.CSSProperties = {
  color: "#a9b4c0",
  textAlign: "left",
  borderBottom: "1px solid #2a323d",
  padding: "8px 6px",
};

const tdStyle: React.CSSProperties = {
  borderBottom: "1px solid #252d37",
  padding: "8px 6px",
  verticalAlign: "top",
};
