"""
cycle_discovery.py — Executable-cycle discovery using ranked pools only.
"""

from typing import List, Dict, Any
from .route_deduplicator import deduplicate_routes


def discover_executable_cycles(
    ranked_buy_sell_routes: List[Dict[str, Any]],
    max_hops: int = 4,
) -> List[Dict[str, Any]]:
    """Only routes that already passed price ranking + same-block + min_out gates."""
    cycles = []
    for r in ranked_buy_sell_routes:
        # Already filtered by executable_price_ranker
        cycles.append({
            "path": [r["base"], r["mid"], r["base"]],
            "pool_sequence": [r["buy_pool"], r["sell_pool"]],
            "mid_min_out_raw": r["mid_min_out_raw"],
            "base_min_out_raw": r["base_min_out_raw"],
            "flash_principal_usd": r["flash_principal_usd"],
        })
    return deduplicate_routes(cycles)
