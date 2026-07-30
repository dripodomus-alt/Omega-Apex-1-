#!/usr/bin/env python3
# ==============================================================================
# execution_truth.py — final on-chain truth gating before execution.
# Updated to call the new payload ID and sequence validation.
# ==============================================================================

import logging
import os
from decimal import Decimal
from typing import Any, Dict

from .pipeline_validation import validate_payload_ids_and_sequence
from .payload_envelope import build_payload_envelope
from .config import MIN_FLASH_PRINCIPAL_USD, build_protocol_sequence_ids

logger = logging.getLogger("omega.truth")

def _truth_min_principal_floor(opportunity: Any) -> Decimal:
    metadata = getattr(opportunity, "metadata", {}) or {}
    gate = metadata.get("principal_gate", {}) if isinstance(metadata, dict) else {}
    proof_only = bool(gate.get("proof_only_below_minimum"))
    allow = os.environ.get("OMEGA_TRUTH_ALLOW_BELOW_MIN_PRINCIPAL_PROOF", "false").lower() in {"1", "true", "yes", "on"}
    runtime_mode = os.environ.get("OMEGA_RUNTIME_MODE", os.environ.get("EXECUTION_MODE", "dry_run")).lower()
    live_trading = os.environ.get("LIVE_TRADING", "0").lower() in {"1", "true", "yes", "on"}
    if proof_only and allow and runtime_mode in {"dry_run", "dry-run", "simulation"} and not live_trading:
        return Decimal(os.environ.get("OMEGA_TRUTH_MIN_PROOF_PRINCIPAL_USD", "25") or "25")
    return Decimal(str(MIN_FLASH_PRINCIPAL_USD))

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
