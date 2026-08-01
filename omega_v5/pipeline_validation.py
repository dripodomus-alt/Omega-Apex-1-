"""
Pipeline integrity and pre-execution validation.
Updated to include validate_payload_ids_and_sequence that checks registry alignment and the new sequence proof.
"""

from __future__ import annotations
import logging
from decimal import Decimal

from typing import Any, Dict

from .invariant_math import verify_buy_low_sell_high_sequence
from .config import build_protocol_sequence_ids, MIN_CALldata_LENGTH, MAX_CALldata_LENGTH, STABLE_SWAP_MAX_PEG_DEVIATION_BPS
from .pricing import PricingError
from .pricing.precision_pricing import get_price_usd_x18
from .cycle_logger import cycle_logger, CycleEventType, CycleType
from .stable_strategies import peg_group_for
from .units import x18_deviation_bps, decimal_to_x18

logger = logging.getLogger(__name__)


def _route_get(route: Any, key: str, default: Any = None) -> Any:
    if hasattr(route, "get"):
        return route.get(key, default)
    return getattr(route, key, default)


def _to_decimal_or_zero(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return Decimal("0")
        try:
            return Decimal(stripped)
        except Exception:
            return Decimal("0")
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


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


def validate_usdc_value_correlation(
    route: Dict[str, Any],
    opportunity_id: str | None = None,
    cycle_id: str | None = None,
    *,
    max_deviation_bps: int | None = None,
) -> bool:
    """Fail closed if the route's stable-asset unit diverges from the USDC anchor."""
    if route is None:
        return False

    if hasattr(route, "get"):
        opp_id = opportunity_id or route.get("opp_id") or route.get("opportunity_id") or "unknown"
        cid = cycle_id or route.get("cycle_id") or "unknown"
    else:
        opp_id = opportunity_id or getattr(route, "opp_id", None) or getattr(route, "opportunity_id", None) or "unknown"
        cid = cycle_id or getattr(route, "cycle_id", None) or "unknown"

    candidate = str(
        _route_get(route, "principal_token")
        or _route_get(route, "base_token")
        or (_route_get(route, "path", ["USDC"]) or ["USDC"])[0]
        or "USDC"
    )
    if peg_group_for(candidate) != "USD_STABLE" and candidate != "USDC":
        return True

    threshold = int(max_deviation_bps if max_deviation_bps is not None else STABLE_SWAP_MAX_PEG_DEVIATION_BPS)

    try:
        usdc_price_x18 = int(get_price_usd_x18("USDC"))
        candidate_price_x18 = int(get_price_usd_x18(candidate))
    except Exception as exc:
        cycle_logger.log_event(
            opportunity_id=opp_id,
            cycle_id=cid,
            cycle_type=CycleType.C1,
            event_type=CycleEventType.VALIDATION_FAILED,
            message=f"USDC normalization gate failed to resolve prices: {exc}",
            metadata={
                "reject_reason": "USDC_NORMALIZATION_PRICE_UNAVAILABLE",
                "candidate_symbol": candidate,
            },
        )
        return False

    deviation_bps = x18_deviation_bps(candidate_price_x18, usdc_price_x18)
    if deviation_bps > threshold:
        cycle_logger.log_event(
            opportunity_id=opp_id,
            cycle_id=cid,
            cycle_type=CycleType.C1,
            event_type=CycleEventType.VALIDATION_FAILED,
            message=(
                f"USDC normalization gate rejected {candidate}: deviation_bps={deviation_bps} "
                f"threshold={threshold}"
            ),
            metadata={
                "reject_reason": "USDC_NORMALIZATION_DRIFT",
                "candidate_symbol": candidate,
                "reference_symbol": "USDC",
                "candidate_price_x18": str(candidate_price_x18),
                "reference_price_x18": str(usdc_price_x18),
                "deviation_bps": deviation_bps,
                "threshold_bps": threshold,
            },
        )
        return False

    return True


def _get_route_profitability(route: Any) -> dict[str, Any]:
    profitability = _route_get(route, "profitability") or {}
    if isinstance(profitability, dict):
        return profitability
    return {
        "gross_surplus_usd": getattr(profitability, "gross_surplus_usd", 0),
        "flashloan_fee_usd": getattr(profitability, "flashloan_fee_usd", 0),
        "gas_cost_usd": getattr(profitability, "gas_cost_usd", 0),
        "relay_tip_usd": getattr(profitability, "relay_tip_usd", 0),
        "risk_buffer_usd": getattr(profitability, "risk_buffer_usd", 0),
        "net_profit_usd": getattr(profitability, "net_profit_usd", 0),
    }


def validate_canonical_execution_proof(
    route: Dict[str, Any], opportunity_id: str | None = None, cycle_id: str | None = None
) -> bool:
    """Enforce a single normalized economic proof gate for profit and cost reconciliation."""
    if route is None:
        return False

    if hasattr(route, "get"):
        opp_id = opportunity_id or route.get("opp_id") or route.get("opportunity_id") or "unknown"
        cid = cycle_id or route.get("cycle_id") or "unknown"
    else:
        opp_id = opportunity_id or getattr(route, "opp_id", None) or getattr(route, "opportunity_id", None) or "unknown"
        cid = cycle_id or getattr(route, "cycle_id", None) or "unknown"

    profitability = _get_route_profitability(route)
    gross_surplus = _to_decimal_or_zero(profitability.get("gross_surplus_usd", 0))
    flashloan_fee = _to_decimal_or_zero(profitability.get("flashloan_fee_usd", 0))
    gas_cost = _to_decimal_or_zero(profitability.get("gas_cost_usd", 0))
    relay_tip = _to_decimal_or_zero(profitability.get("relay_tip_usd", 0))
    risk_buffer = _to_decimal_or_zero(profitability.get("risk_buffer_usd", 0))
    reported_net = _to_decimal_or_zero(profitability.get("net_profit_usd", 0))

    expected_net = gross_surplus - flashloan_fee - gas_cost - relay_tip - risk_buffer
    expected_net_x18 = decimal_to_x18(expected_net)
    reported_net_x18 = decimal_to_x18(reported_net)

    if reported_net_x18 != expected_net_x18:
        cycle_logger.log_event(
            opportunity_id=opp_id,
            cycle_id=cid,
            cycle_type=CycleType.C1,
            event_type=CycleEventType.VALIDATION_FAILED,
            message=(
                f"Canonical execution proof rejected route {opp_id}: "
                f"reported_net_x18={reported_net_x18} expected_net_x18={expected_net_x18}"
            ),
            metadata={
                "reject_reason": "CANONICAL_PROFIT_MISMATCH",
                "reported_net_usd": str(reported_net),
                "expected_net_usd": str(expected_net),
            },
        )
        return False

    if not validate_usdc_value_correlation(route, opportunity_id=opp_id, cycle_id=cid):
        return False

    return True


def validate_payload_ids_and_sequence(
    route: Dict[str, Any], opportunity_id: str | None = None, cycle_id: str | None = None
) -> bool:
    """
    New gate (step 3 of plan): validates that protocol IDs line up with config registry
    AND that the buy-low/sell-higher sequence proof passes.
    """
    if route is None:
        return False

    if hasattr(route, "get"):
        opp_id = opportunity_id or route.get("opp_id") or route.get("opportunity_id") or "unknown"
        cid = cycle_id or route.get("cycle_id") or "unknown"
    else:
        opp_id = opportunity_id or getattr(route, "opp_id", None) or getattr(route, "opportunity_id", None) or "unknown"
        cid = cycle_id or getattr(route, "cycle_id", None) or "unknown"

    try:
        logger.debug(f"[{opp_id}] Validating payload IDs and sequence.")
        ids = build_protocol_sequence_ids(route)
        if len(ids) == 0 or len(ids) != len(route.get("protocol_seq", [])):
            msg = "Protocol ID sequence length mismatch."
            logger.warning(f"[{opp_id}] {msg}")
            cycle_logger.log_event(
                opportunity_id=opp_id,
                cycle_id=cid,
                cycle_type=CycleType.C1,
                event_type=CycleEventType.VALIDATION_FAILED,
                message=msg,
            )
            return False
        if not verify_buy_low_sell_high_sequence(route):
            msg = "Economic invariant (buy-low-sell-high) failed."
            logger.warning(f"[{opp_id}] {msg}")
            cycle_logger.log_event(
                opportunity_id=opp_id,
                cycle_id=cid,
                cycle_type=CycleType.C1,
                event_type=CycleEventType.VALIDATION_FAILED,
                message=msg,
            )
            return False
        if not validate_canonical_execution_proof(route, opportunity_id=opp_id, cycle_id=cid):
            return False
        return True
    except Exception as e:
        logger.warning(f"Payload validation failed: {e}")
        cycle_logger.log_event(
            opportunity_id=opp_id,
            cycle_id=cid,
            cycle_type=CycleType.C1,
            event_type=CycleEventType.VALIDATION_FAILED,
            message=f"Payload validation failed with exception: {e}",
        )
        return False


def validate_calldata_integrity(
    calldata: str, opportunity_id: str, cycle_id: str
) -> bool:
    """
    Validates the basic integrity of the generated calldata.
    Checks for 0x prefix, even hex length, and reasonable length bounds.
    """
    if not calldata.startswith("0x"):
        msg = "Calldata missing '0x' prefix."
        logger.warning(f"[{opportunity_id}] {msg}")
        cycle_logger.log_event(
            opportunity_id=opportunity_id,
            cycle_id=cycle_id,
            cycle_type=CycleType.C1,
            event_type=CycleEventType.VALIDATION_FAILED,
            message=msg,
        )
        return False
    
    hex_body = calldata[2:]
    if len(hex_body) % 2 != 0:
        msg = "Calldata hex body has an odd number of characters."
        logger.warning(f"[{opportunity_id}] {msg}")
        cycle_logger.log_event(
            opportunity_id=opportunity_id,
            cycle_id=cycle_id,
            cycle_type=CycleType.C1,
            event_type=CycleEventType.VALIDATION_FAILED,
            message=msg,
        )
        return False

    if not (MIN_CALldata_LENGTH <= len(hex_body) <= MAX_CALldata_LENGTH):
        msg = f"Calldata length ({len(hex_body)}) is outside expected bounds ({MIN_CALldata_LENGTH}-{MAX_CALldata_LENGTH})."
        logger.warning(f"[{opportunity_id}] {msg}")
        cycle_logger.log_event(
            opportunity_id=opportunity_id,
            cycle_id=cycle_id,
            cycle_type=CycleType.C1,
            event_type=CycleEventType.VALIDATION_FAILED,
            message=msg,
        )
        return False

    # Further checks like bytes.fromhex round-trip can be added if needed, but are more expensive.
    logger.debug(f"[{opportunity_id}] Calldata integrity check passed.")
    return True


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
    mock_calldata = "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890" # Example valid length
    mock_opp_id = "opp_mock_1"
    mock_c1_id = "c1_mock_1"

    pricing_ok = validate_route_pricing(mock_route, mock_opp_id, mock_c1_id)
    print(f"Pricing validation passed: {pricing_ok}")

    payload_ok = validate_payload_ids_and_sequence(mock_route, mock_opp_id, mock_c1_id)
    print(f"Payload validation passed: {payload_ok}")
    
    calldata_ok = validate_calldata_integrity(mock_calldata, mock_opp_id, mock_c1_id)
    print(f"Calldata integrity validation passed: {calldata_ok}")

    if pricing_ok and payload_ok and calldata_ok:
        print("\nAll validation proofs passed.")
    else:
        print("\nOne or more validation proofs failed. Check cycle_events.jsonl for details.")

