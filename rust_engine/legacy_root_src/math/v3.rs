//! Uniswap V3 & Algebra CLMM Adapter

use crate::{Quote, QuoteAdapter};
use alloy_primitives::{Address, U256};
use apex_types::{AdapterError, RawPool};
use async_trait::async_trait;
use serde::Deserialize;

/// Represents the necessary on-chain state for a V3-style pool.
#[derive(Deserialize, Debug)]
struct V3State {
    liquidity: u128,
    sqrt_price_x96: U256,
    // For simplicity, we assume swaps do not cross ticks in this implementation.
    // A full implementation would require tick_spacing and a tick data provider.
    // tick: i32,
}

/// An adapter for Uniswap V3-style Concentrated Liquidity Market Maker pools.
pub struct V3Adapter;

#[async_trait]
impl QuoteAdapter for V3Adapter {
    async fn quote(
        &self,
        pool: &RawPool,
        token_in: &Address,
        amount_in: U256,
    ) -> Result<Quote, AdapterError> {
        let state: V3State = serde_json::from_value(pool.state.clone())?;

        if state.liquidity == 0 {
            return Err(AdapterError::InsufficientLiquidity);
        }

        let zero_for_one = *token_in == pool.tokens[0];

        // This is a pure Rust port of the Uniswap V3 `SwapMath.computeSwapStep` logic.
        // It calculates the result of a swap within a single tick range.
        let (amount_out, new_sqrt_price) = compute_swap_step(
            state.sqrt_price_x96,
            // For now, we assume we don't cross a tick. A full implementation
            // would get the next tick's sqrt_price from a tick data provider.
            if zero_for_one {
                U256::from(4295128739u64) // A realistic minimum sqrt_price_x96
            } else {
                U256::from("1461446703485210103287273052203988822378723970342") // A realistic maximum
            },
            state.liquidity,
            amount_in,
            zero_for_one,
        )?;

        Ok(Quote {
            amount_out,
            new_sqrt_price: Some(new_sqrt_price),
            new_reserves: None,
        })
    }
}

/// Pure Rust implementation of `SwapMath.computeSwapStep` from Uniswap V3 Core.
/// All math is done with U256 to prevent precision loss.
fn compute_swap_step(
    sqrt_ratio_current_x96: U256,
    sqrt_ratio_target_x96: U256,
    liquidity: u128,
    amount_remaining: U256,
    zero_for_one: bool,
) -> Result<(U256, U256), AdapterError> {
    let exact_in = true; // We are always calculating amount_out given amount_in

    if zero_for_one && exact_in {
        let amount_in = get_amount0_delta(sqrt_ratio_target_x96, sqrt_ratio_current_x96, liquidity);
        if amount_in >= amount_remaining {
            // We have enough liquidity in this range to fulfill the swap
            let new_sqrt_price = get_next_sqrt_price_from_input(sqrt_ratio_current_x96, liquidity, amount_remaining, true);
            let amount_out = get_amount1_delta(new_sqrt_price, sqrt_ratio_current_x96, liquidity);
            Ok((amount_out, new_sqrt_price))
        } else {
            // We are using all liquidity in this range
            let amount_out = get_amount1_delta(sqrt_ratio_target_x96, sqrt_ratio_current_x96, liquidity);
            Ok((amount_out, sqrt_ratio_target_x96))
        }
    } else if !zero_for_one && exact_in {
        let amount_in = get_amount1_delta(sqrt_ratio_target_x96, sqrt_ratio_current_x96, liquidity);
        if amount_in >= amount_remaining {
            // We have enough liquidity in this range to fulfill the swap
            let new_sqrt_price = get_next_sqrt_price_from_input(sqrt_ratio_current_x96, liquidity, amount_remaining, false);
            let amount_out = get_amount0_delta(new_sqrt_price, sqrt_ratio_current_x96, liquidity);
            Ok((amount_out, new_sqrt_price))
        } else {
            // We are using all liquidity in this range
            let amount_out = get_amount0_delta(sqrt_ratio_target_x96, sqrt_ratio_current_x96, liquidity);
            Ok((amount_out, sqrt_ratio_target_x96))
        }
    } else {
        Err(AdapterError::CalculationError("Unsupported swap direction".to_string()))
    }
}

// Helper functions ported from Uniswap V3 math libraries
fn get_amount0_delta(sqrt_ratio_a_x96: U256, sqrt_ratio_b_x96: U256, liquidity: u128) -> U256 {
    let (sqrt_ratio_a_x96, sqrt_ratio_b_x96) = if sqrt_ratio_a_x96 > sqrt_ratio_b_x96 { (sqrt_ratio_b_x96, sqrt_ratio_a_x96) } else { (sqrt_ratio_a_x96, sqrt_ratio_b_x96) };
    (U256::from(liquidity) << 96) * (sqrt_ratio_b_x96 - sqrt_ratio_a_x96) / sqrt_ratio_b_x96 / sqrt_ratio_a_x96
}

fn get_amount1_delta(sqrt_ratio_a_x96: U256, sqrt_ratio_b_x96: U256, liquidity: u128) -> U256 {
    let (sqrt_ratio_a_x96, sqrt_ratio_b_x96) = if sqrt_ratio_a_x96 > sqrt_ratio_b_x96 { (sqrt_ratio_b_x96, sqrt_ratio_a_x96) } else { (sqrt_ratio_a_x96, sqrt_ratio_b_x96) };
    U256::from(liquidity) * (sqrt_ratio_b_x96 - sqrt_ratio_a_x96) >> 96
}

fn get_next_sqrt_price_from_input(sqrt_p_x96: U256, liquidity: u128, amount_in: U256, zero_for_one: bool) -> U256 {
    if zero_for_one {
        (U256::from(liquidity) << 96) / ((U256::from(liquidity) << 96) / sqrt_p_x96 + amount_in)
    } else {
        sqrt_p_x96 + (amount_in << 96) / U256::from(liquidity)
    }
}