//! Uniswap V2 CPMM Adapter

use crate::{Quote, QuoteAdapter};
use alloy_primitives::{Address, U256};
use apex_types::{AdapterError, RawPool};
use async_trait::async_trait;
use serde::Deserialize;

/// An adapter for Uniswap V2-style Constant Product Market Maker pools.
pub struct V2Adapter;

#[derive(Deserialize)]
struct V2State {
    reserve0: u128,
    reserve1: u128,
}

#[async_trait]
impl QuoteAdapter for V2Adapter {
    async fn quote(
        &self,
        pool: &RawPool,
        token_in: &Address,
        amount_in: U256,
    ) -> Result<Quote, AdapterError> {
        let state: V2State = serde_json::from_value(pool.state.clone())?;
        let (reserve_in, reserve_out) = if *token_in == pool.tokens[0] {
            (state.reserve0, state.reserve1)
        } else {
            (state.reserve1, state.reserve0)
        };

        if reserve_in == 0 || reserve_out == 0 {
            return Err(AdapterError::InsufficientLiquidity);
        }

        // Standard V2 formula: amountOut = (reserveOut * amountIn * 997) / (reserveIn * 1000 + amountIn * 997)
        let amount_in_with_fee = amount_in * U256::from(997);
        let numerator = U256::from(reserve_out) * amount_in_with_fee;
        let denominator = U256::from(reserve_in) * U256::from(1000) + amount_in_with_fee;

        if denominator.is_zero() {
            return Err(AdapterError::CalculationError("Division by zero".to_string()));
        }

        let amount_out = numerator / denominator;

        Ok(Quote { amount_out, new_sqrt_price: None, new_reserves: Some((reserve_in + amount_in.to::<u128>(), reserve_out - amount_out.to::<u128>())) })
    }
}