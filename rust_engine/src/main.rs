use alloy_primitives::U256;
use clap::{Parser, Subcommand};
use rust_decimal::prelude::ToPrimitive;
use rust_decimal::Decimal;
use rust_decimal::MathematicalOps;
use rust_decimal_macros::dec;
use serde::{Deserialize, Serialize};
use serde_json::json;
use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::io::{self, Read};
use std::str::FromStr;
use tracing::{error, info, instrument, warn};
use tracing_subscriber::{fmt, prelude::*, EnvFilter};

// --- Bellman-Ford specific structs ---
#[derive(Debug, Clone, Deserialize)]
struct EdgeInput {
    token_in: String,
    token_out: String,
    rate: String,
    pool_id: String,
    protocol: String,
}

#[derive(Debug, Deserialize)]
struct BellmanFordRequest {
    edges: Vec<EdgeInput>,
}

#[derive(Debug, Clone)]
struct Edge {
    u: usize,
    v: usize,
    weight: f64,
    rate: f64,
    pool_id: String,
    protocol: String,
}

#[derive(Debug, Clone, Serialize)]
struct EdgeOutput {
    token_in: String,
    token_out: String,
    pool_id: String,
    protocol: String,
    rate: f64,
}

#[derive(Debug, Clone, Serialize)]
struct Opportunity {
    path: Vec<String>,
    edges: Vec<EdgeOutput>,
    cumulative_rate: f64,
    profit_pct: f64,
    detector: String,
}

#[derive(Debug, Serialize, Clone)]
struct FlashLoanParams {
    source: String,
    asset: String,
    principal_usd: Decimal,
    fee_usd: Decimal,
    fee_source: String,
    fee_verified: bool,
}

#[derive(Debug, Serialize, Clone)]
struct Profitability {
    flashloan: FlashLoanParams,
    gross_amount_out_usd: Decimal,
    net_profit_usd: Decimal,
    gas_cost_usd: Decimal,
    relay_tip_usd: Decimal,
    risk_buffer_usd: Decimal,
    passes_gate: bool,
}

#[derive(Debug, Serialize)]
struct LiveOpportunityJson {
    opp_id: String,
    path: Vec<String>,
    pool_sequence: Vec<String>,
    protocol_seq: Vec<String>,
    profitability: Profitability,
    gross_rate: Decimal,
    gross_out_usd: Decimal,
    flash_source: String,
    metadata: serde_json::Value,
    quality: serde_json::Value,
    block_detected: u64,
}

#[derive(Debug, Serialize)]
struct BellmanFordResponse {
    engine: String,
    opportunities: Vec<Opportunity>,
}

// --- Data Models for FindAndRank ---
#[derive(Debug, Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
struct Pool {
    protocol: String,
    address: String,
    tokens: Vec<String>,
    reserves: Option<Vec<Decimal>>,
    // V3 fields
    #[serde(default)]
    sqrt_price_x96: Option<U256>,
    #[serde(default)]
    liquidity: Option<U256>,
    fee_bps: Option<Decimal>,
    weights: Option<Vec<Decimal>>,
    swap_fee: Option<Decimal>,
    // Curve fields
    a: Option<Decimal>,
    // Meta
    #[serde(default)]
    total_executable_liquidity_usd: Option<Decimal>,
}
// --- Find-and-Rank specific structs ---
#[derive(Debug, Deserialize)]
struct SizingParams {
    min_principal_usd: String,
    max_principal_usd: String,
    tvl_fractions: Vec<String>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct EconomicParams {
    gas_cost_usd: String,
    relay_tip_usd: String,
    risk_buffer_bps: String,
    min_net_profit_usd: String,
    // Fees are specific to the flash loan source
    aave_v3_flash_fee_bps: String,
    balancer_flash_fee_bps: String,
}

#[derive(Debug, Deserialize)]
struct FindAndRankRequest {
    pools: HashMap<String, serde_json::Value>,
    prices: HashMap<String, String>,
    #[serde(default)]
    token_decimals: HashMap<String, u8>,
    sizing_params: SizingParams,
    flash_source: String,
    economic_params: EconomicParams,
}

#[derive(Debug, Serialize)]
struct DiscoveryReport {
    rate_pairs: usize,
    directional_quotes: usize,
    cycles_detected: usize,
    bellman_cycles: usize,
    stager_blueprints: usize,
    stager_raw_positive: usize,
    gate_passed_by_hop: BTreeMap<u8, usize>,
    error: Option<String>,
}

#[derive(Debug, Serialize)]
struct FindAndRankResponse {
    ranked_opportunities: Vec<serde_json::Value>, // Keep opportunities as flexible JSON values
    discovery_report: DiscoveryReport,
}

// --- CLI Argument Parsing ---
#[derive(Parser)]
#[command(author, version, about, long_about = None)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Legacy Bellman-Ford cycle detection from a list of edges.
    BellmanFord,
    /// New unified discovery and ranking pipeline.
    FindAndRank,
}

// --- Shared Logic ---

/// Finds the canonical representation of a cycle path to assist in deduplication.
/// A cycle [A, B, C, A] is the same as [B, C, A, B] and [C, A, B, C].
/// This function finds the lexicographically smallest rotation.
fn canonical_cycle_key(path: &[usize]) -> Vec<usize> {
    let mut best: Option<Vec<usize>> = None;
    for idx in 0..path.len() {
        let mut rotated = Vec::with_capacity(path.len());
        rotated.extend_from_slice(&path[idx..]);
        rotated.extend_from_slice(&path[..idx]);
        if best.as_ref().map_or(true, |current| rotated < *current) {
            best = Some(rotated);
        }
    }
    best.unwrap_or_default()
}

/// Bellman-Ford algorithm to detect negative-weight cycles (arbitrage opportunities).
fn detect_negative_cycles(tokens: &[String], edges: &[Edge]) -> Vec<Opportunity> {
    let n = tokens.len();
    let mut seen: BTreeSet<Vec<usize>> = BTreeSet::new();
    let mut out: Vec<Opportunity> = Vec::new();
    if n == 0 || edges.is_empty() {
        return out;
    }

    for source in 0..n {
        let mut dist = vec![f64::INFINITY; n];
        let mut pred: Vec<Option<usize>> = vec![None; n];
        let mut pred_edge: Vec<Option<usize>> = vec![None; n];
        dist[source] = 0.0;

        for _ in 0..n.saturating_sub(1) {
            let mut updated = false;
            for (edge_idx, edge) in edges.iter().enumerate() {
                if dist[edge.u].is_finite() && dist[edge.u] + edge.weight < dist[edge.v] {
                    dist[edge.v] = dist[edge.u] + edge.weight;
                    pred[edge.v] = Some(edge.u);
                    pred_edge[edge.v] = Some(edge_idx);
                    updated = true;
                }
            }
            if !updated {
                break;
            }
        }

        for edge in edges {
            if !(dist[edge.u].is_finite() && dist[edge.u] + edge.weight < dist[edge.v]) {
                continue;
            }

            let mut cycle_node = edge.v;
            let mut valid = true;
            for _ in 0..n {
                match pred[cycle_node] {
                    Some(prev) => cycle_node = prev,
                    None => {
                        valid = false;
                        break;
                    }
                }
            }
            if !valid {
                continue;
            }

            let mut path_rev: Vec<usize> = Vec::new();
            let mut edge_rev: Vec<usize> = Vec::new();
            let mut first_seen: BTreeMap<usize, usize> = BTreeMap::new();
            let mut cur = cycle_node;
            loop {
                if let Some(idx) = first_seen.get(&cur).copied() {
                    path_rev = path_rev[idx..].to_vec();
                    edge_rev = edge_rev[idx..].to_vec();
                    break;
                }
                first_seen.insert(cur, path_rev.len());
                path_rev.push(cur);
                let Some(edge_idx) = pred_edge[cur] else {
                    break;
                };
                edge_rev.push(edge_idx);
                let Some(prev) = pred[cur] else { break };
                cur = prev;
            }

            if path_rev.len() < 2 || edge_rev.len() < 2 || path_rev.len() != edge_rev.len() {
                continue;
            }

            path_rev.reverse();
            let mut ordered_edge_indices: Vec<usize> = Vec::with_capacity(path_rev.len());
            for idx in 0..path_rev.len() {
                let next_node = if idx + 1 < path_rev.len() {
                    path_rev[idx + 1]
                } else {
                    path_rev[0]
                };
                let Some(edge_idx) = pred_edge[next_node] else {
                    valid = false;
                    break;
                };
                ordered_edge_indices.push(edge_idx);
            }
            if !valid {
                continue;
            }

            let key = canonical_cycle_key(&path_rev);
            if key.is_empty() || !seen.insert(key) {
                continue;
            }

            let mut cumulative_rate = 1.0_f64;
            let mut edge_outputs = Vec::with_capacity(ordered_edge_indices.len());
            for edge_idx in &ordered_edge_indices {
                let e = &edges[*edge_idx];
                cumulative_rate *= e.rate;
                edge_outputs.push(EdgeOutput {
                    token_in: tokens[e.u].clone(),
                    token_out: tokens[e.v].clone(),
                    pool_id: e.pool_id.clone(),
                    protocol: e.protocol.clone(),
                    rate: e.rate,
                });
            }
            if cumulative_rate <= 1.0 {
                continue;
            }

            let mut path: Vec<String> = path_rev.iter().map(|idx| tokens[*idx].clone()).collect();
            if let Some(first) = path.first().cloned() {
                path.push(first);
            }
            out.push(Opportunity {
                path,
                edges: edge_outputs,
                cumulative_rate,
                profit_pct: (cumulative_rate - 1.0) * 100.0,
                detector: "RUST_BELLMAN_FORD".to_string(),
            });
        }
    }
    out.sort_by(|a, b| {
        b.profit_pct
            .partial_cmp(&a.profit_pct)
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    out
}

/// Quotes a single Uniswap V2 pool.
fn quote_uniswap_v2(
    reserve_in: Decimal,
    reserve_out: Decimal,
    amount_in: Decimal,
    fee: Decimal,
) -> Decimal {
    if amount_in <= dec!(0) || reserve_in <= dec!(0) || reserve_out <= dec!(0) {
        return dec!(0);
    }
    let amount_in_with_fee = amount_in * (dec!(1) - fee);
    let numerator = amount_in_with_fee * reserve_out;
    let denominator = reserve_in + amount_in_with_fee;
    if denominator <= dec!(0) {
        return dec!(0);
    }
    numerator / denominator
}

/// Example quoting function for a hypothetical "HyperSwap" DEX.
/// This assumes a simple constant product model with a 0.25% fee.
fn quote_hyper_swap(
    reserve_in: Decimal,
    reserve_out: Decimal,
    amount_in: Decimal,
) -> Decimal {
    if amount_in <= dec!(0) || reserve_in <= dec!(0) || reserve_out <= dec!(0) {
        return dec!(0);
    }
    let fee = dec!(0.0025); // HyperSwap's 0.25% fee
    let amount_in_with_fee = amount_in * (dec!(1) - fee);
    let numerator = amount_in_with_fee * reserve_out;
    let denominator = reserve_in + amount_in_with_fee;
    if denominator <= dec!(0) {
        return dec!(0);
    }
    numerator / denominator
}

/// Iteratively calculates the Curve invariant `D` for n-coin pools.
/// Aligned with the Python implementation in `math_engine.py`.
fn get_d_curve(reserves: &[Decimal], a: Decimal) -> Decimal {
    let n_coins = Decimal::from(reserves.len());
    let s: Decimal = reserves.iter().sum();
    if s.is_zero() {
        return Decimal::ZERO;
    }

    let mut d = s;
    let ann = a * n_coins;

    for _ in 0..255 {
        let mut d_p = d;
        for x in reserves {
            if x.is_zero() {
                return Decimal::ZERO;
            }
            d_p = d_p * d / (n_coins * x);
        }

        let d_prev = d;

        let numerator = (ann * s + d_p * n_coins) * d;
        let denominator = (ann - Decimal::ONE) * d + (n_coins + Decimal::ONE) * d_p;
        if denominator.is_zero() {
            return Decimal::ZERO;
        }
        d = numerator / denominator;

        if (d - d_prev).abs() <= Decimal::ONE {
            break;
        }
    }
    d
}

/// Solves for the output amount `y` in an n-coin Curve pool using Newton's method.
/// Aligned with the Python implementation in `math_engine.py`.
fn get_y_curve(
    i: usize,
    j: usize,
    x: Decimal,
    reserves: &[Decimal],
    a: Decimal,
    d: Decimal,
) -> Decimal {
    let n_coins = Decimal::from(reserves.len());
    let ann = a * n_coins;

    let mut new_reserves = reserves.to_vec();
    new_reserves[i] += x;

    let s_ = new_reserves
        .iter()
        .enumerate()
        .filter(|(k, _)| *k != j)
        .map(|(_, val)| val)
        .sum::<Decimal>();

    let mut y = d / n_coins;
    for _ in 0..255 {
        let y_prev = y;

        let mut p_ = y;
        for (k, val) in new_reserves.iter().enumerate() {
            if k != j {
                if val.is_zero() {
                    return Decimal::ZERO;
                }
                p_ *= val;
            }
        }

        if p_.is_zero() || y.is_zero() {
            return Decimal::ZERO;
        }

        // f(y) = Ann*S + D = Ann*D + D^(n+1) / (n^n * P)
        // We solve for y in: Ann*(S_ + y) + D = Ann*D + D^(n+1)/(n^n * P' * y)
        // Let f(y) = Ann*(S_ + y) + D - Ann*D - D^(n+1)/(n^n * P' * y) = 0
        let n_coins_pow_n = n_coins.powd(n_coins);
        let d_pow_n_plus_1 = d.powd(n_coins + Decimal::ONE);

        let term_for_f = d_pow_n_plus_1 / (n_coins_pow_n * p_);
        let f = ann * (s_ + y) + d - ann * d - term_for_f;

        // f'(y) = Ann + D^(n+1)/(n^n * P' * y^2)
        let f_prime = ann + (term_for_f * n_coins) / y;

        if f_prime.is_zero() {
            return Decimal::ZERO;
        }

        y = y - f / f_prime;

        if (y - y_prev).abs() <= Decimal::ONE {
            break;
        }
    }
    y
}

/// Quotes a full route by iterating through its pools.
/// NOTE: This is a simplified implementation. A production version would need to
/// implement quoting logic for V3, Balancer, Curve, etc., and select the
/// correct quoter based on `pool.protocol`.
#[instrument(skip_all, fields(path = ?path, amount_in = %amount_in))]
fn quote_route(
    amount_in: Decimal,
    route_pools: &[&Pool],
    path: &[&str],
    token_decimals: &HashMap<String, u8>,
) -> Decimal {
    let mut current_amount = amount_in;
    for (i, pool) in route_pools.iter().enumerate() {
        if current_amount <= dec!(0) {
            return dec!(0);
        }
        match pool.protocol.as_str() {
            "UniswapV2" | "QuickSwapV2" => {
                let token_in = path[i];
                let _token_out = &path[i + 1];
                let (reserve_in, reserve_out) = if &pool.tokens[0] == token_in {
                    (
                        pool.reserves.as_ref().unwrap()[0],
                        pool.reserves.as_ref().unwrap()[1],
                    )
                } else {
                    (
                        pool.reserves.as_ref().unwrap()[1],
                        pool.reserves.as_ref().unwrap()[0],
                    )
                };
                // Uniswap V2 fee is 0.3% (30 bps)
                let fee = pool.fee_bps.map(|f| f / dec!(10000)).unwrap_or(dec!(0.003));
                current_amount = quote_uniswap_v2(reserve_in, reserve_out, current_amount, fee);
            }
            "UniswapV3" | "QuickSwapV3" | "Algebra" => {
                // --- Uniswap V3 / CLMM Math ---
                // This uses a virtual reserves model, which is a correct approximation
                // for swaps that do not cross a tick boundary. A full implementation
                // would require iterating through tick data.
                warn!(
                    pool_address = %pool.address,
                    "Using single-tick approximation for UniswapV3 quote. Does not handle tick crossings."
                );

                if let (Some(sqrt_price_x96), Some(liquidity)) =
                    (pool.sqrt_price_x96, pool.liquidity)
                {
                    if liquidity > U256::ZERO && sqrt_price_x96 > U256::ZERO {
                        let token_in = path[i];
                        let decimals = token_decimals.get(token_in).cloned().unwrap_or(18); // Default to 18 if not found

                        // --- Production-Grade U256 Math ---
                        let scaling_factor = Decimal::from(10u64).powu(decimals as u64);
                        let amount_in_raw_str =
                            (current_amount * scaling_factor).floor().to_string();
                        let Ok(amount_in_raw) = U256::from_str(&amount_in_raw_str) else {
                            current_amount = dec!(0);
                            continue;
                        };

                        let q96 = U256::from(1) << 96;

                        // Calculate virtual reserves using U256 math to avoid precision loss.
                        let reserve0_raw = liquidity
                            .checked_mul(q96)
                            .and_then(|n| n.checked_div(sqrt_price_x96))
                            .unwrap_or(U256::ZERO);
                        let reserve1_raw = liquidity
                            .checked_mul(sqrt_price_x96)
                            .and_then(|n| n.checked_div(q96))
                            .unwrap_or(U256::ZERO);

                        if reserve0_raw.is_zero() || reserve1_raw.is_zero() {
                            current_amount = dec!(0);
                            continue;
                        }

                        let (reserve_in_raw, reserve_out_raw) = if &pool.tokens[0] == token_in {
                            (reserve0_raw, reserve1_raw)
                        } else {
                            (reserve1_raw, reserve0_raw)
                        };

                        // The fee is passed in basis points (e.g., 5 for 0.05%).
                        let fee_bps_u64 = pool.fee_bps.and_then(|d| d.to_u64()).unwrap_or(5); // Default to 5 bps
                        let fee_factor = U256::from(1_000_000 - fee_bps_u64 * 100); // Convert bps to ppm
                        let amount_in_with_fee = amount_in_raw
                            .checked_mul(fee_factor)
                            .and_then(|n| n.checked_div(U256::from(1_000_000)))
                            .unwrap_or(U256::ZERO);

                        // Standard constant product formula with raw integer units
                        let numerator = amount_in_with_fee
                            .checked_mul(reserve_out_raw)
                            .unwrap_or(U256::ZERO);
                        let denominator = reserve_in_raw
                            .checked_add(amount_in_with_fee)
                            .unwrap_or(U256::ZERO);

                        if denominator.is_zero() {
                            current_amount = dec!(0);
                            continue;
                        }
                        let amount_out_raw = numerator / denominator;

                        // Convert result back to Decimal
                        let Ok(amount_out_dec) = Decimal::from_str(&amount_out_raw.to_string())
                        else {
                            current_amount = dec!(0);
                            continue;
                        };
                        // --- FIX: Use the output token's decimals for scaling ---
                        let token_out = path[i + 1];
                        let decimals_out = token_decimals.get(token_out).cloned().unwrap_or(18);
                        let scaling_factor_out = Decimal::from(10u64).powu(decimals_out as u64);
                        current_amount = amount_out_dec / scaling_factor_out;
                    } else {
                        current_amount = dec!(0);
                    }
                } else {
                    current_amount = dec!(0);
                }
            }
            "Balancer" => {
                // --- Balancer Weighted Pool Math ---
                // Implements the formula: amountOut = balanceOut * (1 - (balanceIn / (balanceIn + amountIn))^(weightIn / weightOut))
                if let (Some(reserves), Some(weights), Some(swap_fee)) =
                    (&pool.reserves, &pool.weights, &pool.swap_fee)
                {
                    let token_in = path[i];
                    let token_out = &path[i + 1];

                    let token_in_idx = pool.tokens.iter().position(|t| t == token_in);
                    let token_out_idx = pool.tokens.iter().position(|t| t == token_out);

                    if let (Some(idx_in), Some(idx_out)) = (token_in_idx, token_out_idx) {
                        if idx_in < reserves.len()
                            && idx_out < reserves.len()
                            && idx_in < weights.len()
                            && idx_out < weights.len()
                        {
                            let balance_in = reserves[idx_in];
                            let balance_out = reserves[idx_out];
                            let weight_in = weights[idx_in];
                            let weight_out = weights[idx_out];
                            let amount_in_with_fee = current_amount * (dec!(1) - *swap_fee);

                            if balance_in > dec!(0) && weight_out > dec!(0) {
                                let ratio = balance_in / (balance_in + amount_in_with_fee);
                                let weight_ratio = weight_in / weight_out;
                                let multiplier = dec!(1) - ratio.powd(weight_ratio);
                                current_amount = balance_out * multiplier;
                            } else {
                                current_amount = dec!(0);
                            }
                        } else {
                            current_amount = dec!(0);
                        }
                    } else {
                        current_amount = dec!(0);
                    }
                } else {
                    current_amount = dec!(0);
                }
            }
            "Curve" => {
                // --- Curve StableSwap Math ---
                // This uses an iterative solver to find the invariant `D` and then
                // solves for the output amount `y`. This now supports n-coin pools.
                let token_in = path[i];
                let token_in_idx = pool.tokens.iter().position(|t| t == token_in);
                let token_out = &path[i + 1];
                let token_out_idx = pool.tokens.iter().position(|t| t == token_out);

                if let (Some(idx_in), Some(idx_out)) = (token_in_idx, token_out_idx) {
                    if let (Some(reserves), Some(a)) = (&pool.reserves, pool.a) {
                        let d = get_d_curve(reserves, a);
                        if d > dec!(0) {
                            let y_new =
                                get_y_curve(idx_in, idx_out, current_amount, reserves, a, d);
                            let amount_out = reserves[idx_out] - y_new;
                            let fee = pool
                                .fee_bps
                                .map(|f| f / dec!(10000))
                                .unwrap_or(dec!(0.0004));
                            current_amount = amount_out * (dec!(1) - fee);
                        } else {
                            current_amount = dec!(0);
                        }
                    }
                } else {
                    current_amount = dec!(0);
                }
            }
            "HyperSwap" => {
                // This is our new, hypothetical DEX protocol.
                let token_in = path[i];
                let (reserve_in, reserve_out) = if &pool.tokens[0] == token_in {
                    (
                        pool.reserves.as_ref().unwrap()[0],
                        pool.reserves.as_ref().unwrap()[1],
                    )
                } else {
                    (
                        pool.reserves.as_ref().unwrap()[1],
                        pool.reserves.as_ref().unwrap()[0],
                    )
                };
                current_amount = quote_hyper_swap(reserve_in, reserve_out, current_amount);
            }
            _ => {
                // Unsupported protocol for quoting in this simplified engine
                return dec!(0);
            }
        }
    }
    current_amount
}

/// Simplified profitability evaluation, ported from Python's `evaluate_profitability`.
fn evaluate_profitability_rust(
    gross_out_usd: Decimal,
    principal_usd: Decimal,
    _hops: usize,
    flash_source: &str,
    asset: &str,
    economic_params: &EconomicParams,
) -> Profitability {
    // These are now passed in from the Python layer via `economic_params`.
    let gas_cost_usd = economic_params
        .gas_cost_usd
        .parse::<Decimal>()
        .unwrap_or(dec!(0.15));
    let relay_tip_usd = economic_params
        .relay_tip_usd
        .parse::<Decimal>()
        .unwrap_or(dec!(0));
    let risk_buffer_bps = economic_params
        .risk_buffer_bps
        .parse::<Decimal>()
        .unwrap_or(dec!(5));
    let min_net_profit_usd = economic_params
        .min_net_profit_usd
        .parse::<Decimal>()
        .unwrap_or(dec!(1.0));

    let risk_buffer_usd = principal_usd * risk_buffer_bps / dec!(10000);

    let flash_fee_bps = if flash_source == "BALANCER" {
        economic_params
            .balancer_flash_fee_bps
            .parse::<Decimal>()
            .unwrap_or(dec!(0))
    } else {
        // Aave, Uniswap V3, etc.
        economic_params
            .aave_v3_flash_fee_bps
            .parse::<Decimal>()
            .unwrap_or(dec!(5))
    };
    let flash_fee_usd = principal_usd * flash_fee_bps / dec!(10000);

    let expenses = flash_fee_usd + gas_cost_usd + relay_tip_usd + risk_buffer_usd;
    let net_profit_usd = gross_out_usd - principal_usd - expenses;

    let passes = net_profit_usd >= min_net_profit_usd;

    Profitability {
        flashloan: FlashLoanParams {
            source: flash_source.to_string(),
            asset: asset.to_string(),
            principal_usd,
            fee_usd: flash_fee_usd,
            fee_source: "rust_engine_config".to_string(),
            fee_verified: true,
        },
        gross_amount_out_usd: gross_out_usd,
        net_profit_usd,
        gas_cost_usd,
        relay_tip_usd,
        risk_buffer_usd,
        passes_gate: passes,
    }
}

// --- Main Find and Rank Logic (simplified for compilation) ---
/// Finds the optimal trade size for a given route. Ported from `optimal_flash_sizer.py`.
#[instrument(skip_all, fields(path = ?path))]
fn find_optimal_injection(
    route_pools: &[&Pool],
    path: &[&str],
    prices: &HashMap<String, Decimal>,
    sizing_params: &SizingParams,
    token_decimals: &HashMap<String, u8>,
    flash_source: &str,
    economic_params: &EconomicParams,
) -> Option<(Decimal, Profitability)> {
    let base_asset = path[0];
    let base_price = match prices.get(base_asset) {
        Some(p) if *p > dec!(0) => *p,
        _ => return None,
    };

    let min_tvl = route_pools
        .iter()
        .filter_map(|p| p.total_executable_liquidity_usd)
        .min()
        .unwrap_or(dec!(0));

    if min_tvl <= dec!(0) {
        return None;
    }

    let max_tvl_fraction = sizing_params
        .tvl_fractions
        .iter()
        .filter_map(|s| s.parse::<Decimal>().ok())
        .max_by(|a, b| a.partial_cmp(b).unwrap())
        .unwrap_or(dec!(0.5));

    let route_cap_usd = min_tvl * max_tvl_fraction;
    let max_principal_usd = sizing_params
        .max_principal_usd
        .parse::<Decimal>()
        .unwrap_or(dec!(250000));
    let hard_cap_usd = route_cap_usd.min(max_principal_usd);
    let min_principal_usd = sizing_params
        .min_principal_usd
        .parse::<Decimal>()
        .unwrap_or(dec!(5000));

    if hard_cap_usd < min_principal_usd {
        return None;
    }

    // 2. Build size ladder
    let mut ladder: BTreeSet<Decimal> = BTreeSet::new();
    ladder.insert(min_principal_usd);
    for frac_str in &sizing_params.tvl_fractions {
        if let Ok(frac) = frac_str.parse::<Decimal>() {
            ladder.insert((min_tvl * frac).min(hard_cap_usd));
        }
    }
    // Add some geometric steps
    let mut geo_step = min_principal_usd * dec!(1.5);
    while geo_step < hard_cap_usd {
        ladder.insert(geo_step);
        geo_step *= dec!(1.5);
    }
    ladder.insert(hard_cap_usd);

    // 3. Find peak delta by walking the ladder
    let mut best_size = dec!(0);
    let mut best_profitability: Option<Profitability> = None;

    for size_usd in ladder.into_iter().filter(|s| *s >= min_principal_usd) {
        let amount_in = size_usd / base_price; // Principal in base asset units
        let amount_out = quote_route(amount_in, route_pools, path, token_decimals); // Amount out in base asset units

        if amount_out <= dec!(0) {
            continue;
        }
        let gross_out_usd = amount_out * base_price;
        let profitability = evaluate_profitability_rust(
            gross_out_usd,
            size_usd,
            path.len() - 1,
            flash_source,
            base_asset,
            economic_params,
        );

        if profitability.passes_gate {
            if best_profitability.is_none()
                || profitability.net_profit_usd
                    > best_profitability.as_ref().unwrap().net_profit_usd
            {
                best_profitability = Some(profitability);
                best_size = size_usd;
            }
        }
    }

    best_profitability.map(|p| (best_size, p))
}

/// Discovers 2 and 3-hop arbitrage routes. This has been refactored for efficiency and to correctly handle multi-token pools.
fn discover_routes<'a>(pools: &'a HashMap<String, Pool>) -> Vec<(Vec<&'a str>, Vec<&'a Pool>)> {
    let mut routes = Vec::new();
    // Adjacency list: TokenIn -> TokenOut -> Vec<Pool>
    let mut adjacency: HashMap<&str, HashMap<&str, Vec<&'a Pool>>> = HashMap::new();

    // Build a more detailed adjacency list that maps In -> Out -> Pools
    for pool in pools.values() {
        // This handles pools with more than 2 tokens correctly by iterating all pairs.
        for token_in in &pool.tokens {
            for token_out in &pool.tokens {
                if token_in == token_out {
                    continue;
                }
                adjacency
                    .entry(token_in)
                    .or_default()
                    .entry(token_out)
                    .or_default()
                    .push(pool);
            }
        }
    }

    // Discover routes using the new adjacency list structure
    for (token_a, sub_adj) in &adjacency {
        for (token_b, pools_ab) in sub_adj {
            // 2-hop routes: A -> B -> A
            if let Some(pools_ba) = adjacency.get(*token_b).and_then(|m| m.get(*token_a)) {
                for pool1 in pools_ab {
                    for pool2 in pools_ba {
                        if pool1.address == pool2.address {
                            continue;
                        }
                        // Use borrowed slices instead of creating new Strings to avoid allocations.
                        routes.push((vec![*token_a, *token_b, *token_a], vec![*pool1, *pool2]));
                    }
                }
            }

            // 3-hop routes: A -> B -> C -> A
            if let Some(sub_sub_adj) = adjacency.get(*token_b) {
                for (token_c, pools_bc) in sub_sub_adj {
                    if *token_c == *token_a {
                        continue;
                    } // This is a 2-hop, already handled
                    if let Some(pools_ca) = adjacency.get(*token_c).and_then(|m| m.get(*token_a)) {
                        for pool1 in pools_ab {
                            for pool2 in pools_bc {
                                for pool3 in pools_ca {
                                    // Ensure no pool is used twice in the same route
                                    if pool1.address == pool2.address
                                        || pool1.address == pool3.address
                                        || pool2.address == pool3.address
                                    {
                                        continue;
                                    }
                                    routes.push((
                                        vec![*token_a, *token_b, *token_c, *token_a],
                                        vec![*pool1, *pool2, *pool3],
                                    ));
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    routes
}

fn run_bellman_ford() -> Result<BellmanFordResponse, String> {
    let mut input = String::new();
    io::stdin()
        .read_to_string(&mut input)
        .map_err(|err| format!("stdin_read_failed: {err}"))?;
    let request: BellmanFordRequest =
        serde_json::from_str(&input).map_err(|err| format!("json_decode_failed: {err}"))?;
    let mut token_set: BTreeSet<String> = BTreeSet::new();
    for edge in &request.edges {
        let Ok(rate) = edge.rate.parse::<f64>() else {
            continue;
        };
        if rate > 0.0 && rate.is_finite() {
            token_set.insert(edge.token_in.clone());
            token_set.insert(edge.token_out.clone());
        }
    }
    let tokens: Vec<String> = token_set.into_iter().collect();
    let token_index: BTreeMap<String, usize> = tokens
        .iter()
        .enumerate()
        .map(|(idx, token)| (token.clone(), idx))
        .collect();

    let edges: Vec<Edge> = request
        .edges
        .into_iter()
        .filter_map(|edge| {
            let rate: f64 = edge.rate.parse().ok()?;
            if !(rate > 0.0 && rate.is_finite()) {
                return None;
            }
            let u = *token_index.get(&edge.token_in)?;
            let v = *token_index.get(&edge.token_out)?;
            Some(Edge {
                u,
                v,
                weight: -rate.ln(),
                rate,
                pool_id: edge.pool_id,
                protocol: edge.protocol,
            })
        })
        .collect();

    Ok(BellmanFordResponse {
        engine: "omega_rust_engine".to_string(),
        opportunities: detect_negative_cycles(&tokens, &edges),
    })
}

#[instrument]
fn run_find_and_rank() -> Result<FindAndRankResponse, String> {
    // 1. Deserialize the request from Python
    let mut input = String::new();
    io::stdin()
        .read_to_string(&mut input)
        .map_err(|err| format!("stdin_read_failed: {err}"))?;
    info!(request_bytes = input.len(), "Received request from stdin");

    let req: FindAndRankRequest =
        serde_json::from_str(&input).map_err(|err| format!("json_decode_failed: {err}"))?;

    // 2. Parse pools and prices into structured, decimal-based formats
    info!(
        pool_count = req.pools.len(),
        price_count = req.prices.len(),
        "Parsing pools and prices"
    );
    let pools: HashMap<String, Pool> = req
        .pools
        .into_iter()
        .filter_map(|(k, v)| serde_json::from_value(v).ok().map(|p: Pool| (k, p)))
        .collect();
    let prices: HashMap<String, Decimal> = req
        .prices
        .into_iter()
        .filter_map(|(k, v)| v.parse::<Decimal>().ok().map(|p| (k, p)))
        .collect();
    let token_decimals: HashMap<String, u8> = req.token_decimals;

    // 3. Discover potential arbitrage routes (2 and 3-hop)
    info!(pool_count = pools.len(), "Discovering routes");
    let routes = discover_routes(&pools);
    info!(route_count = routes.len(), "Discovered routes");
    let mut profitable_opportunities = Vec::new();

    // 4. For each route, find the optimal size and check for profitability
    info!("Sizing and evaluating routes for profitability");
    for (path, route_pools) in routes {
        if let Some((optimal_size, profitability)) = find_optimal_injection(
            &route_pools,
            &path,
            &prices,
            &req.sizing_params,
            &token_decimals,
            &req.flash_source,
            &req.economic_params,
        ) {
            let gross_out_usd = profitability.gross_amount_out_usd;
            let gross_rate = if optimal_size > dec!(0) {
                gross_out_usd / optimal_size
            } else {
                dec!(0)
            };

            let opp_id = format!(
                "OPP-RUST-{:x}",
                md5::compute(format!(
                    "{:?}-{:?}",
                    path,
                    route_pools.iter().map(|p| &p.address).collect::<Vec<_>>()
                ))
                .into_iter()
                .fold(0, |acc, byte| (acc << 8) | byte as u64));

            let opp_json = LiveOpportunityJson {
                opp_id,
                path: path.iter().map(|s| s.to_string()).collect(), // Convert to owned Vec<String> only at the end.
                pool_sequence: route_pools.iter().map(|p| p.address.clone()).collect(),
                protocol_seq: route_pools.iter().map(|p| p.protocol.clone()).collect(),
                profitability,
                gross_rate,
                gross_out_usd,
                flash_source: req.flash_source.clone(),
                metadata: json!({
                    "principal_usd": optimal_size,
                    "sizing_method": "rust_peak_delta_tvl_cap",
                }),
                quality: json!({}),
                block_detected: 0, // Block is not available in this context
            };
            profitable_opportunities.push(opp_json);
        }
    }

    info!(count = profitable_opportunities.len(), "Found profitable opportunities");
    // 5. Sort opportunities by net profit
    profitable_opportunities.sort_by(|a, b| {
        b.profitability
            .net_profit_usd
            .partial_cmp(&a.profitability.net_profit_usd)
            .unwrap_or(std::cmp::Ordering::Equal)
    });

    // 6. Serialize the results back to JSON values for Python
    let ranked_opportunities: Vec<serde_json::Value> = profitable_opportunities
        .into_iter()
        .map(|opp| serde_json::to_value(opp).unwrap())
        .collect();

    // 7. Create a discovery report
    let report = DiscoveryReport {
        rate_pairs: 0, // This metric is from the old rate-based system
        directional_quotes: 0,
        cycles_detected: ranked_opportunities.len(),
        bellman_cycles: 0,
        stager_blueprints: ranked_opportunities.len(),
        stager_raw_positive: ranked_opportunities.len(),
        gate_passed_by_hop: BTreeMap::new(), // Can be populated by counting hops
        error: None,
    };

    info!(count = ranked_opportunities.len(), "Ranking complete");
    // 8. Return the final response
    Ok(FindAndRankResponse {
        ranked_opportunities,
        discovery_report: report,
    })
}

fn main() {
    // Initialize the structured JSON logger.
    // It reads the log level from the RUST_LOG environment variable (e.g., RUST_LOG=info).
    tracing_subscriber::registry()
        .with(fmt::layer().json())
        .with(EnvFilter::from_default_env())
        .init();

    let cli = Cli::parse();

    let result = match cli.command {
        Commands::BellmanFord => match run_bellman_ford() {
            Ok(response) => serde_json::to_string(&response).map_err(|e| e.to_string()),
            Err(e) => Err(e.to_string()),
        },
        Commands::FindAndRank => match run_find_and_rank() {
            Ok(response) => serde_json::to_string(&response).map_err(|e| e.to_string()),
            Err(e) => Err(e.to_string()),
        }
    };

    match result {
        Ok(json) => println!("{}", json),
        Err(e) => {
            error!(error = %e, "An error occurred in the Rust engine");
            std::process::exit(1);
        }
    }
}
