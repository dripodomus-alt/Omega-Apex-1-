#!/usr/bin/env python3
"""Runtime accessor for the canonical pricing engine interface."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from .precision_pricing import PRICE_SCALE, PriceResult
from ..oracle_layer import token_price_usd


class OracleBackedPricingEngine:
    """Small adapter exposing get_usd_price for legacy callers."""

    def get_usd_price(self, token: Any, context: Any | None = None) -> PriceResult:
        symbol = getattr(token, "symbol", None) or str(token)
        price = Decimal(str(token_price_usd(symbol)))
        return PriceResult(
            price_usd_x18=int((price * Decimal(PRICE_SCALE)).to_integral_value()),
            source_ids=["oracle_layer.token_price_usd"],
            aggregation="DIRECT",
            deviation_bps=0,
            max_deviation_bps=0,
            min_confidence_bps=0,
        )


_ENGINE = OracleBackedPricingEngine()


def get_engine() -> OracleBackedPricingEngine:
    return _ENGINE