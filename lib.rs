use alloy_primitives::Address;
use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;
use rust_decimal::Decimal;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::str::FromStr;

/// Configuration for the strict validation gates (locked canon).
#[pyclass]
#[derive(Debug, Clone)]
pub struct GateConfig {
    #[pyo3(get, set)]
    pub min_tvl_usd: String,
    #[pyo3(get, set)]
    pub chain_id: u64,
}

#[pymethods]
impl GateConfig {
    #[new]
    fn new(min_tvl_usd: String, chain_id: u64) -> Self {
        GateConfig { min_tvl_usd, chain_id }
    }
}

/// Error types for validation.
#[derive(Debug, thiserror::Error)]
pub enum ValidationError {
    #[error("Buy pool address cannot be the same as the sell pool address.")]
    SamePool,
    #[error("Executable buy price must be strictly less than executable sell price. Got buy: {0}, sell: {1}")]
    UnprofitablePrice(Decimal, Decimal),
    #[error("Pool TVL below minimum threshold")]
    LowTvl,
    #[error("Failed to parse numeric value: {0}")]
    ParseError(String),
}

impl From<ValidationError> for PyErr {
    fn from(err: ValidationError) -> PyErr {
        PyValueError::new_err(err.to_string())
    }
}

/// Candidate for arbitrage leg pair. Price-driven only.
/// Metadata (protocol, etc.) is carried but NEVER used for selection.
#[pyclass]
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Candidate {
    #[pyo3(get, set)]
    pub buy_pool_address: String,
    #[pyo3(get, set)]
    pub sell_pool_address: String,
    #[pyo3(get, set)]
    pub token_in: String,
    #[pyo3(get, set)]
    pub token_mid: String,

    #[pyo3(get, set)]
    pub buy_pool_tvl_usd: String,
    #[pyo3(get, set)]
    pub executable_buy_price: String,   // lower is better for buy
    #[pyo3(get, set)]
    pub executable_sell_price: String,  // higher is better for sell

    // DNA / metadata only - not for ranking
    #[pyo3(get, set)]
    pub buy_pool_protocol: String,
    #[pyo3(get, set)]
    pub sell_pool_protocol: String,
}

#[pymethods]
impl Candidate {
    #[new]
    fn new() -> Self {
        Candidate {
            buy_pool_address: String::new(),
            sell_pool_address: String::new(),
            token_in: String::new(),
            token_mid: String::new(),
            buy_pool_tvl_usd: "0".to_string(),
            executable_buy_price: "0".to_string(),
            executable_sell_price: "0".to_string(),
            buy_pool_protocol: String::new(),
            sell_pool_protocol: String::new(),
        }
    }

    /// Strict gate validation per locked canon.
    /// - chain_id must be 137 (enforced if provided)
    /// - tvl >= min_tvl_usd (default 50000)
    /// - different pools
    /// - buy_price < sell_price
    pub fn validate(&self, config: &GateConfig) -> PyResult<()> {
        if config.chain_id != 0 && config.chain_id != 137 {
            return Err(PyValueError::new_err("Only chain_id 137 is supported"));
        }

        let min_tvl = Decimal::from_str(&config.min_tvl_usd)
            .map_err(|e| ValidationError::ParseError(e.to_string()))?;
        let tvl = Decimal::from_str(&self.buy_pool_tvl_usd)
            .map_err(|e| ValidationError::ParseError(e.to_string()))?;

        if tvl < min_tvl {
            return Err(ValidationError::LowTvl.into());
        }

        if self.buy_pool_address == self.sell_pool_address || self.buy_pool_address.is_empty() {
            return Err(ValidationError::SamePool.into());
        }

        let buy_p = Decimal::from_str(&self.executable_buy_price)
            .map_err(|e| ValidationError::ParseError(e.to_string()))?;
        let sell_p = Decimal::from_str(&self.executable_sell_price)
            .map_err(|e| ValidationError::ParseError(e.to_string()))?;

        if buy_p >= sell_p {
            return Err(ValidationError::UnprofitablePrice(buy_p, sell_p).into());
        }

        Ok(())
    }
}

/// Pure price-driven selection: min buy price or max sell price.
/// No protocol or venue override allowed.
#[pyfunction]
fn find_best_quote(candidates: Vec<PyRef<Candidate>>, find_min: bool) -> PyResult<Option<Py<Candidate>>> {
    if candidates.is_empty() {
        return Ok(None);
    }

    let mut best: Option<Py<Candidate>> = None;
    let mut best_val = if find_min { Decimal::MAX } else { Decimal::MIN };

    for c in candidates {
        let price_str = if find_min { &c.executable_buy_price } else { &c.executable_sell_price };
        let price = Decimal::from_str(price_str)
            .map_err(|e| ValidationError::ParseError(e.to_string()))?;

        let is_better = if find_min { price < best_val } else { price > best_val };
        if is_better {
            best_val = price;
            best = Some(c.into());
        }
    }
    Ok(best)
}

/// Raw pool input from Python host.
#[derive(Debug, Clone, Deserialize)]
struct RawPool {
    protocol: String,
    address: String,
    tokens: Vec<String>,
    #[serde(rename = "total_executable_liquidity_usd")]
    tvl_usd: String,
    executable_price: String,
}

/// Main scanner entrypoint. Pure price driven per canon.
/// Groups by pairs, selects min buy / max sell, applies gates.
/// Uniswap V3 and Algebra are treated as separate (via protocol field).
#[pyfunction]
fn scan_opportunities(pools_json: String, config: &GateConfig) -> PyResult<Vec<Candidate>> {
    let pools: HashMap<String, RawPool> = serde_json::from_str(&pools_json)
        .map_err(|e| PyValueError::new_err(format!("JSON parse error: {}", e)))?;

    let mut pair_pools: HashMap<(String, String), Vec<&RawPool>> = HashMap::new();
    for pool in pools.values() {
        if pool.tokens.len() == 2 {
            let key = (pool.tokens[0].clone(), pool.tokens[1].clone());
            pair_pools.entry(key).or_default().push(pool);
        }
    }

    let mut candidates = Vec::new();
    let mut seen_tokens: std::collections::HashSet<String> = std::collections::HashSet::new();
    for p in pools.values() {
        for t in &p.tokens {
            seen_tokens.insert(t.clone());
        }
    }
    let tokens: Vec<String> = seen_tokens.into_iter().collect();

    for token_a in &tokens {
        for token_b in &tokens {
            if token_a == token_b { continue; }

            let key_ab = (token_a.clone(), token_b.clone());

            // Best buy: lowest price (min executable_buy_price)
            let best_buy = pair_pools.get(&key_ab)
                .unwrap_or(&vec![])
                .iter()
                .filter_map(|p| {
                    Decimal::from_str(&p.executable_price).ok().map(|pr| (p, pr))
                })
                .min_by(|a, b| a.1.cmp(&b.1));

            // Best sell: for reverse direction, highest price
            let key_ba = (token_b.clone(), token_a.clone());
            let best_sell = pair_pools.get(&key_ba)
                .unwrap_or(&vec![])
                .iter()
                .filter_map(|p| {
                    Decimal::from_str(&p.executable_price).ok().map(|pr| (p, pr))
                })
                .max_by(|a, b| a.1.cmp(&b.1));

            if let (Some((buy_p, buy_price)), Some((sell_p, sell_price))) = (best_buy, best_sell) {
                if buy_p.address == sell_p.address {
                    continue;
                }

                let cand = Candidate {
                    buy_pool_address: buy_p.address.clone(),
                    sell_pool_address: sell_p.address.clone(),
                    token_in: token_a.clone(),
                    token_mid: token_b.clone(),
                    buy_pool_tvl_usd: buy_p.tvl_usd.clone(),
                    executable_buy_price: buy_price.to_string(),
                    executable_sell_price: sell_price.to_string(),
                    buy_pool_protocol: buy_p.protocol.clone(),
                    sell_pool_protocol: sell_p.protocol.clone(),
                };

                if cand.validate(config).is_ok() {
                    candidates.push(cand);
                }
            }
        }
    }

    Ok(candidates)
}

/// Module definition for PyO3.
#[pymodule]
fn scanner_core(_py: Python, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<Candidate>()?;
    m.add_class::<GateConfig>()?;
    m.add_function(wrap_pyfunction!(find_best_quote, m)?)?;
    m.add_function(wrap_pyfunction!(scan_opportunities, m)?)?;
    Ok(())
}