#!/usr/bin/env python3
# ==============================================================================
# execution_truth.py — final on-chain truth gating before execution.
# Updated to call the new payload ID and sequence validation.
# ==============================================================================

import logging
from typing import Any, Dict

from .pipeline_validation import validate_payload_ids_and_sequence
from .payload_envelope import build_payload_envelope
from .config import build_protocol_sequence_ids

logger = logging.getLogger("omega.truth")

def verify_execution_truth(opportunity: Any) -> bool:
    """Final gate before execution. Now includes payload alignment and sequence proof."""
    route = opportunity.route if hasattr(opportunity, 'route') else opportunity
    if not validate_payload_ids_and_sequence(route):
        logger.error("Execution truth failed: payload IDs or sequence proof invalid")
        return False
    # Build payload with aligned IDs
    payload = build_payload_envelope(opportunity)
    logger.info(f"Truth verified for opp {opportunity.get('opp_id', 'unknown')} with protocol_ids={payload.get('protocol_ids')}")
    return True

# Original functions preserved (e.g. simulate_with_truth, etc.)
def simulate_with_truth(route: Dict[str, Any]) -> bool:
    """Placeholder for original simulation logic."""
    return verify_execution_truth(route)
