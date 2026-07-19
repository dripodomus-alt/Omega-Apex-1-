#!/usr/bin/env python3
# ==============================================================================
# protocol_update_watcher.py -- read-only protocol/source drift monitor.
#
# The watcher refreshes discovery metadata sources, fingerprints them, compares
# the result with the previous run, and writes a status artifact. It does not
# mutate pool registry files or arm execution.
# ==============================================================================

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

from . import rpc_layer
from .config import (
    CHAIN_ID,
    CURVE_POOL_REGISTRY_API_BASE_URL,
    CURVE_POOL_REGISTRY_FAMILIES,
    CURVE_POOL_REGISTRY_MAX_POOLS,
    CURVE_POOL_REGISTRY_MIN_USD_TVL,
    DISCOVERY_MAX_PROMOTED_POOLS,
    DISCOVERY_MAX_TOKEN_PAIRS,
    DYNAMIC_POOL_REGISTRY_MAX_POOLS,
    DYNAMIC_POOLS_JSON_PATH,
    ENABLE_CURVE_POOL_REGISTRY,
    ENABLE_DYNAMIC_POOL_REGISTRY,
    ENABLE_FACTORY_POOL_DISCOVERY,
    ENABLE_POLYGON_TOKEN_LIST_DISCOVERY,
    ENABLE_SUBGRAPH_POOL_INTEL,
    POLYGON_TOKEN_LIST_BASES,
    POLYGON_TOKEN_LIST_MAX_CANDIDATES,
    SUBGRAPH_POOL_INTEL_LIMIT,
)
from .contract_deployments import resolved_deployments
from .paths import output_path, resolve_repo_relative


LATEST_REPORT = output_path("protocol_update_watch_latest.json")
HISTORY_REPORT = output_path("protocol_update_watch_history.jsonl")


def _json_ready(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(item) for item in value]
    return value


def stable_digest(value: Any) -> str:
    encoded = json.dumps(_json_ready(value), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _file_snapshot(path_value: str) -> dict[str, Any]:
    path = resolve_repo_relative(path_value)
    if not path.exists():
        return {"present": False, "path": str(path)}
    raw = path.read_bytes()
    return {
        "present": True,
        "path": str(path),
        "size_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "mtime": int(path.stat().st_mtime),
    }


def _deployment_snapshot() -> list[dict[str, Any]]:
    return [
        {
            "name": item.name,
            "env_key": item.env_key,
            "address": item.address,
            "role": item.role,
            "source": item.source,
            "required_for_execution": item.required_for_execution,
        }
        for item in resolved_deployments().values()
    ]


def _latest_pool_scan_summary() -> dict[str, Any]:
    path = output_path("live_pool_scan_report.json")
    if not path.exists():
        return {"available": False, "path": str(path)}
    payload = _read_json(path)
    return {
        "available": bool(payload),
        "path": str(path),
        "block": payload.get("block"),
        "pools_loaded": payload.get("pools_loaded"),
        "protocol_counts": payload.get("protocol_counts", {}),
        "rate_pairs": payload.get("rate_pairs"),
        "directional_quotes": payload.get("directional_quotes"),
        "registry_rows": payload.get("registry_rows"),
        "quality": payload.get("quality", {}),
        "discovery": payload.get("discovery", {}),
        "updated_at": payload.get("updated_at"),
    }


def _polygon_token_list_snapshot(force_refresh: bool) -> dict[str, Any]:
    if not ENABLE_POLYGON_TOKEN_LIST_DISCOVERY:
        return {"enabled": False}
    from .polygon_token_list import fetch_polygon_pos_candidates

    candidates, stats = fetch_polygon_pos_candidates(
        known_addresses=rpc_layer.TOKEN_ADDRESSES.values(),
        known_symbols=rpc_layer.TOKEN_ADDRESSES.keys(),
        force_refresh=force_refresh,
    )
    rows = [
        {
            "symbol": candidate.symbol,
            "address": candidate.address,
            "decimals": candidate.decimals,
            "source_file": candidate.source_file,
            "origin_symbol": candidate.origin_symbol,
        }
        for candidate in candidates
    ]
    return {
        "enabled": True,
        "stats": stats,
        "returned": len(rows),
        "sample": rows[:20],
        "candidate_digest": stable_digest(rows),
    }


def _dynamic_pool_snapshot() -> dict[str, Any]:
    file_state = _file_snapshot(DYNAMIC_POOLS_JSON_PATH)
    if not ENABLE_DYNAMIC_POOL_REGISTRY:
        return {"enabled": False, "file": file_state}
    from .external_pool_registry import load_dynamic_pool_registry

    token_addresses = dict(rpc_layer.TOKEN_ADDRESSES)
    address_to_symbol = dict(rpc_layer.ADDRESS_TO_SYMBOL)
    known_addresses = {
        str(meta.get("address", "")).lower()
        for meta in rpc_layer.DEEP_POOL_REGISTRY.values()
        if meta.get("address")
    }
    imported = load_dynamic_pool_registry(
        DYNAMIC_POOLS_JSON_PATH,
        address_to_symbol=address_to_symbol,
        token_addresses=token_addresses,
        known_pool_addresses=known_addresses,
        max_pools=DYNAMIC_POOL_REGISTRY_MAX_POOLS,
    )
    return {
        "enabled": True,
        "file": file_state,
        "stats": imported.stats,
        "registry_digest": stable_digest({
            pool_id: {
                "protocol": meta.get("protocol"),
                "tokens": list(meta.get("tokens") or [meta.get("token0"), meta.get("token1")]),
                "address": meta.get("address"),
                "fee_bps": str(meta.get("fee_bps", "")),
            }
            for pool_id, meta in imported.registry.items()
        }),
    }


def _curve_pool_snapshot() -> dict[str, Any]:
    if not ENABLE_CURVE_POOL_REGISTRY:
        return {"enabled": False}
    from .curve_pool_registry import load_curve_pool_registry

    token_addresses = dict(rpc_layer.TOKEN_ADDRESSES)
    token_decimals = dict(rpc_layer.TOKEN_DECIMALS)
    token_status = dict(rpc_layer.TOKEN_DISCOVERY_STATUS)
    address_to_symbol = dict(rpc_layer.ADDRESS_TO_SYMBOL)
    known_addresses = {
        str(meta.get("address", "")).lower()
        for meta in rpc_layer.DEEP_POOL_REGISTRY.values()
        if meta.get("address")
    }
    imported = load_curve_pool_registry(
        api_base_url=CURVE_POOL_REGISTRY_API_BASE_URL,
        families=CURVE_POOL_REGISTRY_FAMILIES,
        address_to_symbol=address_to_symbol,
        token_addresses=token_addresses,
        token_decimals=token_decimals,
        token_discovery_status=token_status,
        known_pool_addresses=known_addresses,
        max_pools=CURVE_POOL_REGISTRY_MAX_POOLS,
        min_usd_tvl=CURVE_POOL_REGISTRY_MIN_USD_TVL,
    )
    return {
        "enabled": True,
        "stats": imported.stats,
        "registry_digest": stable_digest({
            pool_id: {
                "tokens": list(meta.get("tokens") or []),
                "address": meta.get("address"),
                "tvl_usd": str(meta.get("tvl_usd", "")),
                "pool_family": meta.get("pool_family"),
            }
            for pool_id, meta in imported.registry.items()
        }),
    }


def _subgraph_snapshot() -> dict[str, Any]:
    if not ENABLE_SUBGRAPH_POOL_INTEL:
        return {"enabled": False}
    from .subgraph_intel import discover_subgraph_v3_candidates

    candidates, stats = discover_subgraph_v3_candidates()
    rows = [
        {
            "source": candidate.source,
            "protocol": candidate.protocol,
            "address": candidate.address,
            "token0": candidate.token0_symbol,
            "token1": candidate.token1_symbol,
            "fee_tier": candidate.fee_tier,
            "liquidity_usd": str(candidate.liquidity_usd),
            "volume_usd": str(candidate.volume_usd),
        }
        for candidate in candidates
    ]
    return {
        "enabled": True,
        "stats": stats,
        "candidate_digest": stable_digest(rows),
        "sample": rows[:20],
    }


def collect_protocol_update_snapshot(*, force_refresh: bool = True) -> dict[str, Any]:
    deployments = _deployment_snapshot()
    sources = {
        "deployment_catalog": {
            "enabled": True,
            "count": len(deployments),
            "items": deployments,
        },
        "polygon_token_list": _polygon_token_list_snapshot(force_refresh=force_refresh),
        "dynamic_pool_registry": _dynamic_pool_snapshot(),
        "curve_pool_registry": _curve_pool_snapshot(),
        "subgraph_pool_intel": _subgraph_snapshot(),
    }
    config_limits = {
        "enable_factory_pool_discovery": ENABLE_FACTORY_POOL_DISCOVERY,
        "discovery_max_token_pairs": DISCOVERY_MAX_TOKEN_PAIRS,
        "discovery_max_promoted_pools": DISCOVERY_MAX_PROMOTED_POOLS,
        "polygon_token_list_max_candidates": POLYGON_TOKEN_LIST_MAX_CANDIDATES,
        "polygon_token_list_bases": POLYGON_TOKEN_LIST_BASES,
        "dynamic_pool_registry_max_pools": DYNAMIC_POOL_REGISTRY_MAX_POOLS,
        "curve_pool_registry_max_pools": CURVE_POOL_REGISTRY_MAX_POOLS,
        "curve_pool_registry_families": CURVE_POOL_REGISTRY_FAMILIES,
        "curve_pool_registry_min_usd_tvl": str(CURVE_POOL_REGISTRY_MIN_USD_TVL),
        "subgraph_pool_intel_limit": SUBGRAPH_POOL_INTEL_LIMIT,
    }
    source_fingerprints = {
        name: stable_digest(payload)
        for name, payload in sources.items()
    }
    return {
        "ok": True,
        "mode": "read_only_no_broadcast",
        "chain_id": CHAIN_ID,
        "updated_at": int(time.time()),
        "config_limits": config_limits,
        "source_fingerprints": source_fingerprints,
        "sources": sources,
        "latest_pool_scan": _latest_pool_scan_summary(),
    }


def diff_snapshots(current: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    previous = previous or {}
    current_fp = dict(current.get("source_fingerprints") or {})
    previous_fp = dict(previous.get("source_fingerprints") or {})
    changed = []
    unchanged = []
    for name, digest in sorted(current_fp.items()):
        old = previous_fp.get(name)
        if old == digest:
            unchanged.append(name)
        else:
            changed.append({
                "source": name,
                "previous": old or "",
                "current": digest,
                "change_type": "new" if not old else "changed",
            })
    removed = [
        {"source": name, "previous": digest}
        for name, digest in sorted(previous_fp.items())
        if name not in current_fp
    ]
    return {
        "has_previous": bool(previous_fp),
        "changed_sources": changed,
        "removed_sources": removed,
        "unchanged_sources": unchanged,
        "changed_count": len(changed) + len(removed),
    }


def recommended_actions(snapshot: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    sources = snapshot.get("sources", {})
    for name, payload in sources.items():
        stats = payload.get("stats", {}) if isinstance(payload, dict) else {}
        errors = stats.get("errors") if isinstance(stats, dict) else None
        if errors:
            actions.append(f"{name}: source errors present; keep source as hints-only until resolved")
    scan = snapshot.get("latest_pool_scan", {})
    if scan.get("available") and int(scan.get("directional_quotes") or 0) <= 0:
        actions.append("latest_pool_scan: no directional quotes; inspect pool quality and quote hydration")
    quality = scan.get("quality", {}) if isinstance(scan, dict) else {}
    if quality.get("v2_pair_canonical", {}).get("v2_failed"):
        actions.append("v2_pair_canonical: failed V2 pools were filtered before route scoring")
    if not actions:
        actions.append("no immediate source action; continue read-only watch cycle")
    return actions


def write_report(snapshot: dict[str, Any], *, latest_path: Path = LATEST_REPORT, history_path: Path = HISTORY_REPORT) -> None:
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(json.dumps(_json_ready(snapshot), indent=2, sort_keys=True), encoding="utf-8")
    with history_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_json_ready(snapshot), sort_keys=True) + "\n")


def run_once(*, force_refresh: bool = True) -> dict[str, Any]:
    previous = _read_json(LATEST_REPORT) if LATEST_REPORT.exists() else {}
    snapshot = collect_protocol_update_snapshot(force_refresh=force_refresh)
    snapshot["diff"] = diff_snapshots(snapshot, previous)
    snapshot["recommended_actions"] = recommended_actions(snapshot)
    write_report(snapshot)
    return snapshot


def _int_env(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)) or default)
    except Exception:
        return default


def main() -> None:
    parser = argparse.ArgumentParser(description="Watch protocol metadata sources for discovery drift.")
    parser.add_argument("--once", action="store_true", help="Run one watch cycle and exit.")
    parser.add_argument("--no-force-refresh", action="store_true", help="Allow cached token-list payloads.")
    parser.add_argument("--interval-seconds", type=int, default=_int_env("PROTOCOL_WATCH_INTERVAL_SECONDS", 1800))
    args = parser.parse_args()

    force_refresh = not args.no_force_refresh
    while True:
        started = time.time()
        try:
            snapshot = run_once(force_refresh=force_refresh)
            print(
                "protocol_update_watch=OK "
                f"changed={snapshot['diff']['changed_count']} "
                f"actions={len(snapshot['recommended_actions'])} "
                f"path={LATEST_REPORT}",
                flush=True,
            )
        except Exception as exc:
            error_snapshot = {
                "ok": False,
                "mode": "read_only_no_broadcast",
                "chain_id": CHAIN_ID,
                "updated_at": int(time.time()),
                "error": f"{type(exc).__name__}: {exc}",
            }
            write_report(error_snapshot)
            print(f"protocol_update_watch=ERROR type={type(exc).__name__} detail={exc}", flush=True)
        if args.once:
            return
        elapsed = time.time() - started
        time.sleep(max(5, int(args.interval_seconds - elapsed)))


if __name__ == "__main__":
    main()
