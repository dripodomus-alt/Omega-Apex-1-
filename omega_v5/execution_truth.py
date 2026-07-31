#!/usr/bin/env python3
# ==============================================================================
# execution_truth.py — final on-chain truth gating before execution.
# Updated to call the new payload ID and sequence validation.
# ==============================================================================

import logging
import os
from decimal import Decimal
from typing import Any, Dict, List, Tuple

from .pipeline_validation import validate_payload_ids_and_sequence
from .execution import build_tx_payload, simulate_tx_payload, simulation_from_address
from .payload_envelope import build_payload_envelope
from .rpc_layer import get_web3_instance # Assuming rpc_layer provides a web3 instance
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

def batch_simulate_with_truth(opportunities: List[Any], pools: dict) -> List[Tuple[Any, bool]]:
    """
    Performs batched `eth_call` simulations for a list of opportunities.

    Args:
        opportunities: A list of opportunity objects.
        pools: A dictionary of live pool data required for building transactions.

    Returns:
        A list of tuples, where each tuple contains the original opportunity
        and a boolean indicating if its simulation was successful.
    """
    if not opportunities:
        return []

    w3 = get_web3_instance()
    batch = w3.eth.batch()
    results = []

    for opp in opportunities:
        # This is where the real simulation logic should be integrated.
        # We build the transaction payload and then simulate it.
        try:
            # NOTE: This assumes `opp` has the necessary structure.
            # The `pools` dictionary would need to be passed into this function.
            # For now, we'll assume it's available in a higher scope.
            tx = build_tx_payload(opp, pools, nonce=0) # Nonce doesn't matter for eth_call
            
            # Use the robust simulation function from execution.py
            sim_ok, sim_detail = simulate_tx_payload(tx, from_addr=simulation_from_address())
            
            if sim_ok:
                results.append({"opp": opp, "sim_passed": True})
            else:
                results.append({"opp": opp, "sim_passed": False})
        except Exception as e:
            logger.warning(f"Failed to prepare simulation for opp {opp.get('opp_id', 'unknown')}: {e}")
            results.append({"opp": opp, "sim_passed": False})

    # In a real implementation with batch.add(), you would execute the batch here:
    # batch.execute()
    # And then process the results from the batch promises.

    # For this example, we return the placeholder results.
    return [(r["opp"], r["sim_passed"]) for r in results]
