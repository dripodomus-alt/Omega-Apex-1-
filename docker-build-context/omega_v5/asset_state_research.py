#!/usr/bin/env python3
# ==============================================================================
# asset_state_research.py -- asset metadata and live-state proof artifact.
#
# Produces a transparent row per configured/discovered asset, joining metadata,
# oracle status, live pool membership, depth, quality gates, and route-edge
# coverage. It is read-only and never signs, simulates, or broadcasts.
# ==============================================================================

from __future__ import annotations

import argparse
import json
import time
from collections import Counter, defaultdict
from decimal import Decimal
from typing import Any

from web3 import Web3

from . import rpc_layer
from .asset_metadata_resolver import resolve_asset_metadata
from .config import ASSET_MATRIX, CHAIN_ID, HTTP_URL
from .liquidity_registry import build_verified_pool_registry
from .oracle_layer import PriceUnavailable, TOKEN_USD_SOURCE, refresh_token_prices, token_price_usd
from .paths import output_path
from .pool_quality import route_quality_metadata
from .ranker import compute_all_pool_rates
from .sizing import estimate_pool_tvl_usd


LATEST_RESEARCH_REPORT = output_path("asset_state_research_latest.json")
HISTORY_RESEARCH_REPORT = output_path("asset_state_research_history.jsonl")

_ABI_ERC20_METADATA = [
    {"name": "symbol", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"name": "", "type": "string"}]},
    {"name": "name", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"name": "", "type": "string"}]},
    {"name": "decimals", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"name": "", "type": "uint8"}]},
    {"name": "totalSupply", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"name": "", "type": "uint256"}]},
]


def _json_ready(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(item) for item in value]
    return value


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except Exception:
        return Decimal("0")


def _pool_token_depth_usd(pool: dict[str, Any], token: str) -> Decimal:
    depths = pool.get("executable_token_depth_usd")
    if isinstance(depths, dict) and token in depths:
        value = _decimal(depths.get(token))
        if value > 0:
            return value
    tokens = list(pool.get("tokens") or [])
    reserves = list(pool.get("reserves") or [])
    if token in tokens and len(reserves) == len(tokens):
        try:
            return _decimal(reserves[tokens.index(token)]) * token_price_usd(token)
        except (PriceUnavailable, ArithmeticError, IndexError):
            return Decimal("0")
    return Decimal("0")


def _asset_sources(symbol: str, pools: dict[str, dict]) -> list[str]:
    sources: set[str] = set()
    if symbol in ASSET_MATRIX:
        sources.add("config.ASSET_MATRIX")
    if symbol in rpc_layer.TOKEN_ADDRESSES:
        sources.add("runtime.TOKEN_ADDRESSES")
    for pool in pools.values():
        if symbol not in (pool.get("tokens") or []):
            continue
        meta = pool.get("_meta", {}) if isinstance(pool.get("_meta"), dict) else {}
        if meta.get("discovery_source"):
            sources.add(str(meta["discovery_source"]))
        elif pool.get("pool_family") == "curve_stable":
            sources.add("curve_pool_registry")
        else:
            sources.add(str(pool.get("protocol") or "live_pool"))
    return sorted(sources)


def _read_erc20_metadata(symbol: str, address: str, *, timeout_label: str = "") -> dict[str, Any]:
    if rpc_layer.w3 is None or not rpc_layer.RPC_LIVE:
        return {"status": "skipped", "reason": "rpc_not_connected"}
    if not address or not Web3.is_address(address):
        return {"status": "fail", "reason": "invalid_or_missing_address"}
    try:
        checksum = Web3.to_checksum_address(address)
        code = rpc_layer.w3.eth.get_code(checksum)
        if not code:
            return {"status": "fail", "reason": "address_has_no_code"}
        contract = rpc_layer.w3.eth.contract(address=checksum, abi=_ABI_ERC20_METADATA)
        row: dict[str, Any] = {"status": "pass", "code_present": True}
        for field in ("symbol", "name", "decimals", "totalSupply"):
            try:
                row[field] = getattr(contract.functions, field)().call()
            except Exception as exc:
                row[f"{field}_error"] = f"{type(exc).__name__}: {exc}"[:240]
        expected_decimals = rpc_layer.TOKEN_DECIMALS.get(symbol)
        actual_decimals = row.get("decimals")
        row["decimals_match_config"] = (
            actual_decimals == expected_decimals
            if actual_decimals is not None and expected_decimals is not None
            else None
        )
        return row
    except Exception as exc:
        return {
            "status": "fail",
            "reason": f"{type(exc).__name__}: {exc}"[:300],
            "timeout_label": timeout_label,
        }


def _metadata_status(row: dict[str, Any], onchain: dict[str, Any]) -> tuple[str, list[str]]:
    blockers: list[str] = []
    metadata_resolution = row.get("metadata_resolution") if isinstance(row.get("metadata_resolution"), dict) else {}
    blockers.extend(str(item) for item in metadata_resolution.get("blockers", []))
    if onchain and onchain.get("status") == "fail":
        blockers.append(f"onchain_metadata_{onchain.get('reason', 'failed')}")
    if onchain and onchain.get("decimals_match_config") is False:
        blockers.append("onchain_decimals_mismatch")
    return ("pass" if not blockers else "fail"), blockers


def _live_status(row: dict[str, Any]) -> tuple[str, list[str]]:
    blockers: list[str] = []
    if int(row.get("pool_count") or 0) <= 0:
        blockers.append("not_in_any_loaded_pool")
    if _decimal(row.get("total_executable_depth_usd")) <= 0:
        blockers.append("no_positive_live_depth")
    if int(row.get("directional_edges_out") or 0) <= 0 and int(row.get("directional_edges_in") or 0) <= 0:
        blockers.append("no_directional_quote_edges")
    if _decimal(row.get("price_usd")) <= 0:
        blockers.append("price_unavailable")
    return ("pass" if not blockers else "fail"), blockers


def build_asset_state_research(
    *,
    pools: dict[str, dict],
    rates: dict,
    onchain_metadata: bool = False,
    onchain_limit: int = 0,
) -> dict[str, Any]:
    started = time.time()
    refresh_token_prices(force=True)
    registry_rows = build_verified_pool_registry(pools)
    assets = set(ASSET_MATRIX) | set(rpc_layer.TOKEN_ADDRESSES)
    for pool in pools.values():
        assets.update(str(token) for token in (pool.get("tokens") or []) if token)
    for token_in, token_out in rates:
        assets.add(str(token_in))
        assets.add(str(token_out))

    pool_ids_by_asset: dict[str, list[str]] = defaultdict(list)
    protocols_by_asset: dict[str, Counter[str]] = defaultdict(Counter)
    depth_by_asset: dict[str, Decimal] = defaultdict(Decimal)
    max_pool_tvl_by_asset: dict[str, Decimal] = defaultdict(Decimal)
    quality_by_asset: dict[str, Counter[str]] = defaultdict(Counter)
    for pool_id, pool in pools.items():
        tokens = [str(token) for token in (pool.get("tokens") or []) if token]
        for token in tokens:
            pool_ids_by_asset[token].append(pool_id)
            protocols_by_asset[token][str(pool.get("protocol") or "")] += 1
            depth_by_asset[token] += _pool_token_depth_usd(pool, token)
            max_pool_tvl_by_asset[token] = max(max_pool_tvl_by_asset[token], estimate_pool_tvl_usd(pool))
            quality = route_quality_metadata([pool_id], pools)
            if quality["clmm_orientation_decimals"] != "pass":
                quality_by_asset[token]["clmm_orientation_decimals_failed"] += 1
            if quality["v2_pair_canonical"] != "pass":
                quality_by_asset[token]["v2_pair_canonical_failed"] += 1

    edges_out: Counter[str] = Counter()
    edges_in: Counter[str] = Counter()
    for (token_in, token_out), entries in rates.items():
        edges_out[str(token_in)] += len(entries)
        edges_in[str(token_out)] += len(entries)

    onchain_budget = len(assets) if onchain_limit <= 0 else onchain_limit
    onchain_reads = 0
    rows: list[dict[str, Any]] = []
    for symbol in sorted(assets):
        address = rpc_layer.TOKEN_ADDRESSES.get(symbol, "")
        price = Decimal("0")
        price_status = "unavailable"
        try:
            price = token_price_usd(symbol)
            price_status = "pass" if price > 0 else "unavailable"
        except PriceUnavailable:
            price_status = "unavailable"
        onchain = {"status": "skipped", "reason": "disabled"}
        if onchain_metadata and onchain_reads < onchain_budget:
            onchain = _read_erc20_metadata(symbol, address)
            onchain_reads += 1
        metadata_resolution = resolve_asset_metadata(symbol, pools, onchain_metadata=onchain)
        resolved_address = str(metadata_resolution.get("address") or address)
        row: dict[str, Any] = {
            "symbol": symbol,
            "chain_id": CHAIN_ID,
            "address": resolved_address,
            "canonical_asset_id": f"{CHAIN_ID}:{resolved_address.lower()}" if resolved_address else rpc_layer.canonical_asset_id(symbol),
            "configured_decimals": rpc_layer.TOKEN_DECIMALS.get(symbol),
            "resolved_decimals": metadata_resolution.get("decimals"),
            "resolved_name": metadata_resolution.get("name", ""),
            "metadata_resolution": metadata_resolution,
            "discovery_status": rpc_layer.TOKEN_DISCOVERY_STATUS.get(symbol, "configured_or_runtime_added"),
            "sources": _asset_sources(symbol, pools),
            "price_usd": price,
            "price_status": price_status,
            "price_source": TOKEN_USD_SOURCE.get(symbol, ""),
            "pool_count": len(pool_ids_by_asset.get(symbol, [])),
            "pool_ids": pool_ids_by_asset.get(symbol, [])[:100],
            "protocol_counts": dict(protocols_by_asset.get(symbol, Counter())),
            "total_executable_depth_usd": depth_by_asset.get(symbol, Decimal("0")),
            "max_pool_tvl_usd": max_pool_tvl_by_asset.get(symbol, Decimal("0")),
            "directional_edges_out": edges_out.get(symbol, 0),
            "directional_edges_in": edges_in.get(symbol, 0),
            "quality_failures": dict(quality_by_asset.get(symbol, Counter())),
            "onchain_metadata": onchain,
        }
        metadata_status, metadata_blockers = _metadata_status(row, onchain)
        live_state_status, live_blockers = _live_status(row)
        row["metadata_status"] = metadata_status
        row["live_state_status"] = live_state_status
        row["execution_blockers"] = metadata_blockers + live_blockers
        row["route_research_status"] = "ready_for_route_search" if not row["execution_blockers"] else "blocked_or_watch"
        rows.append(row)

    summary = {
        "asset_count": len(rows),
        "metadata_pass": sum(1 for row in rows if row["metadata_status"] == "pass"),
        "live_state_pass": sum(1 for row in rows if row["live_state_status"] == "pass"),
        "ready_for_route_search": sum(1 for row in rows if row["route_research_status"] == "ready_for_route_search"),
        "priced_assets": sum(1 for row in rows if _decimal(row["price_usd"]) > 0),
        "assets_with_pools": sum(1 for row in rows if int(row["pool_count"]) > 0),
        "assets_with_quote_edges": sum(1 for row in rows if int(row["directional_edges_out"]) + int(row["directional_edges_in"]) > 0),
        "loaded_pool_count": len(pools),
        "verified_pool_registry_rows": len(registry_rows),
        "rate_pairs": len(rates),
        "directional_quote_edges": sum(len(entries) for entries in rates.values()),
        "onchain_metadata_reads": onchain_reads,
    }
    blocker_counts: Counter[str] = Counter()
    for row in rows:
        for blocker in row["execution_blockers"]:
            blocker_counts[str(blocker)] += 1

    return {
        "ok": True,
        "mode": "read_only_asset_metadata_and_live_state_research",
        "chain_id": CHAIN_ID,
        "block": rpc_layer.BLOCK,
        "elapsed_seconds": Decimal(str(round(time.time() - started, 3))),
        "summary": summary,
        "blocker_counts": dict(sorted(blocker_counts.items())),
        "source_policy": {
            "metadata": ["config.ASSET_MATRIX", "runtime.TOKEN_ADDRESSES", "Polygon token list", "Curve official API", "dynamic pool registry", "optional on-chain ERC20 reads"],
            "live_state": ["Polygon RPC pool state", "pool quality audits", "oracle_layer live prices", "computed directional quote graph"],
            "execution_policy": "research only; no signing, no broadcast",
        },
        "assets": rows,
    }


def write_report(report: dict[str, Any]) -> None:
    LATEST_RESEARCH_REPORT.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_RESEARCH_REPORT.parent.mkdir(parents=True, exist_ok=True)
    LATEST_RESEARCH_REPORT.write_text(json.dumps(_json_ready(report), indent=2, sort_keys=True), encoding="utf-8")
    with HISTORY_RESEARCH_REPORT.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_json_ready(report), sort_keys=True) + "\n")


def run_once(*, rpc_url: str = "", onchain_metadata: bool = False, onchain_limit: int = 0) -> dict[str, Any]:
    if not rpc_layer.connect(http_urls=[rpc_url or HTTP_URL], wss_url="", prefer_wss=False):
        raise RuntimeError("RPC connection failed")
    pools = rpc_layer.load_all_live_pools(rpc_layer.DEEP_POOL_REGISTRY)
    rates = compute_all_pool_rates(pools)
    report = build_asset_state_research(
        pools=pools,
        rates=rates,
        onchain_metadata=onchain_metadata,
        onchain_limit=onchain_limit,
    )
    write_report(report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build deep asset metadata and live-state research artifact.")
    parser.add_argument("--rpc-url", default="")
    parser.add_argument("--onchain-metadata", action="store_true", help="Read ERC20 metadata from chain for assets in the report.")
    parser.add_argument("--onchain-limit", type=int, default=0, help="0 means all assets when --onchain-metadata is enabled.")
    args = parser.parse_args()
    report = run_once(
        rpc_url=args.rpc_url,
        onchain_metadata=args.onchain_metadata,
        onchain_limit=max(0, args.onchain_limit),
    )
    summary = report["summary"]
    print(
        "asset_state_research=OK "
        f"assets={summary['asset_count']} "
        f"metadata_pass={summary['metadata_pass']} "
        f"live_state_pass={summary['live_state_pass']} "
        f"ready={summary['ready_for_route_search']} "
        f"quotes={summary['directional_quote_edges']} "
        f"path={LATEST_RESEARCH_REPORT}",
        flush=True,
    )


if __name__ == "__main__":
    main()
