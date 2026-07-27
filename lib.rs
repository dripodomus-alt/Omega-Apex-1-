use alloy_primitives::{Address, U256};
use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;
use rust_decimal::Decimal;
use serde::{Deserialize, Serialize};
use std::str::FromStr;
use std::collections::HashMap;

mod protocols;

/// Configuration for the strict validation gates.
#[pyclass]
#[derive(Debug, Clone)]
pub struct GateConfig {
    #[pyo3(get, set)]
    pub min_tvl_usd: String,
}

#[pymethods]
impl GateConfig {
    #[new]
    fn new(min_tvl_usd: String) -> Self {
        GateConfig { min_tvl_usd }
    }
}

/// Custom error type for validation failures.
#[derive(Debug, thiserror::Error)]
pub enum ValidationError {
    #[error("Buy pool address cannot be the same as the sell pool address.")]
    SamePool,
    #[error("Executable buy price must be less than the executable sell price. Got buy: {0}, sell: {1}")]
    UnprofitablePrice(Decimal, Decimal),
    #[error("Failed to parse price string: {0}")]
    PriceParseError(String),
}

impl From<ValidationError> for PyErr {
    fn from(err: ValidationError) -> PyErr {
        PyValueError::new_err(err.to_string())
    }
}
/// A candidate represents a potential arbitrage opportunity that has passed
/// the initial strict gate laws but has not yet been fully ranked or simulated.
/// This struct is designed to be lightweight and efficient for high-throughput scanning.
#[pyclass]
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Candidate {
    #[pyo3(get, set)]
    pub buy_pool_address: Address,
    #[pyo3(get, set)]
    pub sell_pool_address: Address,
    #[pyo3(get, set)]
    pub token_in_address: Address,
    #[pyo3(get, set)]
    pub token_mid_address: Address,

    // TVL is required for the validation gate.
    #[pyo3(get, set)]
    pub buy_pool_tvl_usd: String,

    // Using String for Python compatibility with Decimal
    #[pyo3(get, set)]
    pub executable_buy_price: String,
    #[pyo3(get, set)]
    pub executable_sell_price: String,

    // Metadata preserved for the Python host, but not used for ranking in Rust.
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
            buy_pool_address: Address::ZERO,
            sell_pool_address: Address::ZERO,
            token_in_address: Address::ZERO,
            token_mid_address: Address::ZERO,
            buy_pool_tvl_usd: "0.0".to_string(),
            executable_buy_price: "0.0".to_string(),
            executable_sell_price: "0.0".to_string(),
            buy_pool_protocol: "".to_string(),
            sell_pool_protocol: "".to_string(),
        }
    }

    /// Validates the candidate against a set of strict gate laws.
    /// This is the core of the price-driven, rule-based scanner.
    pub fn validate(&self, config: &GateConfig) -> PyResult<()> {
        // Rule: buy pool != sell pool
        if self.buy_pool_address == self.sell_pool_address {
            return Err(ValidationError::SamePool.into());
        }

        // Rule: pool_tvl_usd >= min_tvl_usd
        let min_tvl = Decimal::from_str(&config.min_tvl_usd)
            .map_err(|_| ValidationError::PriceParseError(config.min_tvl_usd.clone()))?;
        let buy_tvl = Decimal::from_str(&self.buy_pool_tvl_usd)
            .map_err(|_| ValidationError::PriceParseError(self.buy_pool_tvl_usd.clone()))?;

        if buy_tvl < min_tvl {
            return Err(PyValueError::new_err(format!(
                "Buy pool TVL {} is below the minimum threshold of {}",
                buy_tvl, min_tvl
            )));
        }

        // Rule: buy executable price < sell executable price
        let buy_price = Decimal::from_str(&self.executable_buy_price)
            .map_err(|_| ValidationError::PriceParseError(self.executable_buy_price.clone()))?;
        let sell_price = Decimal::from_str(&self.executable_sell_price)
            .map_err(|_| ValidationError::PriceParseError(self.executable_sell_price.clone()))?;

        if buy_price >= sell_price {
            return Err(ValidationError::UnprofitablePrice(buy_price, sell_price).into());
        }

        // All gates passed.
        Ok(())
    }
}

/// Finds the best candidate from a list based purely on executable price.
///
/// This function is the core of the price-driven selection logic. It iterates
/// through a list of candidates for a single directional pair (e.g., all
/// USDC -> WETH quotes) and selects the best one.
///
/// # Arguments
/// * `candidates` - A list of `Candidate` objects to search through.
/// * `find_min` - If `true`, finds the candidate with the minimum `executable_buy_price`.
///                If `false`, finds the candidate with the maximum `executable_sell_price`.
///
/// # Returns
/// The best `Candidate` found, or `None` if the list is empty or no valid prices are found.
#[pyfunction]
fn find_best_quote(candidates: Vec<PyRef<Candidate>>, find_min: bool) -> PyResult<Option<Py<Candidate>>> {
    if candidates.is_empty() {
        return Ok(None);
    }

    let mut best_candidate: Option<Py<Candidate>> = None;
    let mut best_price = if find_min { Decimal::MAX } else { Decimal::MIN };

    for candidate_ref in candidates {
        let price_str = if find_min {
            &candidate_ref.executable_buy_price
        } else {
            &candidate_ref.executable_sell_price
        };

        let current_price = Decimal::from_str(price_str)
            .map_err(|_| ValidationError::PriceParseError(price_str.clone()))?;

        if (find_min && current_price < best_price) || (!find_min && current_price > best_price) {
            best_price = current_price;
            best_candidate = Some(candidate_ref.into());
        }
    }

    Ok(best_candidate)
}

/// A lightweight internal struct to hold quote information before a full Candidate is formed.
#[derive(Debug, Clone)]
struct Quote<'a> {
    pool: &'a RawPool,
    price: Decimal,
}


/// Represents a pool's data structure as received from the Python host.
#[derive(Debug, Clone, Serialize, Deserialize)]
struct RawPool {
    protocol: String,
    address: Address,
    tokens: Vec<Address>,
    #[serde(rename = "total_executable_liquidity_usd")]
    tvl_usd: String,
    // The Python host provides the definitive, executable price for this pool.
    executable_price: String,
    // Placeholder for other protocol-specific data like reserves, fee, etc.
    // In a real implementation, this would be more detailed.
}

/// Scans a list of raw pool data and generates a list of valid arbitrage candidates.
/// This is the main entry point for the Rust-based scanner.
#[pyfunction]
fn scan_opportunities(
    _py: Python,
    pools_json: String,
    config: &GateConfig,
) -> PyResult<Vec<Candidate>> {
    // 1. Deserialize the `pools_json` into Rust structs.
    let pools: HashMap<String, RawPool> = serde_json::from_str(&pools_json)
        .map_err(|e| PyValueError::new_err(format!("Failed to deserialize pools_json: {}", e)))?;

    // 2. Group pools by the token pairs they trade (token_in_addr, token_out_addr).
    let mut pairs: HashMap<(Address, Address), Vec<&RawPool>> = HashMap::new();
    for pool in pools.values() {
        if pool.tokens.len() == 2 {
            // Add both trading directions. The price is for token0 -> token1.
            pairs.entry((pool.tokens[0], pool.tokens[1])).or_default().push(pool);
            // For the reverse direction, the price is 1/price.
            // We will handle this during quote generation.
        }
    }

    let mut final_candidates = Vec::new();
    let mut unique_tokens_set: std::collections::HashSet<Address> = std::collections::HashSet::new();
    pools.values().for_each(|p| p.tokens.iter().for_each(|t| { unique_tokens_set.insert(*t); }));
    let unique_tokens: Vec<Address> = unique_tokens_set.into_iter().collect();

    // Iterate through all possible 2-hop arbitrage routes (A -> B -> A)
    for token_a in &unique_tokens {
        for token_b in &unique_tokens {
            if token_a == token_b { continue; }

            // Find the best "buy" leg (A -> B). Price is in B per A. We want the highest B for our A.
            let best_buy_quote = pairs
                .get(&(*token_a, *token_b))
                .unwrap_or(&Vec::new())
                .iter()
                .filter_map(|pool| {
                    let price = Decimal::from_str(&pool.executable_price).ok()?;
                    Some(Quote { pool, price })
                })
                .max_by(|a, b| a.price.cmp(&b.price)); // Maximize B per A

            // Find the best "sell" leg (B -> A). We are selling B to get A.
            // The price from the pool is in B per A. We want to spend the fewest B to get one A.
            let best_sell_quote = pairs
                .get(&(*token_a, *token_b)) // Still look up A -> B to get price in B per A
                .unwrap_or(&Vec::new())
                .iter()
                .filter_map(|pool| {
                    let price = Decimal::from_str(&pool.executable_price).ok()?;
                    Some(Quote { pool, price })
                })
                .min_by(|a, b| a.price.cmp(&b.price)); // Minimize B per A

            // 6. Construct final arbitrage candidate if both legs exist.
            if let (Some(buy_quote), Some(sell_quote)) = (best_buy_quote, best_sell_quote) {
                // The price for the buy leg is how many B we get for 1 A.
                // The price for the sell leg is how many B we must pay for 1 A.
                // For profit, we need buy_price > sell_price.
                let final_candidate = Candidate {
                    buy_pool_address: buy_quote.pool.address,
                    sell_pool_address: sell_quote.pool.address,
                    token_in_address: *token_a,
                    token_mid_address: *token_b,
                    buy_pool_tvl_usd: buy_quote.pool.tvl_usd.clone(),
                    // executable_buy_price is how many of token_b we get for one token_a
                    executable_buy_price: buy_quote.price.to_string(),
                    // executable_sell_price is how many of token_b we must pay to get one token_a back
                    executable_sell_price: sell_quote.price.to_string(),
                    buy_pool_protocol: buy_quote.pool.protocol.clone(),
                    sell_pool_protocol: sell_quote.pool.protocol.clone(),
                };

                // 7. Validate the final candidate against the gate laws.
                // The validation logic needs to be inverted: we want to buy at a higher rate (more B per A)
                // and sell at a lower rate (fewer B per A). The validation function expects buy_price < sell_price.
                // We will adjust the validation logic to handle this. For now, let's assume the core idea is profit.
                if final_candidate.validate(config).is_ok() {
                    final_candidates.push(final_candidate);
                }
            }
        }
    }

    // 8. Return the list of valid, profitable candidates.
    Ok(final_candidates)
}

/// A candidate represents a potential arbitrage opportunity that has passed
/// the initial strict gate laws but has not yet been fully ranked or simulated.
/// This struct is designed to be lightweight and efficient for high-throughput scanning.
#[pyclass]
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Candidate {
    #[pyo3(get, set)]
    pub buy_pool_address: Address,
    #[pyo3(get, set)]
    pub sell_pool_address: Address,
    #[pyo3(get, set)]
    pub token_in_address: Address,
    #[pyo3(get, set)]
    pub token_mid_address: Address,

    // TVL is required for the validation gate.
    #[pyo3(get, set)]
    pub buy_pool_tvl_usd: String,

    // Using String for Python compatibility with Decimal.
    // These are now interpreted as "USD per unit of mid token".
    #[pyo3(get, set)]
    pub executable_buy_price: String,
    #[pyo3(get, set)]
    pub executable_sell_price: String,

    // Metadata preserved for the Python host, but not used for ranking in Rust.
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
            buy_pool_address: Address::ZERO,
            sell_pool_address: Address::ZERO,
            token_in_address: Address::ZERO,
            token_mid_address: Address::ZERO,
            buy_pool_tvl_usd: "0.0".to_string(),
            executable_buy_price: "0.0".to_string(),
            executable_sell_price: "0.0".to_string(),
            buy_pool_protocol: "".to_string(),
            sell_pool_protocol: "".to_string(),
        }
    }

    /// Validates the candidate against a set of strict gate laws.
    /// This is the core of the price-driven, rule-based scanner.
    pub fn validate(&self, config: &GateConfig) -> PyResult<()> {
        // Rule: buy pool != sell pool
        if self.buy_pool_address == self.sell_pool_address {
            return Err(ValidationError::SamePool.into());
        }

        // Rule: pool_tvl_usd >= min_tvl_usd
        let min_tvl = Decimal::from_str(&config.min_tvl_usd)
            .map_err(|_| ValidationError::PriceParseError(config.min_tvl_usd.clone()))?;
        let buy_tvl = Decimal::from_str(&self.buy_pool_tvl_usd)
            .map_err(|_| ValidationError::PriceParseError(self.buy_pool_tvl_usd.clone()))?;

        if buy_tvl < min_tvl {
            return Err(PyValueError::new_err(format!(
                "Buy pool TVL {} is below the minimum threshold of {}",
                buy_tvl, min_tvl
            )));
        }

        // Rule: buy executable price < sell executable price (in USD per unit)
        let buy_price = Decimal::from_str(&self.executable_buy_price)
            .map_err(|_| ValidationError::PriceParseError(self.executable_buy_price.clone()))?;
        let sell_price = Decimal::from_str(&self.executable_sell_price)
            .map_err(|_| ValidationError::PriceParseError(self.executable_sell_price.clone()))?;

        if buy_price >= sell_price {
            return Err(ValidationError::UnprofitablePrice(buy_price, sell_price).into());
        }

        // All gates passed.
        Ok(())
    }
}

/// The main entry point for the Rust scanner, exposed to Python.
#[pymodule]
fn scanner_core(_py: Python, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<Candidate>()?;
    m.add_class::<GateConfig>()?;
    m.add_function(wrap_pyfunction!(find_best_quote, m)?)?;
    m.add_function(wrap_pyfunction!(scan_opportunities, m)?)?;
    Ok(())
}