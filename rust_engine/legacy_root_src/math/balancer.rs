//! Balancer Weighted Pool Adapter

use crate::{Quote, QuoteAdapter};
use alloy_primitives::{Address, U256};
use apex_types::{AdapterError, RawPool};
use async_trait::async_trait;
use std::cmp::min;
use serde::Deserialize;

/// Represents the necessary on-chain state for a Balancer weighted pool.
#[derive(Deserialize, Debug)]
struct BalancerState {
    balances: Vec<U256>,
    weights: Vec<U256>, // Weights are typically stored as 1e18 scaled integers
}

/// An adapter for Balancer weighted pools.
pub struct BalancerAdapter;

#[async_trait]
impl QuoteAdapter for BalancerAdapter {
    async fn quote(
        &self,
        pool: &RawPool,
        token_in: &Address,
        amount_in: U256,
    ) -> Result<Quote, AdapterError> {
        let state: BalancerState = serde_json::from_value(pool.state.clone())?;

        let token_in_index = pool.tokens.iter().position(|&t| t == *token_in)
            .ok_or_else(|| AdapterError::CalculationError("TokenIn not found in pool".to_string()))?;

        // For simplicity, this implementation assumes a 2-token pool.
        // A full implementation would handle multi-token swaps.
        if pool.tokens.len() != 2 {
            return Err(AdapterError::Unsupported("Only 2-token Balancer pools are supported for now".to_string()));
        }

        let token_out_index = if token_in_index == 0 { 1 } else { 0 };

        let balance_in = state.balances[token_in_index];
        let balance_out = state.balances[token_out_index];
        let weight_in = state.weights[token_in_index];
        let weight_out = state.weights[token_out_index];

        // This is a Rust port of the Balancer weighted pool formula:
        // amountOut = balanceOut * (1 - (balanceIn / (balanceIn + amountIn))^(weightIn / weightOut))
        // All math is done with U256 to maintain precision.
        let one = U256::from(10).pow(U256::from(18));

        // Calculate base for exponentiation: balanceIn / (balanceIn + amountIn)
        let ratio = (balance_in * one) / (balance_in + amount_in);

        // Calculate exponent: weightIn / weightOut
        let exponent = (weight_in * one) / weight_out;

        // Calculate ratio^exponent using a high-precision fixed-point power function.
        let ratio_pow_exponent = fixed_point_pow(ratio, exponent, one)?;

        let factor = one - ratio_pow_exponent;
        let amount_out = (balance_out * factor) / one;

        Ok(Quote { amount_out, new_sqrt_price: None, new_reserves: None })
    }
}

// --- High-Precision Fixed-Point Math using U256 ---
// This section implements the necessary functions to calculate `x^y` where
// x and y are fixed-point numbers, without using floating-point arithmetic.

/// Calculates x^y for fixed-point numbers, using the identity x^y = exp(y * ln(x)).
fn fixed_point_pow(base: U256, exp: U256, one: U256) -> Result<U256, AdapterError> {
    if base.is_zero() {
        return Ok(U256::ZERO);
    }
    // ln(base) is also a fixed-point number
    let log_base = fixed_point_ln(base, one)?;
    // (y * ln(x)) is a fixed-point number
    let product = (exp * log_base) / one;
    // exp(product) is the final result
    fixed_point_exp(product, one)
}

/// Calculates ln(x) for a fixed-point number x.
/// Uses a Taylor series expansion for ln(1+z) where z = (x-1).
fn fixed_point_ln(x: U256, one: U256) -> Result<U256, AdapterError> {
    if x.is_zero() {
        return Err(AdapterError::CalculationError(
            "ln(0) is undefined".to_string(),
        ));
    }

    // The Taylor series for ln(1+z) converges for |z| < 1.
    // We need to handle x > one and x < one differently.
    let (z, is_less_than_one) = if x > one {
        (x - one, false)
    } else {
        (one - x, true)
    };

    let mut sum = U256::ZERO;
    for i in 1..=50 {
        let current_term = (term * one) / U256::from(i);
        if i % 2 == 1 {
            sum += current_term;
        } else {
            sum -= current_term;
        }
        term = (term * z) / one;
    }

    if is_less_than_one {
        // We calculated ln(1-z) = - (z + z^2/2 + ...). The series gives a positive sum.
        // We need to return a negative value. Since U256 is unsigned, we'll use
        // twos-complement representation for the negative number.
        Ok(U256::MAX - sum + U256::from(1))
    } else {
        Ok(sum)
    }
}

/// Calculates exp(x) for a fixed-point number x.
/// Uses a Taylor series expansion: exp(x) = 1 + x + x^2/2! + x^3/3! + ...
fn fixed_point_exp(x: U256, one: U256) -> Result<U256, AdapterError> {
    let mut sum = one;
    let mut term = one;
    let mut i = 1;

    // We compute up to 30 terms for good precision.
    // The series converges quickly.
    while i <= 30 {
        term = (term * x) / one / U256::from(i);
        if term.is_zero() {
            break;
        }
        sum += term;
        i += 1;
    }

    Ok(sum)
}