#!/usr/bin/env python3
# ==============================================================================
# net_delta.py -- Core net profit and execution gate math.
#
# This module contains the canonical, low-level functions for calculating
# net profit and validating execution eligibility.
# ==============================================================================

from __future__ import annotations

from decimal import Decimal


def route_within_lifespan(discovery_block: int, current_block: int, n_plus_x: int) -> bool:
    """
    Checks if a route is within its execution lifespan (e.g., n+4 blocks).
    """
    if not discovery_block or not current_block:
        return False
    return 0 < (current_block - discovery_block) <= n_plus_x


def raw_execution_gate_passes(
    *,
    raw_surplus: Decimal,
    total_costs: Decimal,
    min_profit_floor: Decimal | None = None,
) -> bool:
    """
    The final, definitive raw surplus execution gate.

    This function is the single source of truth for whether a raw surplus,
    after all costs are accounted for, is profitable enough to execute.

    Args:
        raw_surplus: The gross surplus in the native asset (e.g., USDC, WETH).
        total_costs: The sum of all associated costs (gas, fees, etc.) in the same native asset.
        min_profit_floor: The minimum required profit in the native asset.
    """
    net_surplus = raw_surplus - total_costs
    return net_surplus > (min_profit_floor or Decimal("0"))