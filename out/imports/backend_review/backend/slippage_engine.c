#include <math.h>
#include <stdint.h>

#define EXPORT __attribute__((visibility("default")))

// 🔱 TITAN V12.4 | MULTI-PROTOCOL SLIPPAGE ENGINE

// 1. CURVE STABLESWAP INVARIANT MATH
EXPORT double simulate_curve_slippage(
    double amount_in, 
    double total_reserve,
    double amp_factor // Amplification coefficient (A)
) {
    // Curve slippage is significantly lower within the equilibrium range
    // Prediction: (amount / reserve) ^ 2 * (1 / amp)
    double ratio = amount_in / total_reserve;
    double slip = (pow(ratio, 2.0) / (amp_factor / 100.0)) * 100.0;
    return (slip < 0.0001) ? 0.0001 : slip; // Floor at 0.01 bps
}

// 2. BALANCER WEIGHTED POOL MATH
EXPORT double simulate_weighted_slippage(
    double amount_in,
    double reserve_in,
    double weight_in, // e.g., 0.80 for 80/20
    double weight_out
) {
    // Slippage = 1 - (reserve_in / (reserve_in + amount_in)) ^ (weight_in / weight_out)
    double weight_ratio = weight_in / weight_out;
    double price_impact = 1.0 - pow((reserve_in / (reserve_in + amount_in)), weight_ratio);
    return price_impact * 100.0;
}

// 3. UNISWAP V3 CONCENTRATED LIQUIDITY
EXPORT double simulate_v3_slippage(
    double amount_in_usd,
    double active_liquidity,
    double fee_bps
) {
    double fee = fee_bps / 10000.0;
    double amount_after_fee = amount_in_usd * (1.0 - fee);
    double delta_sqrt_p = amount_after_fee / active_liquidity;
    double predicted_slip_pct = delta_sqrt_p * 102.0; // 2% safety buffer
    return (predicted_slip_pct > 10.0) ? 10.0 : predicted_slip_pct;
}

// 4. UNISWAP V2 CONSTANT PRODUCT (x*y=k)
EXPORT double simulate_v2_slippage(
    double amount_in,
    double reserve_in,
    double reserve_out,
    double fee_bps
) {
    double fee = fee_bps / 10000.0;
    double amount_with_fee = amount_in * (1.0 - fee);
    double new_reserve_in = reserve_in + amount_with_fee;
    double k = reserve_in * reserve_out;
    double new_reserve_out = k / new_reserve_in;
    double amount_out = reserve_out - new_reserve_out;
    
    // Calculate price impact
    double expected_rate = reserve_out / reserve_in;
    double actual_rate = amount_out / amount_in;
    double slippage = ((expected_rate - actual_rate) / expected_rate) * 100.0;
    return (slippage < 0) ? 0 : slippage;
}

// 5. OPTIMAL TRADE SIZE CALCULATOR
EXPORT double calculate_optimal_size(
    double liquidity,
    double max_slippage_pct,
    double fee_bps,
    int protocol_type // 0=V2, 1=V3, 2=Curve, 3=Balancer
) {
    double fee = fee_bps / 10000.0;
    double max_slip = max_slippage_pct / 100.0;
    
    switch(protocol_type) {
        case 0: // V2
            return liquidity * max_slip / (2.0 + max_slip);
        case 1: // V3
            return (max_slip * liquidity) / (102.0 * (1.0 - fee));
        case 2: // Curve
            return liquidity * sqrt(max_slip / 100.0);
        case 3: // Balancer
            return liquidity * (1.0 - pow(1.0 - max_slip, 2.0));
        default:
            return liquidity * 0.01; // 1% conservative default
    }
}

// 6. MULTI-HOP AGGREGATE SLIPPAGE
EXPORT double aggregate_slippage(
    double* slippages,
    int hop_count
) {
    double total = 1.0;
    for(int i = 0; i < hop_count; i++) {
        total *= (1.0 - slippages[i] / 100.0);
    }
    return (1.0 - total) * 100.0;
}

// 7. GAS-ADJUSTED PROFITABILITY
EXPORT double calculate_net_profit(
    double gross_profit_usd,
    double gas_price_gwei,
    double gas_units,
    double matic_price_usd
) {
    double gas_cost_matic = (gas_price_gwei * gas_units) / 1e9;
    double gas_cost_usd = gas_cost_matic * matic_price_usd;
    return gross_profit_usd - gas_cost_usd;
}
