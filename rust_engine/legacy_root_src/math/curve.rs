//! Curve Stableswap Adapter

use crate::{Quote, QuoteAdapter};
use alloy_primitives::{Address, U256};
use apex_types::{AdapterError, RawPool};
use async_trait::async_trait;
use serde::Deserialize;

/// Represents the necessary on-chain state for a Curve pool.
#[derive(Deserialize, Debug)]
struct CurveState {
    balances: Vec<U256>,
    a: U256, // Amplification parameter
}

/// An adapter for Curve stableswap pools.
pub struct CurveAdapter;

#[async_trait]
impl QuoteAdapter for CurveAdapter {
    async fn quote(
        &self,
        pool: &RawPool,
        token_in: &Address,
        amount_in: U256,
    ) -> Result<Quote, AdapterError> {
        let state: CurveState = serde_json::from_value(pool.state.clone())?;
        let n_coins = pool.tokens.len();

        let i = pool.tokens.iter().position(|&t| t == *token_in)
            .ok_or_else(|| AdapterError::CalculationError("TokenIn not found in pool".to_string()))?;

        // For simplicity, this assumes a 2-coin pool and a swap to the other coin.
        if n_coins != 2 {
            return Err(AdapterError::Unsupported("Only 2-coin Curve pools are supported for now".to_string()));
        }
        let j = if i == 0 { 1 } else { 0 };

        let mut new_balances = state.balances.clone();
        new_balances[i] = new_balances[i] + amount_in;

        let d = get_d(&state.balances, state.a, n_coins)?;
        let y = get_y(i, j, new_balances[i], &state.balances, state.a, d, n_coins)?;

        let amount_out = state.balances[j] - y;

        Ok(Quote { amount_out, new_sqrt_price: None, new_reserves: None })
    }
}

// --- Curve Math Ported from Solidity ---

fn get_d(balances: &[U256], a: U256, n_coins: usize) -> Result<U256, AdapterError> {
    let mut s = U256::ZERO;
    for &x in balances {
        s += x;
    }
    if s == U256::ZERO {
        return Ok(U256::ZERO);
    }

    let mut d_prev;
    let mut d = s;
    let n_coins_u256 = U256::from(n_coins);
    let ann = a * n_coins_u256;

    for _ in 0..255 {
        let mut d_p = d;
        for &x in balances {
            d_p = d_p * d / (x * n_coins_u256);
        }
        d_prev = d;
        d = (ann * s + d_p * n_coins_u256) * d / ((ann - U256::from(1)) * d + (n_coins_u256 + U256::from(1)) * d_p);
        if d.abs_diff(d_prev) <= U256::from(1) {
            return Ok(d);
        }
    }
    Err(AdapterError::CalculationError("D did not converge".to_string()))
}

fn get_y(i: usize, j: usize, x: U256, balances: &[U256], a: U256, d: U256, n_coins: usize) -> Result<U256, AdapterError> {
    let n_coins_u256 = U256::from(n_coins);
    let ann = a * n_coins_u256;
    let mut c = d;
    let mut s = U256::ZERO;

    for k in 0..n_coins {
        if k == i { s += x; }
        else if k != j { s += balances[k]; }
    }
    c = c * c / (x * n_coins_u256);
    c = c * d / (ann * n_coins_u256);
    let b = s + d / ann;
    let mut y_prev;
    let mut y = d;

    for _ in 0..255 {
        y_prev = y;
        y = (y * y + c) / (y * U256::from(2) + b - d);
        if y.abs_diff(y_prev) <= U256::from(1) {
            return Ok(y);
        }
    }
    Err(AdapterError::CalculationError("y did not converge".to_string()))
}