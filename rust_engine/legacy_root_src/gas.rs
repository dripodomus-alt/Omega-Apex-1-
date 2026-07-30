//! # Gas Cost Estimation Model
//!
//! This module provides a static gas estimation model for arbitrage routes based
//! on the sequence of protocols involved.

use apex_routing::Route;

// These constants represent typical gas usage for swaps on the Polygon PoS network.
// They are conservative estimates and include the cost of the swap itself plus
// any associated overhead within the execution contract.

/// Base cost for any transaction, including flash loan initiation and token transfers.
const BASE_TX_COST: u64 = 95_000;

/// Gas cost for a swap on a Uniswap V2-like CPMM pool.
const V2_SWAP_COST: u64 = 70_000;

/// Gas cost for a swap on a Uniswap V3-like CLMM pool (within a single tick).
const V3_SWAP_COST: u64 = 100_000;

/// Gas cost for a swap on a Curve stableswap pool.
const CURVE_SWAP_COST: u64 = 180_000;

/// Gas cost for a swap on a Balancer weighted pool.
const BALANCER_SWAP_COST: u64 = 120_000;

/// A fallback cost for any unrecognized protocol.
const UNKNOWN_SWAP_COST: u64 = 150_000;

/// Estimates the total gas units required to execute a given arbitrage route.
///
/// The model sums a base transaction cost with the per-swap cost for each
/// protocol in the route's path.
pub fn estimate_gas(route: &Route) -> u64 {
    let mut total_gas = BASE_TX_COST;

    for pool in &route.pools {
        total_gas += match pool.protocol.as_str() {
            "QUICKSWAP_V2" | "SUSHISWAP_V2" => V2_SWAP_COST,
            "UNISWAP_V3" | "QUICKSWAP_V3" | "ALGEBRA" => V3_SWAP_COST,
            "CURVE_STABLE" => CURVE_SWAP_COST,
            "BALANCER_WEIGHTED" => BALANCER_SWAP_COST,
            _ => UNKNOWN_SWAP_COST,
        };
    }

    total_gas
}