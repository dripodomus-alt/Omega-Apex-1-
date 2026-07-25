"""Pricing and net-delta modules for dimensionally correct executable opportunity math.

Now includes the PrecisionPricingEngine (Python port of the canonical TS logic)
for strict 18-decimal integer arithmetic across the entire pipeline.
"""
from .net_delta import (
    compute_executable_round_trip,
    compute_net_base_surplus,
    net_profit_usd_from_raw,
    indicative_raw_delta_usd,
    spread_ratio,
    raw_execution_gate_passes,
    simulate_route_with_real_min_out,
    build_executable_route_economics,
)
from .precision_pricing import (
    PrecisionPricingEngine,
    PricingError,
    PriceResult,
    PricePair,
    TokenMetadata,
    TokenOraclePolicy,
    OracleObservation,
    OracleSource,
    PricingContext,
    OracleKind,
    Rounding,
    PRICE_DECIMALS,
    PRICE_SCALE,
    BPS_DENOMINATOR,
    scale_decimals,
    mul_div,
    divide,
    calculate_deviation_bps,
    aggregate_prices,
    pow10,
    create_default_engine,
)

__all__ = [
    # legacy net-delta
    "compute_executable_round_trip",
    "compute_net_base_surplus",
    "net_profit_usd_from_raw",
    "indicative_raw_delta_usd",
    "spread_ratio",
    "raw_execution_gate_passes",
    "simulate_route_with_real_min_out",
    "build_executable_route_economics",
    # precision engine (new canonical path)
    "PrecisionPricingEngine",
    "PricingError",
    "PriceResult",
    "PricePair",
    "TokenMetadata",
    "TokenOraclePolicy",
    "OracleObservation",
    "OracleSource",
    "PricingContext",
    "OracleKind",
    "Rounding",
    "PRICE_DECIMALS",
    "PRICE_SCALE",
    "BPS_DENOMINATOR",
    "scale_decimals",
    "mul_div",
    "divide",
    "calculate_deviation_bps",
    "aggregate_prices",
    "pow10",
    "create_default_engine",
]
