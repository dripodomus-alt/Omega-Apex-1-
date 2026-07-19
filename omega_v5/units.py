#!/usr/bin/env python3
# ==============================================================================
# units.py -- Centralized token amount and gas conversion utilities.
#
# This module is the single source of truth for converting between token decimal
# amounts, their raw integer (wei-like) representations, and their USD value.
# It ensures consistency across all financial calculations in the pipeline.
# ==============================================================================

from __future__ import annotations

from decimal import Decimal, ROUND_FLOOR
from typing import Optional

from . import rpc_layer
from .oracle_layer import PriceUnavailable, token_price_usd


NATIVE_GAS_TOKEN = "WPOL"


def to_raw_units(symbol: str, amount_decimal: Decimal) -> int:
    """Converts a decimal token amount to its raw integer representation (e.g., wei)."""
    if not isinstance(amount_decimal, Decimal):
        amount_decimal = Decimal(str(amount_decimal))

    if amount_decimal <= 0:
        return 0

    decimals = int(rpc_layer.TOKEN_DECIMALS.get(symbol, 18))
    raw = amount_decimal * (Decimal(10) ** decimals)
    return int(raw.to_integral_value(rounding=ROUND_FLOOR))


def from_raw_units(symbol: str, amount_raw: int | Decimal) -> Decimal:
    """Converts a raw integer token amount (e.g., wei) to its decimal representation."""
    if not isinstance(amount_raw, Decimal):
        amount_raw = Decimal(str(amount_raw))

    decimals = int(rpc_layer.TOKEN_DECIMALS.get(symbol, 18))
    return amount_raw / (Decimal(10) ** decimals)


def usd_to_token(symbol: str, usd_amount: Decimal, price: Optional[Decimal] = None) -> Decimal:
    """Converts a USD amount to a token's decimal amount."""
    if not isinstance(usd_amount, Decimal):
        usd_amount = Decimal(str(usd_amount))

    if usd_amount <= 0:
        return Decimal("0")

    try:
        px = Decimal(str(price)) if price is not None else token_price_usd(symbol)
        if px <= 0:
            return Decimal("0")
        return usd_amount / px
    except (PriceUnavailable, Exception):
        return Decimal("0")


def token_to_usd(symbol: str, token_amount: Decimal, price: Optional[Decimal] = None) -> Decimal:
    """Converts a token's decimal amount to its USD value."""
    if not isinstance(token_amount, Decimal):
        token_amount = Decimal(str(token_amount))

    try:
        px = Decimal(str(price)) if price is not None else token_price_usd(symbol)
        return token_amount * px
    except (PriceUnavailable, Exception):
        return Decimal("0")


def gwei_to_wei(gwei: Decimal) -> int:
    """Converts Gwei to Wei."""
    if not isinstance(gwei, Decimal):
        gwei = Decimal(str(gwei))
    return to_raw_units(NATIVE_GAS_TOKEN, gwei / Decimal("1_000_000_000"))


def gas_cost_usd(gas_units: int, gas_price_gwei: Decimal) -> Decimal:
    """
    Calculates the USD cost of a transaction.

    It correctly converts Gwei to the native token's full decimal amount (POL)
    and then multiplies by the native token's USD price.
    """
    if not isinstance(gas_price_gwei, Decimal):
        gas_price_gwei = Decimal(str(gas_price_gwei))

    # Total gas cost in Gwei
    total_gas_gwei = Decimal(gas_units) * gas_price_gwei
    # Convert Gwei to full POL units (1 POL = 10^18 Wei, 1 Gwei = 10^9 Wei)
    total_gas_pol = total_gas_gwei / Decimal("1_000_000_000")

    return token_to_usd(NATIVE_GAS_TOKEN, total_gas_pol)


def gas_cost_to_base_raw(
    gas_units: int,
    gas_price_gwei: Decimal,
    base_token_symbol: str,
) -> int:
    """Calculates the gas cost in terms of a base token's raw units."""
    cost_in_usd = gas_cost_usd(gas_units, gas_price_gwei)
    if cost_in_usd <= 0:
        return 0

    cost_in_base_token_decimal = usd_to_token(base_token_symbol, cost_in_usd)
    return to_raw_units(base_token_symbol, cost_in_base_token_decimal)


def usd_expense_to_base_raw(
    usd_amount: Decimal,
    symbol: str,
    price: Optional[Decimal] = None,
) -> int:
    """
    Convert a USD expense (or principal) amount to base-token raw units.
    usd <= 0 → 0 (no forced min-1; expenses may be zero).
    """
    if not isinstance(usd_amount, Decimal):
        usd_amount = Decimal(str(usd_amount))

    if usd_amount <= 0:
        return 0

    token_amount = usd_to_token(symbol, usd_amount, price=price)
    if token_amount <= 0:
        return 0
    return to_raw_units(symbol, token_amount)
