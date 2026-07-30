//! # Dynamic Trade Sizing Engine
//!
//! This module finds the optimal trade size for a given arbitrage route by
//! iterating through a range of potential principal amounts and selecting the
//! one that yields the highest net profit after accounting for slippage.

use crate::slippage::calculate_slippage_amount;
use apex_routing::Route;
use alloy_primitives::U256;

/// The number of steps to check when searching for the optimal size.
const SIZING_STEPS: u64 = 20;

/// Finds the optimal principal amount for a given route.
///
/// It starts with a small amount and iteratively checks larger sizes up to the
/// total liquidity of the route's shallowest pool.
pub fn find_optimal_size(route: &mut Route) -> U256 {
    let mut best_profit = U256::ZERO;
    let mut optimal_size = U256::ZERO;

    // Find the shallowest pool to set a realistic maximum trade size.
    let max_liquidity_usd = route.pools.iter()
        .map(|p| p.total_executable_liquidity_usd.parse::<u64>().unwrap_or(0))
        .min()
        .unwrap_or(1_000_000); // Default to 1M if parsing fails.

    let step_size = max_liquidity_usd / SIZING_STEPS;

    for i in 1..=SIZING_STEPS {
        let current_size_usd = U256::from(step_size * i);
        
        // This is a simplified model. A full implementation would convert USD to the
        // principal token's amount based on its current price. For now, we assume 1:1.
        let principal_amount = current_size_usd * U256::from(10).pow(U256::from(18));

        let gross_amount_out = principal_amount * U256::from((route.estimated_profit_ratio * 10000.0) as u64) / U256::from(10000);
        
        let slippage_amount = calculate_slippage_amount(route, principal_amount);

        if gross_amount_out > slippage_amount {
            let net_amount_out = gross_amount_out - slippage_amount;
            let profit = net_amount_out - principal_amount;

            if profit > best_profit {
                best_profit = profit;
                optimal_size = principal_amount;
            }
        }
    }

    route.estimated_net_profit_usd = Some(best_profit.to_string());
    optimal_size
}