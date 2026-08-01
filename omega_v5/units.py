#!/usr/bin/env python3
# ==============================================================================
# units.py -- Centralized token amount and gas conversion utilities.
#
# This module is the single source of truth for converting between token decimal
# amounts, their raw integer (wei-like) representations, and their USD value.
#
# Updated for full compatibility with the PrecisionPricingEngine:
# - New pure-int paths (token_atomic_to_usd_x18, usd_x18_to_token_atomic, etc.)
#   that match the TS BigInt logic exactly (18-decimal scale, mulDiv, rounding).
# - Legacy Decimal helpers preserved for non-critical paths.
# - Pipeline should prefer the precision_* functions for execution math.
# ==============================================================================

from __future__ import annotations

from decimal import Decimal, ROUND_FLOOR
from functools import lru_cache
from typing import Optional

from . import rpc_layer
from .exceptions import PriceUnavailable
from .pricing import (
    PrecisionPricingEngine,
    TokenMetadata,
    PRICE_SCALE,
    mul_div,
    pow10,
    Rounding,
)

NATIVE_GAS_TOKEN = "WPOL"


def _as_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def decimal_to_x18(value: object) -> int:
    """Canonical x18 normalization for Decimal-style values."""
    normalized = _as_decimal(value)
    if normalized <= 0:
        return 0
    return int((normalized * Decimal(PRICE_SCALE)).to_integral_value(rounding=ROUND_FLOOR))


def x18_to_decimal(value: int | Decimal) -> Decimal:
    """Canonical Decimal representation for an x18-scaled integer value."""
    normalized = _as_decimal(value)
    if normalized <= 0:
        return Decimal("0")
    return normalized / Decimal(PRICE_SCALE)


def value_equivalent_x18(
    left_x18: int | Decimal,
    right_x18: int | Decimal,
    *,
    max_deviation_bps: int = 0,
) -> bool:
    """Returns True when two x18 values are equivalent within the configured deviation budget."""
    left = int(_as_decimal(left_x18))
    right = int(_as_decimal(right_x18))
    if left <= 0 or right <= 0:
        return False
    if max_deviation_bps <= 0:
        return left == right
    return abs(left - right) * 10_000 // right <= int(max_deviation_bps)


def x18_deviation_bps(value_x18: int | Decimal, reference_x18: int | Decimal) -> int:
    """Measures x18 deviation against a positive reference as basis points."""
    value = int(_as_decimal(value_x18))
    reference = int(_as_decimal(reference_x18))
    if value <= 0 or reference <= 0:
        return 10_000_000
    return abs(value - reference) * 10_000 // reference


# ── Legacy Decimal paths (kept for backward compatibility) ────────────────────
def to_raw_units(symbol: str, amount_decimal: Decimal, *, decimals_override: int | None = None) -> int:
    """Converts a decimal token amount to its raw integer representation (e.g., wei)."""
    if not isinstance(amount_decimal, Decimal):
        amount_decimal = Decimal(str(amount_decimal))

    if amount_decimal <= 0:
        return 0

    decimals = int(decimals_override if decimals_override is not None else rpc_layer.TOKEN_DECIMALS.get(symbol, 18))
    raw = amount_decimal * (Decimal(10) ** decimals)
    return int(raw.to_integral_value(rounding=ROUND_FLOOR))


def from_raw_units(symbol: str, raw_amount: int) -> Decimal:
    """Converts raw integer units back to decimal."""
    if raw_amount <= 0:
        return Decimal("0")

    decimals = int(rpc_layer.TOKEN_DECIMALS.get(symbol, 18))
    return Decimal(raw_amount) / (Decimal(10) ** decimals)


def to_usd(symbol: str, amount_decimal: Decimal, price_usd: Decimal) -> Decimal:
    """Legacy: amount * price (Decimal). Prefer precision paths for execution."""
    if amount_decimal <= 0 or price_usd <= 0:
        return Decimal("0")
    return amount_decimal * price_usd


def raw_to_usd(symbol: str, raw_amount: int, price_usd: Decimal) -> Decimal:
    """Legacy raw -> USD using Decimal price."""
    amount = from_raw_units(symbol, raw_amount)
    return to_usd(symbol, amount, price_usd)


# ── New precision (integer-only) paths — matches TS PrecisionPricingEngine ────

@lru_cache(maxsize=128)
def get_token_metadata(symbol: str, chain_id: int = 137) -> TokenMetadata:
    """Helper to build TokenMetadata from known registry (best-effort)."""
    addr = rpc_layer.TOKEN_ADDRESSES.get(symbol, "0x0000000000000000000000000000000000000000")
    dec = int(rpc_layer.TOKEN_DECIMALS.get(symbol, 18))
    return TokenMetadata(
        chain_id=chain_id,
        address=addr,
        symbol=symbol,
        decimals=dec,
    )


def token_atomic_to_usd_x18(
    amount_atomic: int,
    token: TokenMetadata,
    price_usd_x18: int,
    rounding: Rounding = Rounding.DOWN,
) -> int:
    """Exact port of TS: amount_atomic * price / 10**decimals -> 1e18 USD."""
    token_scale = pow10(token.decimals)
    return mul_div(amount_atomic, price_usd_x18, token_scale, rounding)


def usd_x18_to_token_atomic(
    usd_value_x18: int,
    token: TokenMetadata,
    price_usd_x18: int,
    rounding: Rounding = Rounding.UP,
) -> int:
    """Exact port of TS: usd_x18 * 10**decimals / price -> atomic."""
    return mul_div(usd_value_x18, pow10(token.decimals), price_usd_x18, rounding)


def convert_token_atomic_precision(
    amount_in_atomic: int,
    token_in: TokenMetadata,
    token_in_usd_x18: int,
    token_out: TokenMetadata,
    token_out_usd_x18: int,
    rounding: Rounding = Rounding.UP,
) -> int:
    """Cross-token conversion using only integer math (gas, flash, profit, etc.)."""
    usd_value = token_atomic_to_usd_x18(
        amount_in_atomic, token_in, token_in_usd_x18, rounding
    )
    return usd_x18_to_token_atomic(
        usd_value, token_out, token_out_usd_x18, rounding
    )


def price_pair_quote_per_base_x18(
    base_price_x18: int, quote_price_x18: int, rounding: Rounding = Rounding.DOWN
) -> int:
    """quote units per 1 base token, scaled to 1e18 (exact TS derivePairPrice)."""
    return mul_div(base_price_x18, PRICE_SCALE, quote_price_x18, rounding)


# ── Bridge: use live oracle price to get x18 value (for pipeline wiring) ──────
def get_price_usd_x18(symbol: str, engine: Optional[PrecisionPricingEngine] = None) -> int:
    """
    Returns price of 1 whole token as int scaled to 1e18.
    Falls back to legacy oracle_layer if no engine provided.
    """
    # This now delegates to the canonical implementation in the precision_pricing module.
    from .pricing.precision_pricing import get_price_usd_x18 as _get_price
    return _get_price(symbol, engine)


def atomic_amount_to_usd_x18(symbol: str, amount_atomic: int, price_usd_x18: int) -> int:
    """Convenience using registry metadata + precision math."""
    token = get_token_metadata(symbol)
    return token_atomic_to_usd_x18(amount_atomic, token, price_usd_x18)


def usd_expense_to_base_raw(
    expense_usd_x18: int, base_token: TokenMetadata, base_price_x18: int
) -> int:
    """Converts a USD-denominated expense (x18) to a base token's atomic units."""
    return usd_x18_to_token_atomic(expense_usd_x18, base_token, base_price_x18, Rounding.UP)
