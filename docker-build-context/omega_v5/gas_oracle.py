#!/usr/bin/env python3
# ==============================================================================
# gas_oracle.py -- Polygon EIP-1559 fee intelligence.
# ==============================================================================

from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import requests

from .config import (
    POLYGON_GAS_STATION_ENABLED,
    POLYGON_GAS_STATION_TIMEOUT_SECONDS,
    POLYGON_GAS_STATION_TIER,
    POLYGON_GAS_STATION_TTL_SECONDS,
    POLYGON_GAS_STATION_URL,
    POLYGON_MAX_FEE_SAFETY_MULTIPLIER,
    POLYGON_MIN_PRIORITY_FEE_GWEI,
)


@dataclass(frozen=True)
class GasQuote:
    base_fee_gwei: Decimal
    priority_fee_gwei: Decimal
    max_fee_gwei: Decimal
    tier: str
    source: str
    fetched_at: float
    raw: dict[str, Any]

    @property
    def expected_effective_gwei(self) -> Decimal:
        """Best estimate of what the tx actually pays (base + priority)."""
        return self.base_fee_gwei + self.priority_fee_gwei


_CACHE: tuple[float, GasQuote] | None = None


def _as_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    try:
        dec = Decimal(str(value))
        return dec if dec >= 0 else default
    except Exception:
        return default


def _rpc_fallback_quote() -> GasQuote:
    try:
        from . import rpc_layer

        if rpc_layer.w3 is not None and rpc_layer.RPC_LIVE:
            gas_price = Decimal(str(rpc_layer.w3.eth.gas_price)) / Decimal("1e9")
            priority = min(gas_price, POLYGON_MIN_PRIORITY_FEE_GWEI)
            base = max(Decimal("0"), gas_price - priority)
            max_fee = max(gas_price, base + priority)
            return GasQuote(
                base_fee_gwei=base,
                priority_fee_gwei=priority,
                max_fee_gwei=max_fee,
                tier="rpc",
                source="polygon_rpc_gas_price",
                fetched_at=time.time(),
                raw={"gasPriceGwei": str(gas_price)},
            )
    except Exception:
        pass

    # Static micro-gas fallback ≈ $0.001 class on Polygon flash arbs.
    # base 5 + priority floor → expected ~10 gwei effective when priority floor is 5.
    priority = min(POLYGON_MIN_PRIORITY_FEE_GWEI, Decimal("5"))
    if priority <= 0:
        priority = Decimal("5")
    base = Decimal("5")
    expected = base + priority
    return GasQuote(
        base_fee_gwei=base,
        priority_fee_gwei=priority,
        max_fee_gwei=max(expected * Decimal("1.5"), Decimal("15")),
        tier="static",
        source="static_gas_oracle_fallback_micro",
        fetched_at=time.time(),
        raw={"note": "polygon_micro_gas_fallback", "expected_gwei": str(expected)},
    )


def _parse_station_quote(payload: dict[str, Any], tier: str) -> GasQuote:
    row = payload.get(tier) if isinstance(payload.get(tier), dict) else {}
    if not row and tier != "fast":
        row = payload.get("fast") if isinstance(payload.get("fast"), dict) else {}

    base = _as_decimal(payload.get("estimatedBaseFee"))
    if base <= 0:
        base = _as_decimal(payload.get("baseFee"))

    priority = _as_decimal(row.get("maxPriorityFee") or row.get("maxPriorityFeePerGas"))
    priority = max(priority, POLYGON_MIN_PRIORITY_FEE_GWEI)

    max_fee = _as_decimal(row.get("maxFee") or row.get("maxFeePerGas"))
    floor = (base + priority) * POLYGON_MAX_FEE_SAFETY_MULTIPLIER
    if max_fee <= 0:
        max_fee = floor
    else:
        max_fee = max(max_fee, floor)

    return GasQuote(
        base_fee_gwei=base,
        priority_fee_gwei=priority,
        max_fee_gwei=max_fee,
        tier=tier,
        source=f"polygon_gas_station_v2.{tier}",
        fetched_at=time.time(),
        raw=payload,
    )


def polygon_gas_quote(force: bool = False, tier: str | None = None) -> GasQuote:
    global _CACHE
    now = time.time()
    selected_tier = (tier or POLYGON_GAS_STATION_TIER or "fast").lower()
    if selected_tier not in {"safeLow", "safelow", "standard", "fast"}:
        selected_tier = "fast"
    if selected_tier == "safelow":
        selected_tier = "safeLow"

    if _CACHE and not force and now - _CACHE[0] <= POLYGON_GAS_STATION_TTL_SECONDS:
        return _CACHE[1]

    if not POLYGON_GAS_STATION_ENABLED:
        quote = _rpc_fallback_quote()
        _CACHE = (now, quote)
        return quote

    try:
        response = requests.get(
            POLYGON_GAS_STATION_URL,
            timeout=float(POLYGON_GAS_STATION_TIMEOUT_SECONDS),
            headers={"accept": "application/json"},
        )
        response.raise_for_status()
        quote = _parse_station_quote(response.json(), selected_tier)
    except Exception:
        quote = _rpc_fallback_quote()

    _CACHE = (now, quote)
    return quote


def base_fee_gwei() -> tuple[Decimal, str]:
    quote = polygon_gas_quote()
    return quote.base_fee_gwei, quote.source


def profitability_gas_price_gwei() -> tuple[Decimal, str]:
    """
    Expected effective gas price for PnL math (base + priority).

    Intentionally NOT maxFeePerGas — max fee is an inclusion ceiling and would
    overstate Polygon micro-arb costs by several multiples.
    """
    quote = polygon_gas_quote()
    expected = quote.expected_effective_gwei
    if expected <= 0:
        expected = quote.max_fee_gwei
    return expected, f"{quote.source}|expected_effective"


def eip1559_fee_params() -> tuple[int, int, str]:
    """Submission ceiling fees (maxFee + priority) for real transactions."""
    quote = polygon_gas_quote()
    return (
        int((quote.max_fee_gwei * Decimal("1e9")).to_integral_value()),
        int((quote.priority_fee_gwei * Decimal("1e9")).to_integral_value()),
        quote.source,
    )
