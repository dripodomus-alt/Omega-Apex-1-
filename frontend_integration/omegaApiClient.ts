export type OmegaMode = "dry_run" | "live";

export type OmegaClientOptions = {
  baseUrl: string;
  apiToken?: string;
};

export type RuntimeSettings = {
  execute_top?: number;
  print_top_routes?: number;
  ticks?: number;
  principal_usd?: string;
  interval_seconds?: number;
  no_scan?: boolean;
  canary_mode?: boolean;
};

export type RuntimeState = {
  mode: OmegaMode;
  updated_at_ns: number;
  updated_by: string;
  settings: Required<RuntimeSettings>;
  live_reset_policy: string;
};

export type RuntimeStatus = {
  chain_id: number;
  execution_mode: OmegaMode;
  runtime: RuntimeState;
  discovery?: {
    factory?: Record<string, any>;
    polygon_token_list?: Record<string, any>;
    dynamic_pool_registry?: Record<string, any>;
    curve_pool_registry?: Record<string, any>;
    subgraph_pool_intel?: Record<string, any>;
  };
  latest_pool_scan?: Record<string, any>;
  redis: { ok: boolean; detail: string };
  transport: { enabled: boolean; lane_count: number; redis_ok: boolean };
  sourced_layers: Record<string, unknown>;
  rust_engine: { required: boolean; ready: boolean; binary?: string; error?: string };
  executor: { code_ok: boolean; detail: string; owner: string };
  guards: Record<string, boolean>;
  execution_armed: boolean;
};

export type PnlSnapshot = {
  dry_run: Record<string, any>;
  live: Record<string, any>;
};

export type TraceList = {
  count: number;
  traces: Array<Record<string, any>>;
};

export type ProofStatus = {
  ok: boolean;
  status: string;
  [key: string]: any;
};

export type LiquidationTrackerRow = {
  borrower: string;
  block_number: number;
  health_factor: string;
  status: "LIQUIDATABLE" | "NEAR_THRESHOLD" | "WATCH";
  risk_level: "critical" | "warning" | "watch";
  debt_symbols: string[];
  collateral_symbols: string[];
  total_debt_usd: string;
  total_collateral_usd: string;
  position_count: number;
};

export type LiquidationTracker = {
  ok: boolean;
  healthy: boolean;
  authority?: string;
  chain_id?: number;
  aave_pool?: string;
  block_number?: number;
  alert_health_factor: string;
  borrowers_scanned?: number;
  alert_count?: number;
  liquidatable_count?: number;
  near_threshold_count?: number;
  rows: LiquidationTrackerRow[];
  errors?: string[];
  error?: string;
};

export type OraclePriceRow = {
  symbol: string;
  price_usd: string;
  source: string;
};

export type OraclePriceSnapshot = {
  ok: boolean;
  healthy: boolean;
  chain_id: number;
  count: number;
  prices: OraclePriceRow[];
  error?: string;
};

export class OmegaApiClient {
  private readonly baseUrl: string;
  private readonly apiToken: string;

  constructor(options: OmegaClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, "");
    this.apiToken = options.apiToken || "";
  }

  private headers(): HeadersInit {
    const headers: HeadersInit = { "Content-Type": "application/json" };
    if (this.apiToken) headers.Authorization = `Bearer ${this.apiToken}`;
    return headers;
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const res = await fetch(`${this.baseUrl}${path}`, {
      ...init,
      headers: {
        ...this.headers(),
        ...(init.headers || {}),
      },
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`${res.status} ${res.statusText}: ${text}`);
    }
    return (await res.json()) as T;
  }

  health() {
    return this.request<{ ok: boolean; service: string; chain_id: number }>("/health");
  }

  frontendManifest() {
    return this.request<Record<string, any>>("/api/frontend/manifest");
  }

  runtimeStatus(probe = false) {
    return this.request<RuntimeStatus>(`/api/runtime/status?probe=${String(probe)}`);
  }

  runtimeMode() {
    return this.request<RuntimeState>("/api/runtime/mode");
  }

  setRuntimeMode(mode: OmegaMode, actor = "frontend") {
    return this.request<RuntimeState>("/api/runtime/mode", {
      method: "POST",
      body: JSON.stringify({ mode, actor }),
    });
  }

  updateRuntimeSettings(settings: RuntimeSettings) {
    return this.request<RuntimeState>("/api/runtime/settings", {
      method: "POST",
      body: JSON.stringify(settings),
    });
  }

  pnl() {
    return this.request<PnlSnapshot>("/api/pnl");
  }

  liquidationTracker(alertHealthFactor = "1.10", limit = 50) {
    const qs = new URLSearchParams({ alert_health_factor: alertHealthFactor, limit: String(limit) });
    return this.request<LiquidationTracker>(`/api/liquidations/tracker?${qs.toString()}`);
  }

  oraclePrices(force = false) {
    return this.request<OraclePriceSnapshot>(`/api/oracles/prices?force=${String(force)}`);
  }

  traces(limit = 50, stage: "" | "C1" | "C2" | "LIQUIDATION" = "") {
    const qs = new URLSearchParams({ limit: String(limit), stage });
    return this.request<TraceList>(`/api/traces?${qs.toString()}`);
  }

  sessionProof() {
    return this.request<ProofStatus>("/api/proofs/session-signer");
  }

  runtimeAlignmentProof() {
    return this.request<ProofStatus>("/api/proofs/runtime-alignment");
  }

  finalizerReport(probe = false) {
    return this.request<ProofStatus>(`/api/finalizer/report?probe=${String(probe)}`);
  }

  runSessionProof(samples = 5) {
    return this.request<ProofStatus>(`/api/proofs/session-signer/run?samples=${samples}`, {
      method: "POST",
    });
  }

  runRuntimeAlignmentProof(probe = true) {
    return this.request<ProofStatus>(`/api/proofs/runtime-alignment/run?probe=${String(probe)}`, {
      method: "POST",
    });
  }

  validatePipeline(noEthCall = true, timeoutSeconds = 300) {
    const qs = new URLSearchParams({
      no_eth_call: String(noEthCall),
      timeout_seconds: String(timeoutSeconds),
    });
    return this.request<Record<string, any>>(`/api/pipeline/validate?${qs.toString()}`, {
      method: "POST",
    });
  }
}
