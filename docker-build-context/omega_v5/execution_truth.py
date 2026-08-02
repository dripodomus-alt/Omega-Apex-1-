#!/usr/bin/env python3
# ==============================================================================
# execution_truth.py — final on-chain truth gating before execution.
# Updated to call the new payload ID and sequence validation.
# ==============================================================================

import logging
import os
import asyncio
from decimal import Decimal
from typing import Any, Dict, List, Tuple

from .pipeline_validation import validate_payload_ids_and_sequence
from .execution import build_tx_payload, simulate_tx_payload
from .payload_envelope import build_payload_envelope
from .config import MIN_FLASH_PRINCIPAL_USD
from .transport_lanes import web3_for_lane, LANE_EXACT_C1_ETH_CALL, simulation_from_address

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
    opp_id = getattr(opportunity, "opp_id", None) or (opportunity.get("opp_id", "unknown") if isinstance(opportunity, dict) else "unknown")
    if not validate_payload_ids_and_sequence(route, opportunity_id=str(opp_id), cycle_id=None):
        logger.error("Execution truth failed: payload IDs or sequence proof invalid")
        return False

    payload = build_payload_envelope(opportunity)
    payload_stage = payload.get("payload", {}) if isinstance(payload, dict) else {}
    logger.info(f"Truth verified for opp {opp_id} with protocol_ids={payload_stage.get('protocol_ids')}")
    return True

# Original functions preserved (e.g. simulate_with_truth, etc.)
def simulate_with_truth(route: Dict[str, Any], pools: dict) -> bool:
    """
    Simulates a single route to verify its truth before execution.
    This function now requires live pool data, removing the previous mock implementation.
    """
    if not verify_execution_truth(route):
        return False

    try:
        # The `route` object is expected to be a dict-like structure that
        # `build_tx_payload` can process, and `pools` must contain live data.
        tx = build_tx_payload(route, pools, nonce=0)

        # Perform the simulation using the helper from the execution module,
        # which correctly uses the dedicated transport lane for eth_call.
        sim_ok, sim_detail = simulate_tx_payload(
            tx, from_addr=simulation_from_address()
        )
        if not sim_ok:
            logger.warning(f"Execution truth simulation failed: {sim_detail}")
        return sim_ok
    except Exception as e:
        logger.error(f"Error during simulate_with_truth: {e}")
        return False

async def _simulate_one_opp(opp: Any, pools: dict) -> Tuple[Any, bool]:
    """Helper to simulate a single opportunity, designed for concurrent execution."""
    try:
        # Build the transaction payload. Nonce is irrelevant for eth_call.
        tx = build_tx_payload(opp, pools, nonce=0)

        # Use the robust simulation function from execution.py.
        # The `from_addr` is sourced from the transport lane module.
        sim_ok, sim_detail = simulate_tx_payload(
            tx, from_addr=simulation_from_address()
        )

        if not sim_ok:
            logger.debug(f"Truth sim failed for {getattr(opp, 'opp_id', 'N/A')}: {sim_detail}")
        return opp, sim_ok
    except Exception as e:
        logger.warning(f"Failed to prepare simulation for opp {getattr(opp, 'opp_id', 'unknown')}: {e}")
        return opp, False

def batch_simulate_with_truth(opportunities: List[Any], pools: dict) -> List[Tuple[Any, bool]]:
    """
    Performs batched, concurrent `eth_call` simulations for a list of opportunities.
    This API has been normalized to remove the `w3_override` and now uses asyncio
    for improved performance.

    Args:
        opportunities: A list of opportunity objects.
        pools: A dictionary of live pool data required for building transactions.

    Returns:
        A list of tuples, where each tuple contains the original opportunity and a
        boolean indicating if its simulation was successful.
    """
    if not opportunities:
        return []

    async def run_simulations():
        tasks = [_simulate_one_opp(opp, pools) for opp in opportunities]
        return await asyncio.gather(*tasks)

    try:
        return asyncio.run(run_simulations())
    except RuntimeError: # Handles cases where an event loop is already running
        return asyncio.get_event_loop().run_until_complete(run_simulations())
