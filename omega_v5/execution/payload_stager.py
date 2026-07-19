"""
payload_stager.py — Final gate before broadcast. Uses conflict graph + nonce lanes.

Enforces the canonical raw execution gate before any route reaches STAGED.
Also enforces per-route block lifespan (discovery_block + 4).

Flash injection size must already be set on the route (from optimal_flash_sizer /
ranker). This module refuses to invent principal; it only normalizes aliases.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from ..graph.conflict_graph import select_non_conflicting
from .nonce_lane_manager import NonceLaneManager
from ..pricing.net_delta import raw_execution_gate_passes, route_within_lifespan


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_flash_injection(route: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure flash_principal_raw / flash_principal_usd are consistent for the gate.
    Prefer explicit raw; else sizing.flash_principal_raw; never invent from thin air.
    """
    sizing = route.get("sizing") if isinstance(route.get("sizing"), dict) else {}

    principal_raw = _as_int(
        route.get("flash_principal_raw")
        or sizing.get("flash_principal_raw")
        or route.get("injection_raw_hint")
        or 0
    )
    if principal_raw > 0:
        route["flash_principal_raw"] = principal_raw

    principal_usd = (
        route.get("flash_principal_usd")
        or route.get("flash_injection_usd")
        or route.get("principal_usd")
        or sizing.get("flash_principal_usd")
        or sizing.get("flash_injection_usd")
    )
    if principal_usd is not None:
        route["flash_principal_usd"] = str(principal_usd)
        route["principal_usd"] = str(principal_usd)

    # Alias sell out fields
    if not route.get("sell_amount_out_raw") and route.get("base_min_out_raw"):
        route["sell_amount_out_raw"] = _as_int(route.get("base_min_out_raw"))
    if not route.get("base_min_out_raw") and route.get("sell_amount_out_raw"):
        route["base_min_out_raw"] = _as_int(route.get("sell_amount_out_raw"))

    return route


def _route_passes_raw_gate(route: Dict[str, Any]) -> bool:
    """Extract raw values from a route dict and apply the canonical gate."""
    route = _normalize_flash_injection(route)
    try:
        sell_out = _as_int(
            route.get("base_min_out_raw") or route.get("sell_amount_out_raw") or 0
        )
        principal = _as_int(route.get("flash_principal_raw") or 0)
        flash_fee = _as_int(route.get("flash_fee_raw", 0))
        gas = _as_int(route.get("gas_cost_raw", 0))
        relay = _as_int(route.get("relay_cost_raw", 0))
        risk = _as_int(route.get("risk_buffer_raw", 0))
        min_profit = _as_int(route.get("minimum_profit_raw", 1), default=1)

        if principal <= 0 or sell_out <= 0:
            return False

        return raw_execution_gate_passes(
            sell_amount_out_raw=sell_out,
            flash_principal_raw=principal,
            flash_fee_raw=flash_fee,
            gas_cost_raw=gas,
            relay_cost_raw=relay,
            risk_buffer_raw=risk,
            minimum_profit_raw=min_profit,
        )
    except (ValueError, TypeError):
        return False


def _route_is_stale(route: Dict[str, Any], current_block: int) -> bool:
    """Check if route has exceeded its individual n+4 block lifespan."""
    discovery_block = route.get("discovery_block")
    if discovery_block is None:
        return True  # unknown origin = treat as stale
    return not route_within_lifespan(int(discovery_block), int(current_block), max_blocks=4)


def stage_payload(
    validated_routes: List[Dict[str, Any]],
    nonce_manager: NonceLaneManager,
    current_block: int,
    max_staged: int = 8,
) -> List[Dict[str, Any]]:
    """
    Stage only non-conflicting, nonce-reserved routes that:
    - Carry a TVL/peak-delta sized flash_principal_raw
    - Pass the raw execution gate
    - Are still within their individual discovery_block + 4 lifespan

    No artificial delays. Execute as soon as possible.
    """
    normalized = [_normalize_flash_injection(dict(r)) for r in validated_routes]

    # Filter 1: raw gate (includes principal presence)
    gate_passed = [r for r in normalized if _route_passes_raw_gate(r)]

    # Filter 2: per-route block lifespan (n + 4)
    alive = [r for r in gate_passed if not _route_is_stale(r, current_block)]

    independent = select_non_conflicting(alive)
    staged: List[Dict[str, Any]] = []
    for r in independent[:max_staged]:
        if nonce_manager.reserve_nonce(r):
            r["staged"] = True
            r["stage"] = "STAGED"
            r["passed_raw_execution_gate"] = True
            r["executed_within_lifespan"] = True
            # Payload injection size (authoritative for C1 flash amount)
            r["payload_flash_principal_raw"] = _as_int(r.get("flash_principal_raw"))
            r["payload_flash_principal_usd"] = str(
                r.get("flash_principal_usd") or r.get("principal_usd") or "0"
            )
            staged.append(r)
    return staged
