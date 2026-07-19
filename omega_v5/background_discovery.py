#!/usr/bin/env python3
# ==============================================================================
# background_discovery.py -- unbounded read-only discovery/surplus route loop.
#
# This daemon runs outside the main execution cycle so broader discovery does
# not add latency to the foreground scanner/executor loop.
# ==============================================================================

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from .paths import output_path


LATEST_REPORT = output_path("background_discovery_latest.json")
HISTORY_REPORT = output_path("background_discovery_history.jsonl")


UNBOUNDED_DEFAULTS = {
    "DISCOVERY_MAX_TOKEN_PAIRS": "0",
    "DISCOVERY_MAX_PROMOTED_POOLS": "0",
    "DYNAMIC_POOL_REGISTRY_MAX_POOLS": "0",
    "CURVE_POOL_REGISTRY_MAX_POOLS": "0",
    "POLYGON_TOKEN_LIST_MAX_CANDIDATES": "0",
    "POLYGON_TOKEN_LIST_BASES": "USDC.e,WETH,WPOL,WBTC,USDT,DAI,USDC,LINK,AAVE,CRV,BAL,UNI,SUSHI,QUICK",
    "SUBGRAPH_POOL_INTEL_LIMIT": "1000",
    "DISCOVERY_PAIR_WINDOW_SIZE": "640",
}


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def apply_background_discovery_defaults() -> dict[str, str]:
    applied: dict[str, str] = {}
    if os.environ.get("BACKGROUND_DISCOVERY_UNBOUNDED", "true").strip().lower() not in {"1", "true", "yes", "on"}:
        return applied
    for key, value in UNBOUNDED_DEFAULTS.items():
        if not os.environ.get(key):
            os.environ[key] = value
            applied[key] = value
    return applied


def _load_latest() -> dict[str, Any]:
    if not LATEST_REPORT.exists():
        return {}
    try:
        return json.loads(LATEST_REPORT.read_text(encoding="utf-8"))
    except Exception:
        return {}


def apply_pair_window_cursor() -> int:
    window_size = int(os.environ.get("DISCOVERY_PAIR_WINDOW_SIZE", "0") or "0")
    if window_size <= 0:
        os.environ.pop("DISCOVERY_PAIR_WINDOW_OFFSET", None)
        return 0
    current = _load_latest()
    offset = int(current.get("next_pair_window_offset") or os.environ.get("DISCOVERY_PAIR_WINDOW_OFFSET", "0") or "0")
    os.environ["DISCOVERY_PAIR_WINDOW_OFFSET"] = str(max(0, offset))
    return max(0, offset)


def _summary_from_route_surface(report: dict[str, Any]) -> dict[str, Any]:
    surface = report.get("opportunity_route_surface", {})
    assets = report.get("discovered_assets", {})
    pools = report.get("asset_pools", {})
    return {
        "block": report.get("block"),
        "pool_asset_count": assets.get("pool_asset_count"),
        "mid_token_asset_count": assets.get("mid_token_asset_count"),
        "loaded_rankable_pools": pools.get("loaded_rankable_pools"),
        "protocol_counts": pools.get("protocol_counts", {}),
        "rate_pairs": surface.get("rate_pairs"),
        "directional_quotes": surface.get("directional_quotes"),
        "possible": surface.get("possible", {}),
        "raw_positive_two_leg": surface.get("raw_positive_two_leg"),
        "raw_positive_cycles_all": surface.get("raw_positive_cycles_all"),
        "raw_positive_cycles_execution_candidates": surface.get("raw_positive_cycles_execution_candidates"),
        "net_gate_passed": surface.get("net_gate_passed", {}),
        "calldata_success_surface": report.get("calldata_success_surface", {}),
    }


def write_report(payload: dict[str, Any]) -> None:
    LATEST_REPORT.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_REPORT.parent.mkdir(parents=True, exist_ok=True)
    LATEST_REPORT.write_text(json.dumps(_json_ready(payload), indent=2, sort_keys=True), encoding="utf-8")
    with HISTORY_REPORT.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_json_ready(payload), sort_keys=True) + "\n")


def run_once(*, top: int = 50, calldata_probe: int = 10, rpc_url: str = "") -> dict[str, Any]:
    applied_defaults = apply_background_discovery_defaults()
    pair_window_offset = apply_pair_window_cursor()
    pair_window_size = int(os.environ.get("DISCOVERY_PAIR_WINDOW_SIZE", "0") or "0")

    # Import after env defaults so config module sees the unbounded profile.
    from .route_surface_report import REPORT_PATH as ROUTE_SURFACE_REPORT, build_route_surface_report

    started = time.time()
    route_report = build_route_surface_report(rpc_url=rpc_url, top=top, calldata_probe=calldata_probe)
    payload = {
        "ok": True,
        "mode": "read_only_no_broadcast",
        "updated_at": int(time.time()),
        "elapsed_seconds": round(time.time() - started, 3),
        "unbounded_defaults_applied": applied_defaults,
        "pair_window_offset": pair_window_offset,
        "pair_window_size": pair_window_size,
        "next_pair_window_offset": pair_window_offset + pair_window_size if pair_window_size > 0 else 0,
        "effective_discovery_env": {
            key: os.environ.get(key, "")
            for key in UNBOUNDED_DEFAULTS
        },
        "route_surface_artifact": str(ROUTE_SURFACE_REPORT),
        "summary": _summary_from_route_surface(route_report),
        "revert_risk_policy": route_report.get("accuracy_and_revert_risk_controls", {}),
    }
    write_report(payload)
    return payload


def _int_env(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)) or default)
    except Exception:
        return default


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the unbounded background discovery/surplus route loop.")
    parser.add_argument("--once", action="store_true", help="Run one discovery cycle and exit.")
    parser.add_argument("--interval-seconds", type=int, default=_int_env("BACKGROUND_DISCOVERY_INTERVAL_SECONDS", 900))
    parser.add_argument("--top", type=int, default=_int_env("BACKGROUND_DISCOVERY_TOP", 50))
    parser.add_argument("--calldata-probe", type=int, default=_int_env("BACKGROUND_DISCOVERY_CALLDATA_PROBE", 10))
    parser.add_argument("--rpc-url", default=os.environ.get("BACKGROUND_DISCOVERY_RPC_URL", ""))
    args = parser.parse_args()

    while True:
        started = time.time()
        try:
            payload = run_once(
                top=max(1, args.top),
                calldata_probe=max(0, args.calldata_probe),
                rpc_url=args.rpc_url,
            )
            summary = payload.get("summary", {})
            print(
                "background_discovery=OK "
                f"pools={summary.get('loaded_rankable_pools')} "
                f"quotes={summary.get('directional_quotes')} "
                f"raw_two_leg={summary.get('raw_positive_two_leg')} "
                f"raw_cycles_exec={summary.get('raw_positive_cycles_execution_candidates')} "
                f"net_passed={summary.get('net_gate_passed', {}).get('total')} "
                f"path={LATEST_REPORT}",
                flush=True,
            )
        except Exception as exc:
            payload = {
                "ok": False,
                "mode": "read_only_no_broadcast",
                "updated_at": int(time.time()),
                "error": f"{type(exc).__name__}: {exc}",
            }
            write_report(payload)
            print(f"background_discovery=ERROR type={type(exc).__name__} detail={exc}", flush=True)

        if args.once:
            return
        elapsed = time.time() - started
        time.sleep(max(5, int(args.interval_seconds - elapsed)))


if __name__ == "__main__":
    main()
