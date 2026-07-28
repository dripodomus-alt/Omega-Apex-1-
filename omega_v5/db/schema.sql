-- =============================================================================
-- Omega V5 - Graph-Relational Hybrid Schema for PostgreSQL
-- Includes C1×C2 hierarchical logging model (opportunities, cycles, events)
-- =============================================================================

-- Table for the unique "DNA" of each arbitrage route.
CREATE TABLE IF NOT EXISTS route_registry (
    route_hash TEXT PRIMARY KEY,
    path_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_route_registry_path_json ON route_registry USING GIN(path_json);

-- Time-series table for all simulation data, partitioned by month.
CREATE TABLE IF NOT EXISTS simulation_audit (
    simulation_id BIGSERIAL,
    route_hash TEXT NOT NULL REFERENCES route_registry(route_hash),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata_jsonb JSONB NOT NULL,
    PRIMARY KEY (simulation_id, recorded_at)
) PARTITION BY RANGE (recorded_at);

CREATE INDEX IF NOT EXISTS idx_simulation_audit_opp_id ON simulation_audit USING GIN ((metadata_jsonb ->> 'opp_id'));
CREATE INDEX IF NOT EXISTS idx_simulation_audit_metadata ON simulation_audit USING GIN(metadata_jsonb);

CREATE TABLE IF NOT EXISTS simulation_audit_y2026m07 PARTITION OF simulation_audit FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');
CREATE TABLE IF NOT EXISTS simulation_audit_y2026m08 PARTITION OF simulation_audit FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');
CREATE TABLE IF NOT EXISTS simulation_audit_y2026m09 PARTITION OF simulation_audit FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');
CREATE TABLE IF NOT EXISTS simulation_audit_y2026m10 PARTITION OF simulation_audit FOR VALUES FROM ('2026-10-01') TO ('2026-11-01');

CREATE TABLE IF NOT EXISTS execution_audit (
    execution_id BIGSERIAL PRIMARY KEY,
    simulation_id BIGINT NOT NULL,
    tx_hash TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL,
    net_profit_usd_truth NUMERIC,
    gas_used_truth BIGINT,
    executed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- C1 × C2 Logging Model
-- =============================================================================

CREATE TABLE IF NOT EXISTS opportunities (
    opportunity_id        TEXT PRIMARY KEY,
    chain_id              BIGINT NOT NULL,
    discovered_block      BIGINT NOT NULL,
    discovered_block_hash TEXT,
    detected_at_ms        BIGINT NOT NULL,
    config_version        BIGINT NOT NULL DEFAULT 0,
    config_hash           TEXT NOT NULL,
    borrow_asset          TEXT NOT NULL,
    borrow_symbol         TEXT NOT NULL,
    buy_venue             TEXT,
    buy_pool              TEXT NOT NULL,
    sell_venue            TEXT,
    sell_pool             TEXT NOT NULL,
    buy_family            TEXT,
    sell_family           TEXT,
    buy_leg_price         NUMERIC,
    sell_leg_price        NUMERIC,
    raw_spread_usd        NUMERIC,
    raw_spread_bps        NUMERIC,
    state_hash            TEXT NOT NULL,
    route_hash            TEXT NOT NULL,
    opportunity_status    TEXT NOT NULL,
    c1_cycle_id           TEXT,
    c2_cycle_id           TEXT,
    final_status          TEXT,
    combined_realized_net_usd NUMERIC,
    created_at_ms         BIGINT NOT NULL,
    updated_at_ms         BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_opportunities_block ON opportunities (discovered_block DESC);
CREATE INDEX IF NOT EXISTS idx_opportunities_status ON opportunities (opportunity_status);

CREATE TABLE IF NOT EXISTS c1_cycles (
    c1_cycle_id            TEXT PRIMARY KEY,
    opportunity_id         TEXT NOT NULL REFERENCES opportunities(opportunity_id),
    cycle_type             TEXT NOT NULL DEFAULT 'C1',
    cycle_index            BIGINT NOT NULL DEFAULT 1,
    chain_id               BIGINT NOT NULL,
    discovery_block        BIGINT NOT NULL,
    execution_anchor_block BIGINT,
    expires_at_block       BIGINT,
    borrow_asset           TEXT NOT NULL,
    borrow_amount_raw      TEXT NOT NULL,
    borrow_amount_usd      NUMERIC NOT NULL,
    route_hash             TEXT NOT NULL,
    state_hash             TEXT NOT NULL,
    config_hash            TEXT NOT NULL,
    expected_gross_usd     NUMERIC,
    expected_net_usd       NUMERIC,
    min_net_usd            NUMERIC,
    gas_estimate_usd       NUMERIC,
    flash_fee_usd          NUMERIC,
    risk_buffer_usd        NUMERIC,
    mev_buffer_usd         NUMERIC,
    simulation_status      TEXT NOT NULL DEFAULT 'NOT_STARTED',
    payload_status         TEXT NOT NULL DEFAULT 'NOT_BUILT',
    submission_status      TEXT NOT NULL DEFAULT 'NOT_SUBMITTED',
    settlement_status      TEXT NOT NULL DEFAULT 'NOT_SETTLED',
    tx_hash                TEXT,
    submitted_block        BIGINT,
    confirmed_block        BIGINT,
    realized_gross_usd     NUMERIC,
    realized_net_usd       NUMERIC,
    realized_gas_usd       NUMERIC,
    realized_profit_raw    TEXT,
    reject_reason          TEXT,
    created_at_ms          BIGINT NOT NULL,
    updated_at_ms          BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_c1_cycles_opp ON c1_cycles (opportunity_id);
CREATE INDEX IF NOT EXISTS idx_c1_cycles_tx ON c1_cycles (tx_hash);

CREATE TABLE IF NOT EXISTS c2_cycles (
    c2_cycle_id              TEXT PRIMARY KEY,
    opportunity_id           TEXT NOT NULL REFERENCES opportunities(opportunity_id),
    parent_c1_cycle_id       TEXT NOT NULL REFERENCES c1_cycles(c1_cycle_id),
    cycle_type               TEXT NOT NULL DEFAULT 'C2',
    cycle_index              BIGINT NOT NULL DEFAULT 2,
    c1_tx_hash               TEXT NOT NULL,
    c1_confirmed_block       BIGINT NOT NULL,
    c2_window_start_block    BIGINT NOT NULL,
    c2_window_end_block      BIGINT NOT NULL,
    c2_eval_block            BIGINT,
    post_c1_state_hash       TEXT NOT NULL,
    pre_c2_route_hash        TEXT,
    c2_route_hash            TEXT,
    c2_decision              TEXT NOT NULL DEFAULT 'PENDING',
    mirror_expected_net_usd  NUMERIC,
    reverse_expected_net_usd NUMERIC,
    selected_expected_net_usd NUMERIC,
    borrow_asset             TEXT,
    borrow_amount_raw        TEXT,
    borrow_amount_usd        NUMERIC,
    gas_estimate_usd         NUMERIC,
    flash_fee_usd            NUMERIC,
    risk_buffer_usd          NUMERIC,
    mev_buffer_usd           NUMERIC,
    simulation_status        TEXT NOT NULL DEFAULT 'NOT_STARTED',
    payload_status           TEXT NOT NULL DEFAULT 'NOT_BUILT',
    submission_status        TEXT NOT NULL DEFAULT 'NOT_SUBMITTED',
    settlement_status        TEXT NOT NULL DEFAULT 'NOT_SETTLED',
    tx_hash                  TEXT,
    submitted_block          BIGINT,
    confirmed_block          BIGINT,
    realized_gross_usd       NUMERIC,
    realized_net_usd         NUMERIC,
    realized_gas_usd         NUMERIC,
    realized_profit_raw      TEXT,
    reject_reason            TEXT,
    created_at_ms            BIGINT NOT NULL,
    updated_at_ms            BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_c2_cycles_opp ON c2_cycles (opportunity_id);
CREATE INDEX IF NOT EXISTS idx_c2_cycles_parent ON c2_cycles (parent_c1_cycle_id);

CREATE TABLE IF NOT EXISTS cycle_events (
    event_id          TEXT PRIMARY KEY,
    opportunity_id    TEXT NOT NULL,
    cycle_id          TEXT NOT NULL,
    cycle_type        TEXT NOT NULL,
    event_type        TEXT NOT NULL,
    event_status      TEXT NOT NULL DEFAULT 'OK',
    block_number      BIGINT,
    tx_hash           TEXT,
    state_hash        TEXT,
    route_hash        TEXT,
    config_hash       TEXT,
    message           TEXT,
    metadata_json     JSONB,
    created_at_ms     BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cycle_events_opp ON cycle_events (opportunity_id, created_at_ms);
CREATE INDEX IF NOT EXISTS idx_cycle_events_type ON cycle_events (event_type);

CREATE TABLE IF NOT EXISTS cycle_quotes (
    quote_id       TEXT PRIMARY KEY,
    opportunity_id TEXT NOT NULL,
    cycle_id       TEXT NOT NULL,
    cycle_type     TEXT NOT NULL,
    quote_json     JSONB NOT NULL,
    created_at_ms  BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS cycle_sizing (
    sizing_id      TEXT PRIMARY KEY,
    opportunity_id TEXT NOT NULL,
    cycle_id       TEXT NOT NULL,
    cycle_type     TEXT NOT NULL,
    sizing_json    JSONB NOT NULL,
    created_at_ms  BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS cycle_simulations (
    simulation_row_id TEXT PRIMARY KEY,
    opportunity_id    TEXT NOT NULL,
    cycle_id          TEXT NOT NULL,
    cycle_type        TEXT NOT NULL,
    status            TEXT NOT NULL,
    simulation_json   JSONB NOT NULL,
    created_at_ms     BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS cycle_payloads (
    payload_id     TEXT PRIMARY KEY,
    opportunity_id TEXT NOT NULL,
    cycle_id       TEXT NOT NULL,
    cycle_type     TEXT NOT NULL,
    payload_hash   TEXT,
    payload_json   JSONB NOT NULL,
    created_at_ms  BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS cycle_submissions (
    submission_id  TEXT PRIMARY KEY,
    opportunity_id TEXT NOT NULL,
    cycle_id       TEXT NOT NULL,
    cycle_type     TEXT NOT NULL,
    channel        TEXT,
    tx_hash        TEXT,
    status         TEXT NOT NULL,
    submission_json JSONB,
    created_at_ms  BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS cycle_settlements (
    settlement_id  TEXT PRIMARY KEY,
    opportunity_id TEXT NOT NULL,
    cycle_id       TEXT NOT NULL,
    cycle_type     TEXT NOT NULL,
    tx_hash        TEXT,
    status         TEXT NOT NULL,
    realized_net_usd NUMERIC,
    settlement_json JSONB,
    created_at_ms  BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS cycle_rejections (
    rejection_id   TEXT PRIMARY KEY,
    opportunity_id TEXT NOT NULL,
    cycle_id       TEXT NOT NULL,
    cycle_type     TEXT NOT NULL,
    reason         TEXT NOT NULL,
    rejection_json JSONB,
    created_at_ms  BIGINT NOT NULL
);

-- ML training view (best-effort; simulation_id join may be loose without composite FK)
CREATE OR REPLACE VIEW vqc_training_view AS
SELECT
    sim.simulation_id,
    sim.route_hash,
    (sim.metadata_jsonb -> 'profitability' ->> 'gross_rate')::NUMERIC AS pre_math_gross_rate,
    (sim.metadata_jsonb -> 'profitability' ->> 'slippage_bps')::NUMERIC AS slippage_bps,
    jsonb_array_length(reg.path_json) - 1 AS num_legs,
    (sample ->> 'principal')::NUMERIC AS principal_usd,
    (exec.net_profit_usd_truth > 0) AS is_profitable_truth
FROM
    simulation_audit sim
JOIN route_registry reg ON sim.route_hash = reg.route_hash
CROSS JOIN LATERAL jsonb_array_elements(
    COALESCE(sim.metadata_jsonb -> 'profitability' -> 'samples', '[]'::jsonb)
) AS sample
LEFT JOIN execution_audit exec ON true
WHERE exec.tx_hash IS NOT NULL OR true
LIMIT 0; -- placeholder safe view; populate via app queries

CREATE OR REPLACE VIEW live_pnl_dashboard_view AS
SELECT
    o.opportunity_id,
    o.discovered_block,
    o.opportunity_status,
    o.final_status,
    c1.tx_hash AS c1_tx_hash,
    c1.realized_net_usd AS c1_realized_net_usd,
    c2.c2_decision,
    c2.tx_hash AS c2_tx_hash,
    c2.realized_net_usd AS c2_realized_net_usd,
    o.combined_realized_net_usd,
    o.updated_at_ms
FROM opportunities o
LEFT JOIN c1_cycles c1 ON o.c1_cycle_id = c1.c1_cycle_id
LEFT JOIN c2_cycles c2 ON o.c2_cycle_id = c2.c2_cycle_id
ORDER BY o.updated_at_ms DESC;

CREATE OR REPLACE VIEW c1_c2_timeline_view AS
SELECT
    e.created_at_ms,
    e.opportunity_id,
    e.cycle_id,
    e.cycle_type,
    e.event_type,
    e.block_number,
    e.tx_hash,
    e.message
FROM cycle_events e
ORDER BY e.created_at_ms ASC;
