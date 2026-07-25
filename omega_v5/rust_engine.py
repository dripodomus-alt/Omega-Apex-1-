#!/usr/bin/env python3
# ==============================================================================
# rust_engine.py -- mandatory bridge to the Omega Rust graph engine.
# ==============================================================================

from __future__ import annotations

import json
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

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
            raise RuntimeError(f"mandatory Rust engine malformed cycle index={idx} path_edge_length_mismatch")
        for edge_idx, edge in enumerate(edges_out):
            if edge.get("token_in") != path[edge_idx] or edge.get("token_out") != path[edge_idx + 1]:
                raise RuntimeError(
                    "mandatory Rust engine malformed cycle "
                    f"index={idx} edge={edge_idx} expected={path[edge_idx]}->{path[edge_idx + 1]} "
                    f"actual={edge.get('token_in')}->{edge.get('token_out')}"
                )
    return opportunities


def rust_pre_rank_routes(
    token_paths: list[tuple[str, ...]],
    rates: dict,
    pools: dict[str, dict],
    *,
    principal_usd: Decimal,
    max_quote_options_per_pair: int = 0,
    timeout_seconds: int = 60,
) -> list[dict]:
    """
    Offloads the combinatorial pre-ranking to the Rust engine.

    This function serializes the graph and route-finding parameters, then
    invokes the Rust binary with the `pre-rank` command. The Rust engine
    is responsible for the CPU-heavy combinatorial search and initial filtering.

    If the Rust engine is not implemented for this task or fails, this function
    will fail closed by returning an empty list, allowing the Python-based
    stager to proceed as a fallback.
    """
    binary = assert_rust_engine_ready()
    input_data = {
        "token_paths": token_paths,
        "rates": {f"{k[0]},{k[1]}": v for k, v in rates.items()},
        "pools": pools,
        "principal_usd": str(principal_usd),
        "max_quote_options_per_pair": max_quote_options_per_pair,
    }
    try:
        proc = subprocess.run(
            [str(binary), "pre-rank"],
            input=json.dumps(input_data, default=str),
            text=True, capture_output=True, timeout=timeout_seconds, check=True,
        )
        return json.loads(proc.stdout).get("candidates", [])
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        # Fail closed if the Rust pre-ranker isn't implemented or fails.
        return []


def rust_find_and_rank_opportunities(
    pools: dict[str, dict],
    prices: dict[str, str],
    *,
    principal_usd: Decimal,
    flash_source: str,
    stager_max_token_paths: int,
    stager_max_pre_ranked: int,
    stager_max_quote_options_per_pair: int,
    timeout_seconds: int = 60,
) -> tuple[list[dict], dict]:
    """
    Offloads the entire discovery-to-ranking pipeline to the Rust engine.
    This single call replaces multiple Python steps for maximum performance.
    """
    binary = assert_rust_engine_ready()
    input_data = {
        "pools": pools,
        "prices": prices,
        "principal_usd": str(principal_usd),
        "flash_source": flash_source,
        "stager_max_token_paths": stager_max_token_paths,
        "stager_max_pre_ranked": stager_max_pre_ranked,
        "stager_max_quote_options_per_pair": stager_max_quote_options_per_pair,
    }
    try:
        proc = subprocess.run(
            [str(binary), "find-and-rank"],
            input=json.dumps(input_data, default=str),
            text=True, capture_output=True, timeout=timeout_seconds, check=True,
        )
        payload = json.loads(proc.stdout)
        ranked = payload.get("ranked_opportunities", [])
        report = payload.get("discovery_report", {})
        return ranked, report
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as e:
        error_report = {"error": f"Rust engine 'find-and-rank' failed: {type(e).__name__}", "detail": str(e)}
        return [], error_report
