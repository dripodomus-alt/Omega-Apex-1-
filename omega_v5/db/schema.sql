-- =============================================================================
-- Omega V5 - Graph-Relational Hybrid Schema for PostgreSQL
--
-- This schema optimizes for high-frequency, low-latency data ingestion and
-- powerful, flexible querying for ML model training and performance analysis.
-- =============================================================================

-- Table for the unique "DNA" of each arbitrage route.
-- This acts as the "Graph" node in our hybrid model.
CREATE TABLE IF NOT EXISTS route_registry (
    route_hash TEXT PRIMARY KEY, -- SHA256 of the sorted pool sequence
    path_json JSONB NOT NULL,    -- The sequence of pools, e.g., ["pool1", "pool2"]
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_route_registry_path_json ON route_registry USING GIN(path_json);

-- Time-series table for all simulation data, partitioned by month for performance.
-- This is the "Relational" time-series data linked to the Graph node.
CREATE TABLE IF NOT EXISTS simulation_audit (
    simulation_id BIGSERIAL,
    route_hash TEXT NOT NULL REFERENCES route_registry(route_hash),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata_jsonb JSONB NOT NULL, -- All simulation details: profitability, sizing, etc.
    PRIMARY KEY (simulation_id, recorded_at)
) PARTITION BY RANGE (recorded_at);

-- GIN index for fast queries on metadata (e.g., finding all simulations with a certain token).
CREATE INDEX IF NOT EXISTS idx_simulation_audit_metadata ON simulation_audit USING GIN(metadata_jsonb);

-- Example: Create partitions for the next few months. In production, this would be automated.
CREATE TABLE IF NOT EXISTS simulation_audit_y2026m07 PARTITION OF simulation_audit FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');
CREATE TABLE IF NOT EXISTS simulation_audit_y2026m08 PARTITION OF simulation_audit FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');
CREATE TABLE IF NOT EXISTS simulation_audit_y2026m09 PARTITION OF simulation_audit FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');

-- Table for the on-chain "truth" of an executed transaction.
CREATE TABLE IF NOT EXISTS execution_audit (
    execution_id BIGSERIAL PRIMARY KEY,
    simulation_id BIGINT UNIQUE NOT NULL REFERENCES simulation_audit(simulation_id, recorded_at), -- A simulation can only be executed once
    tx_hash TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL, -- e.g., 'success', 'reverted'
    net_profit_usd_truth NUMERIC,
    gas_used_truth BIGINT,
    executed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- The "Evolveline" View: Generates ML training data by joining simulation with execution truth.
-- This flattens the nested sizing iterations into a clean, ML-ready format.
CREATE OR REPLACE VIEW vqc_training_view AS
SELECT
    sim.simulation_id,
    sim.route_hash,
    -- Extract features from the main simulation metadata
    (sim.metadata_jsonb -> 'profitability' ->> 'gross_rate')::NUMERIC AS pre_math_gross_rate,
    (sim.metadata_jsonb -> 'profitability' ->> 'slippage_bps')::NUMERIC AS slippage_bps,
    jsonb_array_length(reg.path_json) - 1 AS num_legs,
    -- Unnest the sizing samples for more training data points
    (sample ->> 'principal')::NUMERIC AS principal_usd,
    -- The label: was the final execution profitable?
    (exec.net_profit_usd_truth > 0) AS is_profitable_truth
FROM
    simulation_audit sim
JOIN route_registry reg ON sim.route_hash = reg.route_hash
CROSS JOIN LATERAL jsonb_array_elements(sim.metadata_jsonb -> 'profitability' -> 'samples') AS sample
JOIN execution_audit exec ON sim.simulation_id = exec.simulation_id;

-- Live PnL Dashboard View: Monitors actual vs. simulated profit in real-time.
CREATE OR REPLACE VIEW live_pnl_dashboard_view AS
SELECT
    exec.executed_at AS timestamp,
    exec.tx_hash,
    reg.path_json AS route_path,
    (sim.metadata_jsonb -> 'optimal_injection_usd')::NUMERIC AS simulated_principal_usd,
    (sim.metadata_jsonb -> 'peak_surplus_usd')::NUMERIC AS simulated_net_profit_usd,
    exec.gas_used_truth,
    exec.net_profit_usd_truth AS actual_net_profit_usd,
    (exec.net_profit_usd_truth - (sim.metadata_jsonb -> 'peak_surplus_usd')::NUMERIC) AS net_delta_usd,
    exec.status
FROM
    execution_audit exec
JOIN
    simulation_audit sim ON exec.simulation_id = sim.simulation_id
JOIN
    route_registry reg ON sim.route_hash = reg.route_hash
ORDER BY
    exec.executed_at DESC;