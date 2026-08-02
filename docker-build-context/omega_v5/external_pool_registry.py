#!/usr/bin/env python3
# ==============================================================================
# external_pool_registry.py -- fail-closed pool registry metadata importer.
# ==============================================================================

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from web3 import Web3

from .paths import resolve_repo_relative


QUICKSWAP_V2_FACTORY_POLYGON = "0x5757371414417b8C6CAad45bAeF941aBc7d3Ab32"
SUSHISWAP_V2_FACTORY_POLYGON = "0xc35DADB65012eC5796536bD9864eD8773aBc74C4"
UNISWAP_V3_FACTORY_POLYGON = "0x1F98431c8aD98523631AE4a59f267346ea31F984"


@dataclass(frozen=True)
class DynamicPoolImportResult:
    registry: dict[str, dict[str, Any]]
    stats: dict[str, Any]


def _clean_symbol(value: Any) -> str:
    symbol = str(value or "").strip()
    if symbol in {"WMATIC", "MATIC", "POL"}:
        return "WPOL"
    return symbol


def _protocol(row: dict[str, Any]) -> str:
    raw = str(row.get("protocol", "")).strip()
    dex = str(row.get("dex_name", "")).lower()
    if raw == "2":
        return "UniswapV2"
    if raw == "3":
        return "QuickSwapV3" if "quick" in dex and "v3" in dex else "UniswapV3"
    return ""


def _factory(row: dict[str, Any], protocol: str) -> str:
    dex = str(row.get("dex_name", "")).lower()
    if protocol == "UniswapV2":
        if "sushi" in dex:
            return SUSHISWAP_V2_FACTORY_POLYGON
        return QUICKSWAP_V2_FACTORY_POLYGON
    if protocol == "UniswapV3":
        return UNISWAP_V3_FACTORY_POLYGON
    return ""


def _symbol_from_address(
    address: str,
    fallback: Any,
    address_to_symbol: dict[str, str],
) -> str:
    return address_to_symbol.get(str(address).lower()) or _clean_symbol(fallback)


def load_dynamic_pool_registry(
    path: str | Path,
    *,
    address_to_symbol: dict[str, str],
    token_addresses: dict[str, str],
    known_pool_addresses: set[str],
    max_pools: int,
) -> DynamicPoolImportResult:
    registry: dict[str, dict[str, Any]] = {}
    stats: dict[str, Any] = {
        "enabled": True,
        "path": str(path),
        "rows": 0,
        "promoted": 0,
        "skipped": {},
        "by_protocol": {},
    }
    resolved = resolve_repo_relative(path)
    if not resolved.exists():
        stats["enabled"] = False
        stats["error"] = f"dynamic pool registry file not found: {resolved}"
        return DynamicPoolImportResult(registry, stats)

    payload = json.loads(resolved.read_text(encoding="utf-8"))
    rows = payload.get("pools") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        stats["enabled"] = False
        stats["error"] = "dynamic pool registry JSON must contain a pools list"
        return DynamicPoolImportResult(registry, stats)

    stats["rows"] = len(rows)
    known_tokens = set(token_addresses)
    skipped: dict[str, int] = {}
    by_protocol: dict[str, int] = {}

    def skip(reason: str) -> None:
        skipped[reason] = skipped.get(reason, 0) + 1

    unbounded = int(max_pools or 0) <= 0
    for row in rows:
        if not unbounded and len(registry) >= max_pools:
            skip("max_pools_reached")
            break
        if not isinstance(row, dict):
            skip("row_not_object")
            continue

        address = str(row.get("pair_address", "")).strip()
        token0_addr = str(row.get("token0_address", "")).lower()
        token1_addr = str(row.get("token1_address", "")).lower()
        if not Web3.is_address(address):
            skip("bad_pool_address")
            continue
        if address.lower() in known_pool_addresses:
            skip("duplicate_pool_address")
            continue
        if not Web3.is_address(token0_addr) or not Web3.is_address(token1_addr):
            skip("bad_token_address")
            continue

        token0 = _symbol_from_address(token0_addr, row.get("token0_symbol"), address_to_symbol)
        token1 = _symbol_from_address(token1_addr, row.get("token1_symbol"), address_to_symbol)
        if token0 not in known_tokens or token1 not in known_tokens:
            skip("unknown_token")
            continue

        protocol = _protocol(row)
        if protocol not in {"UniswapV2", "UniswapV3", "QuickSwapV3"}:
            skip("unsupported_protocol")
            continue

        try:
            fee_bps = int(row.get("fee_bps") or 30)
        except Exception:
            fee_bps = 30

        pool_id = (
            f"DYN_{protocol}_{token0}_{token1}_{fee_bps}_{address[-6:]}"
            .replace(".", "_")
            .replace("-", "_")
        )
        registry[pool_id] = {
            "protocol": protocol,
            "token0": token0,
            "token1": token1,
            "address": Web3.to_checksum_address(address),
            "fee_bps": fee_bps,
            "factory_address": _factory(row, protocol),
            "_meta": {
                "discovery_source": "pools_dynamic_json",
                "dex_name": str(row.get("dex_name", "")),
                "raw_protocol": str(row.get("protocol", "")),
                "token0_address": token0_addr,
                "token1_address": token1_addr,
                "token0_decimals": row.get("token0_decimals"),
                "token1_decimals": row.get("token1_decimals"),
                "execution_policy": "metadata_only_live_rpc_state_required",
            },
        }
        known_pool_addresses.add(address.lower())
        by_protocol[protocol] = by_protocol.get(protocol, 0) + 1

    stats["promoted"] = len(registry)
    stats["unbounded"] = unbounded
    stats["skipped"] = skipped
    stats["by_protocol"] = by_protocol
    return DynamicPoolImportResult(registry, stats)
