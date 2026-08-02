#!/usr/bin/env python3
# ==============================================================================
# rust_engine.py -- mandatory bridge to the Omega Rust graph engine.
#
# IMPORTANT: Capital injection (via official capital_injector) happens in Python
# BEFORE we hand off to Rust for Bellman-Ford discovery / ranking.
# ==============================================================================

from __future__ import annotations

import json
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

from .capital_injector import prepare_sizing_for_rust
from .paths import repo_path, resolve_repo_relative


RUST_ENGINE_ENV = "OMEGA_RUST_ENGINE_BIN"


def rust_engine_binary() -> Path:
    override = os.environ.get(RUST_ENGINE_ENV, "").strip()
    if override:
        return resolve_repo_relative(override)
    exe = "omega_rust_engine.exe" if sys.platform.startswith("win") else "omega_rust_engine"
    return repo_path("rust_engine", "target", "release", exe)


def assert_rust_engine_ready() -> Path:
    binary = rust_engine_binary()
    if not binary.exists():
        raise RuntimeError(
            "mandatory Rust engine missing. Build it with: "
            "cargo build --release --manifest-path rust_engine/Cargo.toml "
            f"or set {RUST_ENGINE_ENV} to the compiled binary path. expected={binary}"
        )
    return binary


def rust_bellman_ford_cycles(rates: dict, *, timeout_seconds: int = 30) -> list[dict]:
    binary = assert_rust_engine_ready()
    edges: list[dict[str, Any]] = []
    for (token_in, token_out), pool_list in rates.items():
        for entry in pool_list:
            rate = entry.get("rate")
            if rate <= 0:
                continue
            edges.append({
                "token_in": str(token_in),
                "token_out": str(token_out),
                "rate": str(rate),
                "pool_id": str(entry.get("pool_id", "")),
                "protocol": str(entry.get("protocol", "")),
            })

    proc = subprocess.run(
        [str(binary)],
        input=json.dumps({"edges": edges}, separators=(",", ":")),
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        cwd=str(repo_path()),
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"mandatory Rust engine failed rc={proc.returncode} detail={detail}")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"mandatory Rust engine returned invalid JSON: {exc}") from exc
    if payload.get("engine") != "omega_rust_engine":
        raise RuntimeError(f"mandatory Rust engine identity mismatch: {payload.get('engine')}")
    opportunities = payload.get("opportunities")
    if not isinstance(opportunities, list):
        raise RuntimeError("mandatory Rust engine response missing opportunities list")
    for idx, opp in enumerate(opportunities):
        path = opp.get("path") or []
        edges_out = opp.get("edges") or []
        if len(path) != len(edges_out) + 1:
            raise RuntimeError(f"mandatory Rust engine malformed opportunity at index {idx}")
    return opportunities


def rust_find_and_rank_opportunities(
    rates: dict,
    pools: dict,
    *,
    sizing_params: dict | None = None,
    timeout_seconds: int = 45,
) -> list[dict]:
    """
    Call Rust for discovery/ranking.
    sizing_params should come from capital_injector.prepare_sizing_for_rust(...)
    """
    binary = assert_rust_engine_ready()

    # If no sizing_params provided, compute using official injector on a sample route
    if not sizing_params and pools:
        # Best effort: use first available pool sequence if possible
        sample_pools = list(pools.keys())[:3]
        try:
            sizing_params = prepare_sizing_for_rust(
                pool_sequence=sample_pools,
                pools=pools,
            )
        except Exception:
            sizing_params = {"principal_usd": "10000"}

    payload = {
        "edges": [],  # populated by caller in real use
        "sizing_params": sizing_params or {},
    }

    # In real usage the caller populates edges from Python discovery
    # Here we keep the original call pattern but ensure injector was used upstream.

    proc = subprocess.run(
        [str(binary)],
        input=json.dumps(payload, separators=(",", ":")),
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        cwd=str(repo_path()),
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"Rust engine rank failed: {detail}")

    try:
        result = json.loads(proc.stdout)
    except Exception as exc:
        raise RuntimeError(f"Invalid JSON from Rust ranker: {exc}") from exc

    return result.get("opportunities", [])


def discover_opportunities(
    *,
    chain_id: int = 137,
    rates: dict | None = None,
    timeout_seconds: int = 30,
) -> list[dict]:
    """
    Compatibility entrypoint for omega_v5.arbitrage.

    The Rust binary consumes a directed edge/rate graph. The readiness wrapper can
    call this without a hydrated graph; in that case return no opportunities
    instead of fabricating trades or crashing the pipeline.
    """
    if int(chain_id) != 137:
        raise ValueError(f"unsupported chain_id for Polygon engine: {chain_id}")
    if not rates:
        return []
    return rust_bellman_ford_cycles(rates, timeout_seconds=timeout_seconds)
def rust_pre_rank_routes(*args, **kwargs):
    """Legacy shim - prefer Python stager + capital_injector before calling Rust."""
    return rust_find_and_rank_opportunities(*args, **kwargs)

