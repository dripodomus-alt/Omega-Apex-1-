"""
Pipeline integrity and pre-execution validation.
Updated to include validate_payload_ids_and_sequence that checks registry alignment and the new sequence proof.
"""

from __future__ import annotations
import logging

from typing import Any, Dict

from .invariant_math import verify_buy_low_sell_high_sequence
from .config import build_protocol_sequence_ids
from .pricing import PricingError
from .pricing.precision_pricing import get_price_usd_x18
from .cycle_logger import cycle_logger, CycleEventType, CycleType

logger = logging.getLogger(__name__)


def validate_route_pricing(
    route: Dict[str, Any], opportunity_id: str, cycle_id: str
) -> bool:
    """
    Example gate: ensure the route carries or can produce x18 prices
    that would pass the precision engine.
    """
    try:
        price = get_price_usd_x18(route.get("principal_token", "USDC"))
        if price <= 0:
            cycle_logger.log_event(
                opportunity_id=opportunity_id,
                cycle_id=cycle_id,
                cycle_type=CycleType.C1,
                event_type=CycleEventType.VALIDATION_FAILED,
                message="Route pricing validation failed: Non-positive price.",
            )
            return False
        return True
    except PricingError as e:
        cycle_logger.log_event(
            opportunity_id=opportunity_id,
            cycle_id=cycle_id,
            cycle_type=CycleType.C1,
            event_type=CycleEventType.VALIDATION_FAILED,
            message=f"Route pricing validation failed: {e}",
        )
        return False


def validate_payload_ids_and_sequence(
    route: Dict[str, Any], opportunity_id: str, cycle_id: str
) -> bool:
    """
    New gate (step 3 of plan): validates that protocol IDs line up with config registry
    AND that the buy-low/sell-higher sequence proof passes.
    """
    try:
        # Use the canonical builder (aligns with payload encoding)
        logger.debug(f"[{opportunity_id}] Validating payload IDs and sequence.")
        ids = build_protocol_sequence_ids(route)
        if len(ids) == 0 or len(ids) != len(route.get("protocol_seq", [])):
            msg = "Protocol ID sequence length mismatch."
            logger.warning(f"[{opportunity_id}] {msg}")
            cycle_logger.log_event(
                opportunity_id=opportunity_id,
                cycle_id=cycle_id,
                cycle_type=CycleType.C1,
                event_type=CycleEventType.VALIDATION_FAILED,
                message=msg,
            )
            return False
        if not verify_buy_low_sell_high_sequence(route):
            msg = "Economic invariant (buy-low-sell-high) failed."
            logger.warning(f"[{opportunity_id}] {msg}")
            cycle_logger.log_event(
                opportunity_id=opportunity_id,
                cycle_id=cycle_id,
                cycle_type=CycleType.C1,
                event_type=CycleEventType.VALIDATION_FAILED,
                message=msg,
            )
            return False
        return True
    except Exception as e:
        logger.warning(f"Payload validation failed: {e}")
        cycle_logger.log_event(
            opportunity_id=opportunity_id,
            cycle_id=cycle_id,
            cycle_type=CycleType.C1,
            event_type=CycleEventType.VALIDATION_FAILED,
            message=f"Payload validation failed with exception: {e}",
        )
        return False


if __name__ == "__main__":
    # Example of running the validation checks with the new logging integration
    # This is for demonstration; real integration happens in the state machine.
    print("Running pipeline validation proof with logging integration...")
    mock_route = {
        "opp_id": "mock-opp-123",
        "protocol_seq": ["V2_CPMM", "V3_CLMM"],
        "principal_token": "USDC",
        "profitability": {"buy_price_usd": "3000", "sell_price_usd": "3001"},
    }
    mock_opp_id = "opp_mock_1"
    mock_c1_id = "c1_mock_1"

    pricing_ok = validate_route_pricing(mock_route, mock_opp_id, mock_c1_id)
    print(f"Pricing validation passed: {pricing_ok}")

    payload_ok = validate_payload_ids_and_sequence(mock_route, mock_opp_id, mock_c1_id)
    print(f"Payload validation passed: {payload_ok}")

    if pricing_ok and payload_ok:
        print("\nAll validation proofs passed.")
    else:
        print("\nOne or more validation proofs failed. Check cycle_events.jsonl for details.")
