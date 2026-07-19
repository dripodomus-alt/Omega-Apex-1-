"""Pricing and net-delta modules for dimensionally correct executable opportunity math."""
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

__all__ = [
    "compute_executable_round_trip",
    "compute_net_base_surplus",
    "net_profit_usd_from_raw",
    "indicative_raw_delta_usd",
    "spread_ratio",
    "raw_execution_gate_passes",
    "simulate_route_with_real_min_out",
    "build_executable_route_economics",
]
