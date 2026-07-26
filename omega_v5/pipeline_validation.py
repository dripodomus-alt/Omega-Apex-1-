"""
Pipeline integrity and pre-execution validation.
Updated to include validate_payload_ids_and_sequence that checks registry alignment and the new sequence proof.
"""

from __future__ import annotations

from typing import Any, Dict

from .invariant_math import verify_buy_low_sell_high_sequence
from .config import build_protocol_sequence_ids
from .pricing import PrecisionPricingEngine, PricingError, PRICE_SCALE
from .pricing.precision_pricing import get_price_usd_x18


def validate_route_pricing(route: Dict[str, Any]) -> bool:
    """
    Example gate: ensure the route carries or can produce x18 prices
    that would pass the precision engine.
    """
    try:
        price = get_price_usd_x18(route.get("principal_token", "USDC"))
        if price <= 0:
            return False
        return True
    except PricingError:
        return False


def validate_payload_ids_and_sequence(route: Dict[str, Any]) -> bool:
    """
    New gate (step 3 of plan): validates that protocol IDs line up with config registry
    AND that the buy-low/sell-higher sequence proof passes.
    """
    try:
        # Use the canonical builder (aligns with payload encoding)
        ids = build_protocol_sequence_ids(route)
        if len(ids) == 0 or len(ids) != len(route.get("protocol_seq", [])):
            return False
        if not verify_buy_low_sell_high_sequence(route):
            return False
        return True
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.warning(f"Payload validation failed: {e}")
        return False


import logging  # added for the function
