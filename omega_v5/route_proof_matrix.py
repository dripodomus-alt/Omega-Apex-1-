#!/usr/bin/env python3
# ==============================================================================
# route_proof_matrix.py -- live route proof profiles for coverage/precision audits.
#
# Read-only runner: hydrates live pools, builds directional quote edges, stages
# 2/3/4-hop routes, and attaches route-level metadata/state/equation proofs.
# It never signs or broadcasts.
# ==============================================================================

from __future__ import annotations

import argparse
import itertools
import json
import logging
import os
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass, is_dataclass
from decimal import Decimal
from typing import Any, Optional
from web3 import Web3
from . import rpc_layer
from .arbitrage import ArbitrageGraphEngine
from .config import (
    CHAIN_ID, HTTP_URL, MAX_FLASH_PRINCIPAL_USD, MAX_ROUTE_IMPACT,
    FLASH_ROUTE_TVL_FRACTIONS,
)
from .executable_quotes import quote_route_for_executor
from .execution import build_tx_payload, simulate_tx_payload
from .flash_loan import FlashSource, evaluate_profitability
from .oracle_layer import TOKEN_USD_SOURCE, refresh_token_prices, token_price_usd
from .paths import output_path
from .pipeline_validation import validate_calldata_integrity, validate_usdc_value_correlation
from .pricing import mul_div
from .pool_quality import filter_rankable_pools
from .route_execution_stager import SUPPORTED_HOPS, _json_ready, enumerate_closed_token_paths
from .transport_lanes import simulation_from_address, web3_for_lane, LANE_EXACT_C1_ETH_CALL


LATEST_PROOF_REPORT = output_path("route_proof_matrix_latest.json")
HISTORY_PROOF_REPORT = output_path("route_proof_matrix_history.jsonl")
LATEST_PROFILE_REPORT = output_path("route_profile_settings_latest.json")
DEFAULT_MAX_OPTION_COMBINATIONS = 200_000
logger = logging.getLogger("omega.proof_matrix")


@dataclass(frozen=True)
class ProofProfile:
    name: str
    rank_fast_to_slow: int
    intent: str
    principal_usd: Decimal
    hops: tuple[int, ...]
    max_pools: int
    stage_limit: int
    max_quote_options_per_pair: int
    max_token_paths: int
    max_pre_ranked: int
    slippage_bps: Decimal

    def __post_init__(self) -> None:
        principal = Decimal(str(self.principal_usd))
        max_principal = Decimal(str(MAX_FLASH_PRINCIPAL_USD))
        slippage = Decimal(str(self.slippage_bps))
        hops = tuple(int(hop) for hop in self.hops)

        if principal <= 0:
            raise ValueError(f"Profile {self.name!r} principal_usd must be positive; got {principal}")
        if principal > max_principal:
            raise ValueError(
                f"Profile {self.name!r} principal {principal} exceeds max {max_principal}"
            )
        if slippage < 0 or slippage > Decimal("1000"):
            raise ValueError(
                f"Profile {self.name!r} slippage_bps {slippage} out of bounds (0..1000)"
            )
        if not hops:
            raise ValueError(f"Profile {self.name!r} must declare at least one hop")

        unsupported = tuple(hop for hop in hops if hop not in SUPPORTED_HOPS)
        if unsupported:
            raise ValueError(
                f"Profile {self.name!r} has unsupported hops {unsupported}; supported={SUPPORTED_HOPS}"
            )

        object.__setattr__(self, "principal_usd", principal)
        object.__setattr__(self, "slippage_bps", slippage)
        object.__setattr__(self, "hops", hops)

    def to_row(self) -> dict[str, Any]:
        return _json_ready({
            "name": self.name,
            "rank_fast_to_slow": self.rank_fast_to_slow,
            "intent": self.intent,
            "principal_usd": self.principal_usd,
            "hops": self.hops,
            "max_pools": self.max_pools,
            "stage_limit": self.stage_limit,
            "max_quote_options_per_pair": self.max_quote_options_per_pair,
            "max_token_paths": self.max_token_paths,
            "max_pre_ranked": self.max_pre_ranked,
            "slippage_bps": self.slippage_bps,
            "speed_coverage_precision_tradeoff": _profile_tradeoff(self),
        })


PROFILES: tuple[ProofProfile, ...] = (
    ProofProfile(
        name="fastest_low_latency",
        rank_fast_to_slow=1,
        intent="minimum wall-clock proof with real metadata and exact route quotes",
        principal_usd=Decimal("1000"),
        hops=(2,),
        max_pools=12,
        stage_limit=8,
        max_quote_options_per_pair=2,
        max_token_paths=250,
        max_pre_ranked=32,
        slippage_bps=Decimal("5"),
    ),
    ProofProfile(
        name="balanced_coverage",
        rank_fast_to_slow=2,
        intent="broader two/three-hop coverage while keeping live proof runtime bounded",
        principal_usd=Decimal("5000"),
        hops=(2, 3),
        max_pools=40,
        stage_limit=25,
        max_quote_options_per_pair=4,
        max_token_paths=1500,
        max_pre_ranked=150,
        slippage_bps=Decimal("10"),
    ),
    ProofProfile(
        name="maximum_dynamics",
        rank_fast_to_slow=3,
        intent="full configured discovery dynamics across all supported hop depths",
        principal_usd=Decimal("10000"),
        hops=SUPPORTED_HOPS,
        max_pools=0,
        stage_limit=100,
        max_quote_options_per_pair=0,
        max_token_paths=0,
        max_pre_ranked=500,
        slippage_bps=Decimal("15"),
    ),
    ProofProfile(
        name="maximum_precision_slowest",
        rank_fast_to_slow=4,
        intent="slowest profile: no quote-option cap, no path cap, stage every raw-positive route returned",
        principal_usd=Decimal("10000"),
        hops=SUPPORTED_HOPS,
        max_pools=0,
        stage_limit=0,
        max_quote_options_per_pair=0,
        max_token_paths=0,
        max_pre_ranked=0,
        slippage_bps=Decimal("20"),
    ),
)


PREFERRED_PROOF_POOL_IDS = (
    "QS_WETH_USDC_e",
    "V3_USDC_e_WETH_500",
    "V3_USDC_e_WETH_3000",
    "V3_USDC_e_WETH_100",
    "ALG_USDC_e_WETH",
    "QS_USDC_WETH",
    "V3_USDC_WETH_500",
    "QS_WPOL_USDC_e",
    "V3_WPOL_USDC_e_500",
    "QS_WPOL_WETH",
    "V3_WBTC_WETH_500",
    "QS_WBTC_WETH",
)


def _profile_tradeoff(profile: ProofProfile) -> dict[str, str]:
    pool_scope = "all configured live pools" if profile.max_pools <= 0 else f"first {profile.max_pools} prioritized pools"
    quote_scope = "all quote edges" if profile.max_quote_options_per_pair <= 0 else f"top {profile.max_quote_options_per_pair} quote edges per pair"
    path_scope = "all closed token paths" if profile.max_token_paths <= 0 else f"first {profile.max_token_paths} closed token paths"
    stage_scope = "all raw-positive staged routes" if profile.stage_limit <= 0 else f"top {profile.stage_limit} staged routes"
    return {
        "pool_scope": pool_scope,
        "quote_scope": quote_scope,
        "path_scope": path_scope,
        "stage_scope": stage_scope,
        "precision_note": "precision increases as caps move to zero, because zero means uncapped in this runner",
    }


def profile_settings_report() -> dict[str, Any]:
    return {
        "schema_version": "omega_v5.route_profile_settings.v1",
        "ordering": "fastest_lowest_latency_to_slowest_maximum_precision",
        "config_semantics": {
            "max_pools": "0 = load every configured pool; positive values load that many prioritized pools",
            "stage_limit": "0 = stage every pre-ranked raw-positive route; positive values cap staged rows",
            "max_quote_options_per_pair": "0 = use every quote edge per token pair",
            "max_token_paths": "0 = enumerate every closed token path for selected hop depths",
            "max_pre_ranked": "0 = keep every raw-positive pre-ranked route",
            "slippage_bps": "higher value is more conservative for net execution proof",
        },
        "profiles": [profile.to_row() for profile in sorted(PROFILES, key=lambda item: item.rank_fast_to_slow)],
    }


def _select_profile(name: str) -> ProofProfile:
    for profile in PROFILES:
        if profile.name == name:
            return profile
    valid = ", ".join(profile.name for profile in PROFILES)
    raise ValueError(f"unknown profile {name!r}; valid profiles: {valid}")


def _prioritized_registry(max_pools: int) -> dict[str, dict]:
    registry = rpc_layer.DEEP_POOL_REGISTRY
    if max_pools <= 0:
        return dict(registry)
    selected: dict[str, dict] = {}
    for pool_id in PREFERRED_PROOF_POOL_IDS:
        if pool_id in registry and len(selected) < max_pools:
            selected[pool_id] = registry[pool_id]
    for pool_id, meta in registry.items():
        if len(selected) >= max_pools:
            break
        selected.setdefault(pool_id, meta)
    return selected


def _load_profile_pools(profile: ProofProfile) -> tuple[dict[str, dict], dict[str, Any]]:
    """Load only the selected profile registry without triggering discovery expansion."""
    registry = _prioritized_registry(profile.max_pools)
    loaded: dict[str, dict] = {}
    failed: list[str] = []
    started = time.time()
    for pool_id, meta in registry.items():
        state = rpc_layer.load_live_pool_state(pool_id, meta)
        if state:
            loaded[pool_id] = state
        else:
            failed.append(pool_id)
    filtered, quality_summary = filter_rankable_pools(loaded)
    stats = {
        "registry_selected": len(registry),
        "loaded_live": len(loaded),
        "load_failed": len(failed),
        "failed_pool_ids": failed[:50],
        "rankable_after_quality_filter": len(filtered),
        "quality_summary": quality_summary,
        "direct_hydration": True,
        "discovery_expansion": False,
        "elapsed_seconds": Decimal(str(round(time.time() - started, 3))),
    }
    return filtered, stats


def _pool_metadata_proof(pool_id: str, pool: dict[str, Any]) -> dict[str, Any]:
    meta = dict(pool.get("_meta") or {})
    tokens = list(pool.get("tokens") or [])
    addresses = list(meta.get("onchain_addresses") or pool.get("token_addresses") or [])
    decimals = list(meta.get("onchain_decimals") or [])
    missing: list[str] = []
    if not pool.get("address"):
        missing.append("pool_address")
    if not tokens:
        missing.append("tokens")
    if len(addresses) < len(tokens):
        missing.append("onchain_addresses")
    if len(decimals) < len(tokens) or any(item is None for item in decimals):
        missing.append("onchain_decimals")
    if meta.get("composition_mismatch"):
        missing.append("composition_mismatch")

    audit_statuses = {}
    for key, value in meta.items():
        if key.endswith("_audit") and isinstance(value, dict):
            audit_statuses[key] = value.get("status", "unknown")

    return {
        "pool_id": pool_id,
        "protocol": pool.get("protocol", ""),
        "pool_address": pool.get("address", ""),
        "tokens": tokens,
        "onchain_addresses": addresses,
        "onchain_decimals": decimals,
        "registered_tokens": meta.get("registered_tokens", []),
        "audit_statuses": audit_statuses,
        "metadata_complete": not missing,
        "missing_or_reject_reasons": missing,
    }


def _live_state_summary(pool: dict[str, Any]) -> dict[str, Any]:
    proto = str(pool.get("protocol") or "")
    summary = {
        "protocol": proto,
        "address": pool.get("address", ""),
        "liquidity_key": pool.get("liquidity_key", pool.get("pool_id", "")),
        "route_class": pool.get("route_class", ""),
    }
    if proto == "UniswapV2":
        reserves = list(pool.get("reserves") or [])
        summary.update({
            "state_fields": ["reserves"],
            "reserve_count": len(reserves),
            "positive_reserves": all(Decimal(str(item)) > 0 for item in reserves),
        })
    elif proto in {"UniswapV3", "QuickSwapV3", "Algebra"}:
        summary.update({
            "state_fields": ["sqrtPriceX96", "liquidity", "fee_bps"],
            "sqrtPriceX96_positive": Decimal(str(pool.get("sqrtPriceX96") or "0")) > 0,
            "liquidity_positive": Decimal(str(pool.get("liquidity") or "0")) > 0,
            "fee_bps": str(pool.get("fee_bps", "")),
            "fee_tier": str(pool.get("fee_tier", "")),
        })
    else:
        reserves = list(pool.get("reserves") or [])
        summary.update({
            "state_fields": ["reserves"],
            "reserve_count": len(reserves),
            "positive_reserves": all(Decimal(str(item)) > 0 for item in reserves) if reserves else False,
        })
    return summary


def _route_hop_trace(path: list[str], pool_sequence: list[str], pools: dict[str, dict], amount_in: Decimal, base_token_decimals: int = 18) -> list[dict[str, Any]]:
    amount = Decimal(amount_in)
    amount_raw = mul_div(int(amount * Decimal("1e18")), 1, 1, rounding=0) # Convert to raw units for tracing
    rows: list[dict[str, Any]] = []
    for idx, pool_id in enumerate(pool_sequence):
        token_in = path[idx]
        token_out = path[idx + 1]
        
        pool_data = pools.get(pool_id, {})
        protocol = pool_data.get("protocol", "")
        
        # Capture pre-state for invariant check
        reserves_before = list(pool_data.get("reserves", []))
        k_before = Decimal("0")
        if protocol == "UniswapV2" and len(reserves_before) == 2:
            k_before = reserves_before[0] * reserves_before[1]

        quote = quote_route_for_executor([token_in, token_out], [pool_id], pools, amount)
        
        # Simulate reserve mutation (simplified for tracing)
        reserves_after = list(reserves_before)
        if protocol == "UniswapV2" and len(reserves_after) == 2:
            # This is a simplified simulation, actual mutation depends on exact swap logic
            # For a real trace, we'd need to re-run the swap function.
            # Here, we just show the expected delta based on quote.
            token_in_idx = pool_data["tokens"].index(token_in)
            token_out_idx = pool_data["tokens"].index(token_out)
            
            reserves_after[token_in_idx] += amount
            reserves_after[token_out_idx] -= quote.amount_out

        k_after = Decimal("0")
        if protocol == "UniswapV2" and len(reserves_after) == 2:
            k_after = reserves_after[0] * reserves_after[1]

        invariant_check = "N/A"
        if protocol == "UniswapV2":
            # For V2, k_after should be >= k_before (after fees, k should not decrease)
            invariant_check = "PASS" if k_after >= k_before * Decimal("0.999") else "FAIL" # Allow small tolerance for fees

        rows.append({
            "hop": idx + 1,
            "pool_id": pool_id,
            "protocol": protocol,
            "token_in": token_in,
            "token_out": token_out,
            "amount_in": amount,
            "amount_in_raw": amount_raw,
            "amount_out": quote.amount_out,
            "amount_out_raw": quote.amount_out_raw,
            "clmm_quoted": quote.clmm_quoted,
            "clmm_unquoted": quote.clmm_unquoted,
            "proof": quote.hop_proofs,
            "positive": quote.amount_out > 0,
            "reserves_before": [str(r) for r in reserves_before],
            "reserves_after_simulated": [str(r) for r in reserves_after],
            "k_before": str(k_before),
            "k_after_simulated": str(k_after),
            "invariant_check": invariant_check,
        })
        amount = quote.amount_out
        amount_raw = quote.amount_out_raw
        if amount <= 0:
            break
    return rows


def _route_equation_proof(row: dict[str, Any], pools: dict[str, dict], calldata_hash: str = "", calldata_length: int = 0, calldata_round_trip_ok: bool = False) -> dict[str, Any]:
    path = [str(item) for item in row.get("path") or []]
    pool_sequence = [str(item) for item in row.get("pool_sequence") or []]
    x0 = Decimal(str(row.get("selected_base_amount_in") or "0"))
    base_token = str(row.get("base_token") or (path[0] if path else ""))
    base_price = Decimal(str(row.get("base_token_usd") or "0"))
    base_token_decimals = int(row.get("base_token_decimals") or row.get("decimals") or 18)
    trace = _route_hop_trace(path, pool_sequence, pools, x0) if x0 > 0 and path else []
    x_out = Decimal(str(trace[-1]["amount_out"])) if trace else Decimal("0")
    gross = x_out - x0
    gross_usd = x_out * base_price
    raw_delta_usd = gross * base_price
    staged_formula = row.get("net_formula") if isinstance(row.get("net_formula"), dict) else {}
    profit = evaluate_profitability(
        gross_usd,
        Decimal(str(row.get("selected_principal_usd") or "0")),
        hops=len(pool_sequence),
    )
    extra_slippage_buffer_usd = Decimal(str(staged_formula.get("extra_slippage_buffer_usd") or "0"))
    flashloan_fee_usd = Decimal(str(staged_formula.get("flashloan_fee_usd") or profit.flashloan.fee_usd))
    gas_cost_usd = Decimal(str(staged_formula.get("gas_cost_usd") or profit.gas_cost_usd))
    relay_cost_usd = Decimal(str(staged_formula.get("relay_or_private_submit_cost_usd") or profit.relay_tip_usd))
    risk_buffer_usd = Decimal(str(staged_formula.get("risk_buffer_usd") or profit.risk_buffer_usd))
    slippage_cost_usd = Decimal(str(staged_formula.get("slippage_cost_usd") or staged_formula.get("extra_slippage_buffer_usd") or "0"))
    builder_fee_usd = Decimal(str(staged_formula.get("builder_fee_usd") or staged_formula.get("builder_tip_usd") or "0"))
    expected_net = (
        raw_delta_usd
        - flashloan_fee_usd
        - gas_cost_usd
        - relay_cost_usd
        - risk_buffer_usd
        - extra_slippage_buffer_usd
    )
    reported_net = Decimal(str(row.get("net_gain_usd") or "0"))
    two_leg_prices: dict[str, Any] = {}
    if len(trace) == 2 and trace[0]["amount_out"] > 0:
        mid_units = Decimal(str(trace[0]["amount_out"]))
        buy_price_base_per_mid = x0 / mid_units
        sell_price_base_per_mid = Decimal(str(trace[1]["amount_out"])) / mid_units
        two_leg_prices = {
            "mid_token": path[1],
            "buy_price_base_per_mid": buy_price_base_per_mid,
            "sell_price_base_per_mid": sell_price_base_per_mid,
            "raw_spread_base_per_mid": sell_price_base_per_mid - buy_price_base_per_mid,
            "buy_lower_than_sell": buy_price_base_per_mid < sell_price_base_per_mid,
        }
    
    # Calldata integrity checks
    calldata_ok = validate_calldata_integrity(row.get("calldata", ""), row.get("opp_id", "unknown"), "proof_matrix")

    return {
        "canonical_equation": "xN = F_N(...F2(F1(x0))); net = xN_usd - x0_usd - flash - gas - relay - risk - slippage_buffer",
        "base_token": base_token,
        "base_token_usd": base_price,
        "base_token_decimals": base_token_decimals,
        "principal_usd": Decimal(str(row.get("selected_principal_usd") or "0")),
        "x0_base_amount_in": x0,
        "xN_base_amount_out": x_out,
        "gross_base_delta": gross,
        "gross_out_usd": gross_usd,
        "raw_delta_usd": raw_delta_usd,
        "net_gain_usd_recomputed": expected_net,
        "net_gain_usd_reported": reported_net,
        "net_identity_pass": abs(expected_net - reported_net) <= Decimal("0.00000001"), # High precision tolerance
        "gross_spread_bps": (profit.gross_amount_out / profit.flashloan.principal_usd - Decimal("1")) * Decimal("10000") if profit.flashloan.principal_usd > 0 else Decimal("0"),
        "post_math_spread_bps": ((getattr(profit, "gross_amount_out", Decimal("0")) - profit.flashloan.principal_usd) / profit.flashloan.principal_usd) * Decimal("10000") if profit.flashloan.principal_usd > 0 else Decimal("0"),
        "slippage_cost_usd": slippage_cost_usd,
        "flashloan_fee_usd": flashloan_fee_usd,
        "flashloan_fee_verified": getattr(profit.flashloan, "fee_verified", True),
        "flashloan_fee_source": getattr(profit.flashloan, "fee_source", "static_config"),
        "gas_cost_usd": gas_cost_usd,
        "gas_accounting": staged_formula.get("gas_accounting", getattr(profit, "gas_accounting", {}) or {}),
        "gas_payer": staged_formula.get("gas_payer", getattr(profit, "gas_payer", "user_wallet")),
        "builder_fee_usd": builder_fee_usd,
        "relay_or_private_submit_cost_usd": relay_cost_usd,
        "risk_buffer_usd": risk_buffer_usd,
        "total_costs_usd": flashloan_fee_usd + gas_cost_usd + relay_cost_usd + risk_buffer_usd + extra_slippage_buffer_usd,
        "calldata_hash": calldata_hash,
        "calldata_length": calldata_length,
        "calldata_round_trip_ok": calldata_round_trip_ok, # Placeholder for actual round-trip check
        "two_leg_price_proof": two_leg_prices,
        "hop_trace": trace,
    }


def _route_universal_conditions(row: dict[str, Any], pools: dict[str, dict], equation: dict[str, Any]) -> dict[str, Any]:
    path = [str(item) for item in row.get("path") or []]
    pool_sequence = [str(item) for item in row.get("pool_sequence") or []]
    metadata = [_pool_metadata_proof(pool_id, pools.get(pool_id, {})) for pool_id in pool_sequence]
    liquidity_keys = [str(pools.get(pool_id, {}).get("liquidity_key") or pool_id) for pool_id in pool_sequence]
    hop_trace = list(equation.get("hop_trace") or [])
    usdc_correlation_ok = validate_usdc_value_correlation(row, opportunity_id=row.get("opp_id", "unknown"), cycle_id="proof_matrix")
    checks = {
        "closed_route": bool(path) and path[0] == path[-1],
        "supported_hop_count": len(pool_sequence) in SUPPORTED_HOPS,
        "distinct_liquidity": len(set(liquidity_keys)) == len(liquidity_keys),
        "all_pools_loaded": all(pool_id in pools for pool_id in pool_sequence),
        "metadata_complete": all(item.get("metadata_complete") for item in metadata),
        "all_hops_positive": bool(hop_trace) and all(item.get("positive") for item in hop_trace),
        "clmm_execution_truth_proven": all(int(item.get("clmm_unquoted") or 0) == 0 for item in hop_trace),
        "net_identity_pass": bool(equation.get("net_identity_pass")),
        "usdc_value_correlation_normalized": usdc_correlation_ok,
        "no_sign_no_broadcast": True,
    }
    checks["route_proof_pass"] = all(checks.values())
    return {
        "checks": checks,
        "metadata": metadata,
        "live_state": [_live_state_summary(pools.get(pool_id, {})) for pool_id in pool_sequence],
    }


def _quote_options(entries: list[dict[str, Any]], max_options: int) -> list[dict[str, Any]]:
    return list(entries if max_options <= 0 else entries[:max_options])


def _option_space_estimate_for_path(
    path: tuple[str, ...],
    rates: dict[tuple[str, str], list[dict[str, Any]]],
    max_quote_options_per_pair: int,
) -> tuple[int, bool, list[int]]:
    """Estimates the number of quote combinations for a token path after option capping."""
    counts: list[int] = []
    for idx in range(len(path) - 1):
        entries = list(rates.get((path[idx], path[idx + 1]), []))
        options = _quote_options(entries, max_quote_options_per_pair)
        if not options:
            return 0, False, counts
        counts.append(len(options))

    combinations = 1
    for count in counts:
        combinations *= count
    return combinations, True, counts


def _exact_route_probe(
    path: tuple[str, ...],
    entries: tuple[dict[str, Any], ...],
    pools: dict[str, dict],
    profile: ProofProfile,
) -> dict[str, Any]:
    pool_sequence = [str(entry.get("pool_id") or "") for entry in entries]
    protocol_seq = [str(entry.get("protocol") or "") for entry in entries]
    liquidity_keys = [str(entry.get("liquidity_key") or entry.get("pool_id") or "") for entry in entries]
    base_token = path[0]
    try:
        base_price = token_price_usd(base_token)
    except Exception as exc:
        return {
            "status": "probe_rejected",
            "stage": "base_price_unavailable",
            "path": list(path),
            "pool_sequence": pool_sequence,
            "reason": f"{type(exc).__name__}: {exc}",
        }
    if base_price <= 0:
        return {
            "status": "probe_rejected",
            "stage": "base_price_invalid",
            "path": list(path),
            "pool_sequence": pool_sequence,
            "reason": f"non_positive_base_price:{base_token}",
        }

    selected_principal_usd = profile.principal_usd
    base_amount_in = selected_principal_usd / base_price
    route_quote = quote_route_for_executor(list(path), pool_sequence, pools, base_amount_in)
    gross_out_usd = route_quote.amount_out * base_price
    raw_delta_usd = gross_out_usd - selected_principal_usd
    extra_slippage_buffer_usd = max(Decimal("0"), gross_out_usd * profile.slippage_bps / Decimal("10000"))
    profitability = evaluate_profitability(
        gross_out_usd - extra_slippage_buffer_usd,
        selected_principal_usd,
        hops=len(pool_sequence),
        flash_source=FlashSource.BALANCER,
        asset=base_token,
    )
    net_formula = {
        "raw_delta_usd": raw_delta_usd,
        "flashloan_fee_usd": profitability.flashloan.fee_usd,
        "gas_cost_usd": profitability.gas_cost_usd,
        "relay_or_private_submit_cost_usd": profitability.relay_tip_usd,
        "risk_buffer_usd": profitability.risk_buffer_usd,
        "extra_slippage_buffer_usd": extra_slippage_buffer_usd,
        "net_gain_usd": profitability.net_profit_usd,
        "formula": (
            "net_gain_usd = raw_delta_usd - flashloan_fee_usd - gas_cost_usd "
            "- relay_or_private_submit_cost_usd - risk_buffer_usd - extra_slippage_buffer_usd"
        ),
    }
    row = {
        "status": "probe_net_positive" if raw_delta_usd > 0 else "probe_net_negative",
        "stage": "exact_probe_before_profit_gate",
        "path": list(path),
        "pool_sequence": pool_sequence,
        "protocol_seq": protocol_seq,
        "liquidity_keys": liquidity_keys,
        "duplicate_liquidity": len(set(liquidity_keys)) != len(liquidity_keys),
        "base_token": base_token,
        "base_token_usd": base_price,
        "selected_base_amount_in": base_amount_in,
        "selected_principal_usd": selected_principal_usd,
        "gross_base_amount_out": route_quote.amount_out,
        "gross_out_usd": gross_out_usd,
        "raw_delta_usd": raw_delta_usd,
        "net_gain_usd": profitability.net_profit_usd,
        "passes_profit_gate": profitability.passes_gate,
        "quote_detail": {
            "source": "exact_route_quote_for_executor",
            "clmm_quoted": route_quote.clmm_quoted,
            "clmm_unquoted": route_quote.clmm_unquoted,
            "hop_proofs": route_quote.hop_proofs,
        },
        "net_formula": net_formula,
        "submission_policy": "probe only; no signing, no broadcast",
    }
    equation = _route_equation_proof(row, pools)
    universal = _route_universal_conditions(row, pools, equation)
    row["route_proof"] = {
        "equation": _json_ready(equation),
        "universal_conditions": _json_ready(universal),
    }
    return _json_ready(row)


def _build_exact_route_probes( # This function is currently disabled in run_profile
    rates: dict,
    pools: dict[str, dict],
    profile: ProofProfile,
    *,
    limit: int = 50,
) -> dict[str, Any]:
    started = time.time()
    max_option_combinations = int(
        os.environ.get("OMEGA_PROOF_MAX_COMBINATIONS", str(DEFAULT_MAX_OPTION_COMBINATIONS)) or DEFAULT_MAX_OPTION_COMBINATIONS
    )
    rows: list[dict[str, Any]] = []
    reject_counts: Counter[str] = Counter()
    estimated_total_combinations = 0
    skipped_option_space_paths = 0
    paths = enumerate_closed_token_paths(
        rates,
        hops=profile.hops,
        max_token_paths=profile.max_token_paths,
    )
    for path in paths:
        estimated_combos, has_full_path, edge_option_counts = _option_space_estimate_for_path(
            path,
            rates,
            profile.max_quote_options_per_pair,
        )
        if not has_full_path:
            reject_counts["missing_directional_edge"] += 1
            continue
        estimated_total_combinations += estimated_combos
        if max_option_combinations > 0 and estimated_combos > max_option_combinations:
            skipped_option_space_paths += 1
            reject_counts["option_space_guard"] += 1
            logger.warning(
                "route_proof_matrix option-space guard skipped path=%s combos=%s limit=%s edge_option_counts=%s",
                path,
                estimated_combos,
                max_option_combinations,
                edge_option_counts,
            )
            continue

        option_sets = []
        for idx in range(len(path) - 1):
            options = _quote_options(
                list(rates.get((path[idx], path[idx + 1]), [])),
                profile.max_quote_options_per_pair,
            )
            if not options:
                reject_counts["missing_directional_edge"] += 1
                option_sets = []
                break
            option_sets.append(options)
        if not option_sets:
            continue
        for combo in itertools.product(*option_sets):
            if len(rows) >= limit:
                break
            pool_sequence = [str(entry.get("pool_id") or "") for entry in combo]
            if any(pool_id not in pools for pool_id in pool_sequence):
                reject_counts["missing_live_pool"] += 1
                continue
            rows.append(_exact_route_probe(path, tuple(combo), pools, profile))
        if len(rows) >= limit:
            break

    counts = Counter(str(row.get("status", "unknown")) for row in rows)
    proof_counts = Counter(
        "passed" if row.get("route_proof", {}).get("universal_conditions", {}).get("checks", {}).get("route_proof_pass") else "failed"
        for row in rows
    )
    return {
        "enabled": True,
        "purpose": "prove exact sequential quote, metadata, SPLS accounting, and rejection causes even when pre-rank has no raw-positive stage candidates",
        "attempted": len(rows),
        "limit": limit,
        "option_space": {
            "estimated_total_combinations": estimated_total_combinations,
            "max_combinations_per_path": max_option_combinations,
            "paths_skipped_by_guard": skipped_option_space_paths,
            "guard_env": "OMEGA_PROOF_MAX_COMBINATIONS",
        },
        "status_counts": dict(sorted(counts.items())),
        "route_proofs_passed": proof_counts.get("passed", 0),
        "route_proofs_failed": proof_counts.get("failed", 0),
        "reject_counts": dict(sorted(reject_counts.items())),
        "elapsed_seconds": Decimal(str(round(time.time() - started, 3))),
        "routes": rows,
    }


def simulate_and_diagnose(
    route: dict[str, Any],
    pools: dict[str, dict],
    *,
    w3_override: Optional[Web3] = None
) -> dict[str, Any]:
    """
    Builds calldata for a route, simulates it via eth_call, and returns a
    diagnostic proof.
    """
    w3 = w3_override or web3_for_lane(LANE_EXACT_C1_ETH_CALL)
    if w3 is None:
        return {"ok": False, "status": "rpc_unavailable", "detail": "web3_for_lane returned None"}

    # The route dict from the stager has the necessary fields for build_tx_payload
    try:
        # build_tx_payload needs a nonce, but it's not used for eth_call, so 0 is fine.
        tx_payload = build_tx_payload(route, pools, nonce=0)
    except Exception as e:
        return {
            "ok": False,
            "status": "payload_build_failed",
            "detail": f"{type(e).__name__}: {e}",
        }

    # The from_addr is sourced from the transport lane module to ensure consistency.
    from_addr = simulation_from_address()
    sim_ok, sim_detail = simulate_tx_payload(tx_payload, from_addr=from_addr, w3_override=w3)

    return {
        "ok": sim_ok,
        "status": "pass" if sim_ok else "fail",
        "detail": sim_detail,
        "from_address": from_addr,
        "to_address": tx_payload.get("to"),
        "calldata_bytes": len(tx_payload.get("data", "0x")) // 2 - 1,
        "selector": tx_payload.get("data", "0x")[:10],
    }


def _enrich_stage_report(stage_report: dict[str, Any], pools: dict[str, dict], profile: ProofProfile) -> dict[str, Any]:
    enriched_routes = []
    for row in stage_report.get("routes", []):
        route = dict(row)
        if row.get("selected_base_amount_in") and row.get("path") and row.get("pool_sequence"):
            equation = _route_equation_proof(row, pools, row.get("calldata_hash", ""), row.get("calldata_length", 0))
            universal = _route_universal_conditions(row, pools, equation)
            simulation = simulate_and_diagnose(row, pools)
            route["route_proof"] = {
                "equation": _json_ready(equation), # This will now include calldata details
                "universal_conditions": _json_ready(universal),
                "simulation_proof": _json_ready(simulation),
            }
        else:
            route["route_proof"] = {
                "equation": {},
                "universal_conditions": {
                    "checks": {"route_proof_pass": False},
                    "reason": row.get("reason", row.get("stage", "not_staged")),
                },
            }
        enriched_routes.append(route)

    stage_report = dict(stage_report)
    stage_report["routes"] = enriched_routes
    proof_counts = Counter(
        "passed" if route.get("route_proof", {}).get("universal_conditions", {}).get("checks", {}).get("route_proof_pass") else "failed"
        for route in enriched_routes
    )
    stage_report["proof"] = {
        "profile": profile.to_row(),
        "route_proofs_passed": proof_counts.get("passed", 0),
        "route_proofs_failed": proof_counts.get("failed", 0),
        "pool_metadata_rows": [_pool_metadata_proof(pool_id, pool) for pool_id, pool in pools.items()],
        "base_price_sources": dict(TOKEN_USD_SOURCE),
    }
    return stage_report


def _write_json(path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_ready(payload), indent=2, sort_keys=True), encoding="utf-8")


def write_profile_settings() -> dict[str, Any]:
    report = profile_settings_report()
    _write_json(LATEST_PROFILE_REPORT, report)
    return report


def write_proof_report(report: dict[str, Any]) -> None:
    _write_json(LATEST_PROOF_REPORT, report)
    HISTORY_PROOF_REPORT.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_PROOF_REPORT.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_json_ready(report), sort_keys=True) + "\n")


def run_profile(
    profile_name: str,
    *,
    rpc_url: str = "",
    flash_source: FlashSource = FlashSource.BALANCER,
) -> dict[str, Any]:
    profile = _select_profile(profile_name)
    started = time.time()
    os.environ.setdefault("OMEGA_RUNTIME_MODE", "dry_run")
    os.environ.setdefault("EXECUTION_MODE", "dry_run")
    os.environ.setdefault("LIVE_TRADING", "0")

    if not rpc_layer.connect(http_urls=[rpc_url or HTTP_URL], wss_url="", prefer_wss=False):
        raise RuntimeError("RPC connection failed")

    pools, pool_load_stats = _load_profile_pools(profile)
    prices = refresh_token_prices(force=True)

    # --- Unified Pipeline with compatibility fallback ---
    arb_engine = ArbitrageGraphEngine()
    sizing_params = {
        "min_principal_usd": str(profile.principal_usd),
        "max_principal_usd": str(MAX_FLASH_PRINCIPAL_USD),
        "tvl_fractions": [str(f) for f in FLASH_ROUTE_TVL_FRACTIONS],
        "max_impact_bps": int(MAX_ROUTE_IMPACT * 10000),
    }

    if hasattr(arb_engine, "find_and_rank_opportunities"):
        ranked_opps, discovery_report = arb_engine.find_and_rank_opportunities(
            sizing_params=sizing_params,
            flash_source=flash_source,
            stager_max_token_paths=profile.max_token_paths,
            stager_max_pre_ranked=profile.max_pre_ranked,
            max_quote_options_per_pair=profile.max_quote_options_per_pair,
        )
    else:
        ranked_opps = arb_engine.discover(chain_id=CHAIN_ID)
        discovery_report = {
            "engine_mode": "discover_fallback",
            "cycles_detected": len(ranked_opps),
            "directional_quotes": 0,
            "rate_pairs": 0,
            "stager_blueprints": len(ranked_opps),
            "sizing_params": sizing_params,
        }

    def _opp_to_row(opp: Any) -> dict[str, Any]:
        if isinstance(opp, dict):
            return dict(opp)
        if hasattr(opp, "as_dict"):
            try:
                return dict(opp.as_dict())
            except Exception:
                pass
        if is_dataclass(opp):
            return asdict(opp)
        if hasattr(opp, "__dict__"):
            return dict(vars(opp))
        return {"repr": repr(opp)}

    # Reconstruct a report compatible with the proof matrix's expectations
    staged_routes = [_opp_to_row(opp) for opp in ranked_opps[:profile.stage_limit or len(ranked_opps)]]
    stage_report = {
        "routes": staged_routes,
        "stage": {
            "attempted": discovery_report.get("cycles_detected", 0),
            "staged_for_executor_truth": len(staged_routes),
        },
        "quote_edges": {
            "directional_quote_edges": discovery_report.get("directional_quotes", 0),
            "rate_pairs": discovery_report.get("rate_pairs", 0),
        },
        "pre_rank": {
            "pre_ranked_returned": discovery_report.get("stager_blueprints", 0),
        },
        "pre_rank_diagnostic": discovery_report,
    }

    report = _enrich_stage_report(stage_report, pools, profile)
    report["exact_route_probes"] = {
        "enabled": False,
        "reason": "This has been superseded by the unified Rust engine's discovery process.",
        "discovery_report": discovery_report,
    }
    report.update({
        "schema_version": "omega_v5.route_proof_matrix.v1",
        "updated_at": int(time.time()),
        "elapsed_seconds_total": Decimal(str(round(time.time() - started, 3))),
        "mode": "read_only_no_sign_no_broadcast",
        "chain_id": CHAIN_ID,
        "block": rpc_layer.BLOCK,
        "runtime_safety": {
            "OMEGA_RUNTIME_MODE": os.environ.get("OMEGA_RUNTIME_MODE", ""),
            "EXECUTION_MODE": os.environ.get("EXECUTION_MODE", ""),
            "LIVE_TRADING": os.environ.get("LIVE_TRADING", ""),
            "signing": False,
            "broadcast": False,
        },
        "pool_load": pool_load_stats,
    })
    write_profile_settings()
    write_proof_report(report)
    return report


def _parse_profiles(raw: str) -> list[str]:
    names = [item.strip() for item in raw.split(",") if item.strip()]
    return names or ["fastest_low_latency"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run live read-only route proof matrix profiles.")
    parser.add_argument("--profiles", default=os.environ.get("ROUTE_PROOF_PROFILES", "fastest_low_latency"))
    parser.add_argument("--rpc-url", default=os.environ.get("ROUTE_PROOF_RPC_URL", ""))
    parser.add_argument("--settings-only", action="store_true", help="Only write profile settings artifact.")
    args = parser.parse_args()

    settings = write_profile_settings()
    if args.settings_only:
        print(f"route_profile_settings=OK profiles={len(settings['profiles'])} path={LATEST_PROFILE_REPORT}", flush=True)
        return

    reports = []
    for name in _parse_profiles(args.profiles):
        report = run_profile(name, rpc_url=args.rpc_url)
        reports.append(report)
        print(
            "route_proof_matrix=OK "
            f"profile={name} "
            f"block={report.get('block')} "
            f"edges={report.get('quote_edges', {}).get('directional_quote_edges')} "
            f"pre_ranked={report.get('pre_rank', {}).get('pre_ranked_returned')} "
            f"attempted={report.get('stage', {}).get('attempted')} "
            f"staged={report.get('stage', {}).get('staged_for_executor_truth')} "
            f"proof_pass={report.get('proof', {}).get('route_proofs_passed')} "
            f"path={LATEST_PROOF_REPORT}",
            flush=True,
        )

    if len(reports) > 1:
        aggregate = {
            "schema_version": "omega_v5.route_proof_matrix.aggregate.v1",
            "profiles": [report.get("proof", {}).get("profile", {}).get("name", "") for report in reports],
            "reports": reports,
        }
        write_proof_report(aggregate)


if __name__ == "__main__":
    main()
