#!/usr/bin/env python3
# ==============================================================================
# rust_scanner.py -- Python wrapper for the high-performance Rust scanner engine.
#
# This module serves as the integration point between the Python host and the
# compiled Rust `scanner_core` library. It handles data preparation, invocation,
a# and result transformation.
# ==============================================================================

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, List
import logging

from .ranker import compute_all_pool_rates
from .opportunity_ranker import LiveOpportunity, _score_closed_path
from .flash_loan import FlashSource
from .config import MIN_TVL_USD

logger = logging.getLogger(__name__)

# Attempt to import the compiled Rust module
try:
    from scanner_core import GateConfig, scan_opportunities as rust_scan
    RUST_SCANNER_AVAILABLE = True
    logger.info("Rust scanner engine (`scanner_core`) loaded successfully.")
except ImportError:
    RUST_SCANNER_AVAILABLE = False
    rust_scan = None
    GateConfig = None
    logger.warning("Rust scanner engine (`scanner_core`) not found. Falling back to Python implementation.")


def _prepare_pools_for_rust(pools: dict[str, Any], rates: dict[tuple[str, str], list[dict]]) -> str:
    """
    Enriches the pool data with the executable price and serializes it to JSON
    for the Rust engine.
    """
    pools_with_price = {}
    
    # Create a lookup for rates by pool_id
    rate_lookup = {}
    for pair_rates in rates.values():
        for rate_info in pair_rates:
            rate_lookup[rate_info['pool_id']] = rate_info.get('rate', '0')

    for pool_id, pool_data in pools.items():
        # The Rust engine expects a flat structure with the executable price.
        # We use the pre-computed rate as the definitive price.
        enriched_pool = {
            "protocol": pool_data.get("protocol", "Unknown"),
            "address": pool_data.get("address", "0x" + "0" * 40),
            "tokens": pool_data.get("tokens", []),
            "total_executable_liquidity_usd": str(pool_data.get("total_executable_liquidity_usd", "0")),
            "executable_price": str(rate_lookup.get(pool_id, "0")),
        }
        pools_with_price[pool_id] = enriched_pool
        
    return json.dumps(pools_with_price)


def find_opportunities_with_rust(
    live_pools: dict[str, Any],
    principal_usd: Decimal,
    slippage_bps: Decimal,
) -> list[LiveOpportunity]:
    """
    Discovers arbitrage opportunities using the high-performance Rust scanner.

    This function orchestrates the process:
    1. Computes initial rates in Python.
    2. Prepares and passes the data to the Rust `scan_opportunities` function.
    3. The Rust engine finds profitable, validated candidates.
    4. This function transforms the Rust candidates back into Python `LiveOpportunity` objects.
    """
    if not RUST_SCANNER_AVAILABLE or not rust_scan or not GateConfig:
        return []

    # 1. Compute rates in Python, as it has the complex pricing models.
    rates = compute_all_pool_rates(live_pools)

    # 2. Prepare data for Rust.
    pools_json = _prepare_pools_for_rust(live_pools, rates)
    gate_config = GateConfig(min_tvl_usd=str(MIN_TVL_USD))

    # 3. Invoke the Rust scanner.
    rust_candidates = rust_scan(pools_json, gate_config)

    # 4. Transform Rust candidates into full-fledged LiveOpportunity objects.
    # This step is simplified for now. A full implementation would re-run the
    # profitability calculation (`_score_closed_path`) on the candidates
    # found by Rust to generate the complete profitability breakdown.
    opportunities = []
    for candidate in rust_candidates:
        # This is a placeholder transformation. We create a minimal LiveOpportunity.
        # The full profitability object would be built here.
        mock_opp = LiveOpportunity(
            path=(candidate.token_in_address, candidate.token_mid_address, candidate.token_in_address),
            pool_sequence=(candidate.buy_pool_address, candidate.sell_pool_address),
            protocol_seq=(candidate.buy_pool_protocol, candidate.sell_pool_protocol),
            profitability=None, # In a full implementation, this would be calculated.
            metadata={"source": "rust_scanner", "rust_candidate": candidate.__dict__}
        )
        opportunities.append(mock_opp)

    logger.info(f"Rust scanner found {len(opportunities)} opportunities.")
    return opportunities