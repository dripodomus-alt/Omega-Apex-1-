"""
directional_edge_builder.py — Maximize executable directional coverage.

Classifies every pool:
DISCOVERED_ONLY | STATE_HYDRATED | QUOTE_SUPPORTED | CALLDATA_SUPPORTED | FLASH_COMPATIBLE | SIMULATION_PASSED | EXECUTION_READY
"""

from typing import Dict, List, Any
from decimal import Decimal


def classify_pool(pool: Dict[str, Any]) -> str:
    if not pool.get("state_hydrated"):
        return "DISCOVERED_ONLY"
    if not pool.get("quote_supported"):
        return "STATE_HYDRATED"
    if not pool.get("calldata_supported"):
        return "QUOTE_SUPPORTED"
    if not pool.get("flash_compatible"):
        return "CALLDATA_SUPPORTED"
    if not pool.get("simulation_passed"):
        return "FLASH_COMPATIBLE"
    if pool.get("execution_ready"):
        return "EXECUTION_READY"
    return "SIMULATION_PASSED"


def build_directional_edges(
    live_pools: Dict[str, Dict],
    rates: Dict,
    block_number: int,
) -> Dict[str, Any]:
    """
    Returns full coverage report + only EXECUTION_READY edges.
    """
    edges = []
    stats = {
        "expected_edges": 1200,  # Polygon mainnet estimate for major pairs
        "discovered_edges": len(rates),
        "quote_success_edges": 0,
        "calldata_ready_edges": 0,
        "simulation_passed_edges": 0,
        "execution_ready_edges": 0,
        "duplicate_edges": 0,
        "stale_edges": 0,
        "unsupported_edges": 0,
        "failed_edges": 0,
    }

    for (t_in, t_out), pool_list in rates.items():
        for p in pool_list:
            cls = classify_pool(p)
            if cls == "EXECUTION_READY":
                stats["execution_ready_edges"] += 1
                edges.append({
                    "token_in": t_in,
                    "token_out": t_out,
                    "pool_id": p["pool_id"],
                    "protocol": p.get("protocol"),
                    "block": block_number,
                    "classification": cls,
                })
            elif cls in ("QUOTE_SUPPORTED", "CALLDATA_SUPPORTED"):
                stats["quote_success_edges"] += 1
            else:
                stats["unsupported_edges"] += 1

    stats["discovered_edges"] = len(edges) + stats["unsupported_edges"]

    return {
        "edges": edges,
        "stats": stats,
        "artifacts/edge_coverage_report.json": stats,  # for later dump
    }
