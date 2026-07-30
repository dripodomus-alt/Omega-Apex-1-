use apex_adapters::{
    get_adapter,
};
use apex_routing::{ArbitrageGraph, Route};
use apex_types::{GateConfig, RawPool, ScannerError};
use apex_simulation::{gas::estimate_gas, sizing::find_optimal_size};
use alloy_primitives::{Address, U256};
use std::collections::{HashMap, HashSet};
use futures::future::join_all;
use tokio;

/// Main scanner entrypoint. Builds a graph and finds arbitrage cycles.
#[tokio::main]
pub async fn scan_opportunities(
    pools_json: &str,
    _config: &GateConfig,
) -> Result<Vec<Route>, ScannerError> {
    let pools: HashMap<String, RawPool> = serde_json::from_str(pools_json)?;
    let mut graph = ArbitrageGraph::new();
    let mut all_tokens = Vec::new();
    let mut quote_tasks = Vec::new();

    // Define a fixed principal amount for quoting. This will be replaced by a
    // dynamic sizing model in a later stage.
    let principal_amount = U256::from(1_000_000_000_000_000_000u128); // 1.0 of a token with 18 decimals

    // 1. Build the graph
    for pool in pools.values() {
        if pool.tokens.len() == 2 {
            let token0 = pool.tokens[0];
            let token1 = pool.tokens[1];

            if !all_tokens.contains(&token0) { all_tokens.push(token0); }
            if !all_tokens.contains(&token1) { all_tokens.push(token1); }

            let adapter = get_adapter(&pool.protocol);

            // Create async tasks for quoting in both directions.
            let pool_clone_a = pool.clone();
            let adapter_a = adapter.clone();
            let task_a_to_b = async move { (pool_clone_a.clone(), token0, token1, adapter_a.quote(&pool_clone_a, &token0, principal_amount).await) };

            let pool_clone_b = pool.clone();
            let adapter_b = adapter.clone();
            let task_b_to_a = async move { (pool_clone_b.clone(), token1, token0, adapter_b.quote(&pool_clone_b, &token1, principal_amount).await) };

            quote_tasks.push(Box::pin(task_a_to_b));
            quote_tasks.push(Box::pin(task_b_to_a));
        }
    }

    // Execute all quote tasks in parallel.
    let results = join_all(quote_tasks).await;

    // Process the results to build the graph.
    for (pool, token_in, token_out, result) in results {
        if let Ok(quote) = result {
            if !quote.amount_out.is_zero() {
                let price = U256::to_f64_lossy(quote.amount_out) / U256::to_f64_lossy(principal_amount);
                graph.add_edge(token_in, token_out, pool, price);
            }
        }
    }

    // 2. Find routes from all known tokens
    let mut all_routes = Vec::new();
    let mut seen_routes = HashSet::new();

    for token in all_tokens {
        if let Ok(routes) = graph.find_routes(token) {
            for route in routes {
                // Filter out unprofitable routes and apply basic validation
                if route.estimated_profit_ratio > 1.0001 { // e.g., > 0.01% profit
                    // Create a canonical representation of the route to avoid duplicates
                    let mut canonical_pools = route.pools.iter().map(|p| p.address.to_string()).collect::<Vec<_>>();
                    canonical_pools.sort();
                    let route_signature = canonical_pools.join("-");

                    if seen_routes.insert(route_signature) {
                        all_routes.push(route);
                    }
                }
            }
        }
    }

    // Sort by profitability
    all_routes.sort_by(|a, b| b.estimated_profit_ratio.partial_cmp(&a.estimated_profit_ratio).unwrap_or(std::cmp::Ordering::Equal));

    Ok(all_routes)
}