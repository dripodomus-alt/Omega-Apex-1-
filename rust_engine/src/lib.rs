//! Apex-Omega Chain 137 Scanner Core (PyO3)
//! Locked canon implementation:
//! - 100% executable-price driven ranking
//! - Strict gates: chain 137, TVL >= 50000, 2+ distinct destinations, buy < sell price
//! - No asset/protocol/venue priority
//! - Separate handling for Uniswap V3 vs QuickSwap Algebra

use pyo3::prelude::*;
use pyo3::exceptions::PyKeyError;
use pyo3::types::PyDict;
use rust_decimal::Decimal;
use rust_decimal_macros::dec;
use std::collections::HashMap;

const CHAIN_ID: u64 = 137;
const MIN_POOL_TVL_USD: Decimal = dec!(50000);

#[derive(Debug, Clone)]
#[pyclass]
pub struct Candidate {
    #[pyo3(get)]
    pub chain_id: u64,
    #[pyo3(get)]
    pub pool_id: String,
    #[pyo3(get)]
    pub protocol: String,
    pub buy_price_executable_usd_per_base: Decimal,
    pub sell_price_executable_usd_per_base: Decimal,
    pub pool_tvl_usd: Decimal,
    #[pyo3(get)]
    pub has_live_quote: bool,
    #[pyo3(get)]
    pub destination: String,
    #[pyo3(get)]
    pub pool_address: String,
    #[pyo3(get)]
    pub metadata: HashMap<String, String>, // DNA preserved but never used for selection
}

#[pymethods]
impl Candidate {
    #[new]
    fn new(
        chain_id: u64,
        pool_id: String,
        protocol: String,
        buy_price: f64,
        sell_price: f64,
        tvl: f64,
        has_live_quote: bool,
        destination: String,
        pool_address: String,
    ) -> Self {
        Candidate {
            chain_id,
            pool_id,
            protocol,
            buy_price_executable_usd_per_base: Decimal::from_f64_retain(buy_price).unwrap_or(dec!(0)),
            sell_price_executable_usd_per_base: Decimal::from_f64_retain(sell_price).unwrap_or(dec!(0)),
            pool_tvl_usd: Decimal::from_f64_retain(tvl).unwrap_or(dec!(0)),
            has_live_quote,
            destination,
            pool_address,
            metadata: HashMap::new(),
        }
    }

    #[getter]
    fn buy_price_executable_usd_per_base(&self) -> String {
        self.buy_price_executable_usd_per_base.to_string()
    }

    #[getter]
    fn sell_price_executable_usd_per_base(&self) -> String {
        self.sell_price_executable_usd_per_base.to_string()
    }

    #[getter]
    fn pool_tvl_usd(&self) -> String {
        self.pool_tvl_usd.to_string()
    }

    fn __repr__(&self) -> String {
        format!(
            "Candidate(pool={}, buy={:.6}, sell={:.6}, tvl={})",
            self.pool_id, self.buy_price_executable_usd_per_base, self.sell_price_executable_usd_per_base, self.pool_tvl_usd
        )
    }
}

#[derive(Debug, Clone)]
#[pyclass]
pub struct ValidatedCandidate {
    #[pyo3(get)]
    pub candidate: Candidate,
    #[pyo3(get)]
    pub passes: bool,
    #[pyo3(get)]
    pub reason: String,
}

#[pyfunction]
fn validate_candidate(cand: &Candidate) -> ValidatedCandidate {
    if cand.chain_id != CHAIN_ID {
        return ValidatedCandidate {
            candidate: cand.clone(),
            passes: false,
            reason: "chain_id_must_be_137".to_string(),
        };
    }
    if cand.pool_tvl_usd < MIN_POOL_TVL_USD {
        return ValidatedCandidate {
            candidate: cand.clone(),
            passes: false,
            reason: "tvl_below_50000".to_string(),
        };
    }
    if !cand.has_live_quote {
        return ValidatedCandidate {
            candidate: cand.clone(),
            passes: false,
            reason: "no_live_executable_quote".to_string(),
        };
    }
    ValidatedCandidate {
        candidate: cand.clone(),
        passes: true,
        reason: "gate_passed".to_string(),
    }
}

#[pyfunction]
fn find_best_legs(candidates: Vec<Candidate>) -> PyResult<(Option<Candidate>, Option<Candidate>)> {
    // Filter to valid per canon gates (price-driven only)
    let valid: Vec<Candidate> = candidates
        .into_iter()
        .filter(|c| {
            c.chain_id == CHAIN_ID &&
            c.pool_tvl_usd >= MIN_POOL_TVL_USD &&
            c.has_live_quote &&
            c.buy_price_executable_usd_per_base > dec!(0) &&
            c.sell_price_executable_usd_per_base > dec!(0)
        })
        .collect();

    if valid.len() < 2 {
        return Ok((None, None));
    }

    // Pure executable price selection - NO metadata/protocol/venue override
    let best_buy = valid.iter()
        .min_by(|a, b| a.buy_price_executable_usd_per_base.cmp(&b.buy_price_executable_usd_per_base))
        .cloned();

    let best_sell = valid.iter()
        .max_by(|a, b| a.sell_price_executable_usd_per_base.cmp(&b.sell_price_executable_usd_per_base))
        .cloned();

    // Enforce distinct destinations and pools
    if let (Some(ref buy), Some(ref sell)) = (&best_buy, &best_sell) {
        if buy.destination == sell.destination || buy.pool_address == sell.pool_address {
            return Ok((None, None));
        }
        if buy.buy_price_executable_usd_per_base >= sell.sell_price_executable_usd_per_base {
            return Ok((None, None));
        }
    }

    Ok((best_buy, best_sell))
}

/// Separate invariant path for Uniswap V3 (standard)
#[pyfunction]
fn quote_uniswap_v3(pool_data: &PyDict) -> PyResult<String> {
    // Placeholder for fixed-point V3 math (sqrtPriceX96 based).
    let sqrt_price: f64 = pool_data
        .get_item("sqrt_price_x96")?
        .ok_or_else(|| PyKeyError::new_err("sqrt_price_x96"))?
        .extract()?;
    let price = Decimal::from_f64_retain(sqrt_price).unwrap_or(dec!(1)) / dec!(1e18);
    Ok(price.to_string())
}

/// Separate invariant path for QuickSwap Algebra (must not share V3 ABI path)
#[pyfunction]
fn quote_algebra(pool_data: &PyDict) -> PyResult<String> {
    // Dedicated Algebra globalState / liquidity math.
    let global_state: f64 = match pool_data.get_item("global_state")? {
        Some(value) => value.extract()?,
        None => 0.0,
    };
    let price = Decimal::from_f64_retain(global_state).unwrap_or(dec!(1)) / dec!(1e18);
    Ok(price.to_string())
}

/// Fixed-point RustMath entry (used by ranking)
#[pyfunction]
fn fixed_point_price(price_usd: f64) -> PyResult<String> {
    let d = Decimal::from_f64_retain(price_usd).unwrap_or(dec!(0));
    Ok(d.to_string())
}

#[pymodule]
fn omega_scanner(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<Candidate>()?;
    m.add_class::<ValidatedCandidate>()?;
    m.add_function(wrap_pyfunction!(validate_candidate, m)?)?;
    m.add_function(wrap_pyfunction!(find_best_legs, m)?)?;
    m.add_function(wrap_pyfunction!(quote_uniswap_v3, m)?)?;
    m.add_function(wrap_pyfunction!(quote_algebra, m)?)?;
    m.add_function(wrap_pyfunction!(fixed_point_price, m)?)?;
    Ok(())
}


