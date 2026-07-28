#!/usr/bin/env python3
# ==============================================================================
# cycle_ids.py — Canonical opportunity / C1 / C2 ID builders (C1×C2 logging model)
# ==============================================================================
"""
Deterministic hash IDs linking one opportunity to its C1 and C2 cycles.

  opportunity_id = hash(chain_id, discovered_block, buy_pool, sell_pool,
                        borrow_asset, route_hash, state_hash, config_hash)
  c1_cycle_id    = hash(opportunity_id, "C1", discovery_block, route_hash)
  c2_cycle_id    = hash(opportunity_id, "C2", c1_tx_hash, c1_confirmed_block,
                        post_c1_state_hash, c2_route_hash)

C2 cannot exist without a confirmed C1 parent.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Optional


def _norm(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return str(value).strip().lower()


def stable_hash(*parts: Any, prefix: str = "") -> str:
    """SHA-256 hex digest over normalized parts. Optional human prefix."""
    material = "|".join(_norm(p) for p in parts)
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    if prefix:
        return f"{prefix}_{digest[:24]}"
    return digest


def route_hash(pool_sequence: Iterable[str], path: Optional[Iterable[str]] = None) -> str:
    pools = [str(p).lower() for p in (pool_sequence or [])]
    tokens = [str(t).upper() for t in (path or [])]
    return stable_hash("route", pools, tokens, prefix="rh")


def state_hash(block: int | str, pool_state_fingerprint: Any) -> str:
    return stable_hash("state", block, pool_state_fingerprint, prefix="sh")


def config_hash(config_version: int | str, extra: Any = None) -> str:
    return stable_hash("config", config_version, extra, prefix="ch")


def build_opportunity_id(
    *,
    chain_id: int,
    discovered_block: int,
    buy_pool: str,
    sell_pool: str,
    borrow_asset: str,
    route_hash_value: str,
    state_hash_value: str,
    config_hash_value: str,
) -> str:
    return stable_hash(
        chain_id,
        discovered_block,
        buy_pool,
        sell_pool,
        borrow_asset,
        route_hash_value,
        state_hash_value,
        config_hash_value,
        prefix=f"opp_{chain_id}_{discovered_block}",
    )


def build_c1_cycle_id(
    *,
    opportunity_id: str,
    discovery_block: int,
    route_hash_value: str,
) -> str:
    return stable_hash(opportunity_id, "C1", discovery_block, route_hash_value, prefix="c1")


def build_c2_cycle_id(
    *,
    opportunity_id: str,
    c1_tx_hash: str,
    c1_confirmed_block: int,
    post_c1_state_hash: str,
    c2_route_hash: str = "",
) -> str:
    return stable_hash(
        opportunity_id,
        "C2",
        c1_tx_hash,
        c1_confirmed_block,
        post_c1_state_hash,
        c2_route_hash,
        prefix="c2",
    )


def event_id(
    *,
    opportunity_id: str,
    cycle_id: str,
    event_type: str,
    block_number: Optional[int] = None,
    created_at_ms: Optional[int] = None,
) -> str:
    return stable_hash(
        opportunity_id,
        cycle_id,
        event_type,
        block_number,
        created_at_ms,
        prefix="ev",
    )
