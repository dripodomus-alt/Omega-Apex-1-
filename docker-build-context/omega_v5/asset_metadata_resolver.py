#!/usr/bin/env python3
# ==============================================================================
# asset_metadata_resolver.py -- multi-source asset metadata resolution.
# ==============================================================================

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from . import rpc_layer
from .paths import cache_path


POLYGON_TOKEN_LIST_CACHE = cache_path("polygon_token_list_candidates.json")


@dataclass(frozen=True)
class MetadataAttempt:
    source: str
    found: bool
    address: str = ""
    symbol: str = ""
    name: str = ""
    decimals: int | None = None
    status: str = ""
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _load_polygon_cache_rows() -> list[dict[str, Any]]:
    if not POLYGON_TOKEN_LIST_CACHE.exists():
        return []
    try:
        payload = json.loads(POLYGON_TOKEN_LIST_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return []
    rows = payload.get("candidates") if isinstance(payload, dict) else []
    return [row for row in rows if isinstance(row, dict)]


def _polygon_token_list_attempts(symbol: str, address: str) -> list[MetadataAttempt]:
    attempts: list[MetadataAttempt] = []
    symbol_u = symbol.upper()
    address_l = address.lower() if address else ""
    for row in _load_polygon_cache_rows():
        row_symbol = str(row.get("symbol") or "")
        row_address = str(row.get("address") or "")
        if row_symbol.upper() != symbol_u and (not address_l or row_address.lower() != address_l):
            continue
        attempts.append(MetadataAttempt(
            source="polygon_token_list_cache",
            found=True,
            address=row_address,
            symbol=row_symbol,
            name=str(row.get("name") or ""),
            decimals=_safe_int(row.get("decimals")),
            status=str(row.get("discovery_status") or "POLYGON_TOKEN_LIST_DISCOVERY_CANDIDATE"),
            detail=str(row.get("source_file") or ""),
        ))
    if not attempts:
        attempts.append(MetadataAttempt(
            source="polygon_token_list_cache",
            found=False,
            address=address,
            symbol=symbol,
            detail="no_symbol_or_address_match",
        ))
    return attempts


def _pool_attempts(symbol: str, pools: dict[str, dict]) -> list[MetadataAttempt]:
    attempts: list[MetadataAttempt] = []
    seen: set[tuple[str, str, int | None]] = set()
    for pool_id, pool in pools.items():
        tokens = list(pool.get("tokens") or [])
        if symbol not in tokens:
            continue
        idx = tokens.index(symbol)
        addresses = list(pool.get("token_addresses") or [])
        decimals = list(pool.get("token_decimals") or [])
        meta = pool.get("_meta", {}) if isinstance(pool.get("_meta"), dict) else {}
        source = str(meta.get("discovery_source") or pool.get("protocol") or "live_pool")
        address = str(addresses[idx]) if idx < len(addresses) else rpc_layer.TOKEN_ADDRESSES.get(symbol, "")
        dec = _safe_int(decimals[idx]) if idx < len(decimals) else rpc_layer.TOKEN_DECIMALS.get(symbol)
        key = (source, address.lower(), dec)
        if key in seen:
            continue
        seen.add(key)
        attempts.append(MetadataAttempt(
            source=f"live_pool_metadata:{source}",
            found=bool(address or dec is not None),
            address=address,
            symbol=symbol,
            decimals=dec,
            status="pool_member",
            detail=str(pool_id),
        ))
    if not attempts:
        attempts.append(MetadataAttempt(
            source="live_pool_metadata",
            found=False,
            symbol=symbol,
            detail="asset_not_present_in_loaded_pools",
        ))
    return attempts


def resolve_asset_metadata(
    symbol: str,
    pools: dict[str, dict],
    *,
    onchain_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    runtime_address = rpc_layer.TOKEN_ADDRESSES.get(symbol, "")
    runtime_decimals = rpc_layer.TOKEN_DECIMALS.get(symbol)
    attempts: list[MetadataAttempt] = [
        MetadataAttempt(
            source="runtime_registry",
            found=bool(runtime_address or runtime_decimals is not None),
            address=runtime_address,
            symbol=symbol,
            decimals=runtime_decimals,
            status=rpc_layer.TOKEN_DISCOVERY_STATUS.get(symbol, "configured_or_runtime_added"),
            detail="TOKEN_ADDRESSES/TOKEN_DECIMALS",
        )
    ]
    attempts.extend(_polygon_token_list_attempts(symbol, runtime_address))
    attempts.extend(_pool_attempts(symbol, pools))

    if onchain_metadata:
        attempts.append(MetadataAttempt(
            source="onchain_erc20_metadata",
            found=onchain_metadata.get("status") == "pass",
            address=runtime_address,
            symbol=str(onchain_metadata.get("symbol") or symbol),
            name=str(onchain_metadata.get("name") or ""),
            decimals=_safe_int(onchain_metadata.get("decimals")),
            status=str(onchain_metadata.get("status") or ""),
            detail=str(onchain_metadata.get("reason") or ""),
        ))
    else:
        attempts.append(MetadataAttempt(
            source="onchain_erc20_metadata",
            found=False,
            address=runtime_address,
            symbol=symbol,
            detail="not_requested",
        ))

    resolved_address = ""
    resolved_decimals: int | None = None
    resolved_name = ""
    resolved_symbol = symbol
    sources_used: list[str] = []

    for attempt in attempts:
        if not attempt.found:
            continue
        if not resolved_address and attempt.address:
            resolved_address = attempt.address
            sources_used.append(attempt.source)
        if resolved_decimals is None and attempt.decimals is not None:
            resolved_decimals = attempt.decimals
            sources_used.append(attempt.source)
        if not resolved_name and attempt.name:
            resolved_name = attempt.name
            sources_used.append(attempt.source)
        if attempt.symbol:
            resolved_symbol = attempt.symbol

    blockers: list[str] = []
    if not resolved_address:
        blockers.append("metadata_address_unresolved_after_all_sources")
    if resolved_decimals is None:
        blockers.append("metadata_decimals_unresolved_after_all_sources")

    return {
        "status": "resolved" if not blockers else "exhausted",
        "symbol": resolved_symbol,
        "name": resolved_name,
        "address": resolved_address,
        "decimals": resolved_decimals,
        "sources_used": sorted(set(sources_used)),
        "attempted_sources": [attempt.source for attempt in attempts],
        "attempts": [attempt.as_dict() for attempt in attempts],
        "blockers": blockers,
        "policy": "do_not_stop_on_first_missing_metadata; exhaust runtime, token-list, live-pool, curve/dynamic metadata, and optional on-chain reads",
    }
