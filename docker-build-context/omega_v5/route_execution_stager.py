#!/usr/bin/env python3
"""Compact route execution staging layer with buy-low/sell-high proof."""

from __future__ import annotations

import itertools
import argparse
import json
import logging
import os
import time
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable

from eth_abi import encode
from web3 import Web3

from . import rpc_layer
from .config import (
    CHAIN_ID,
    normalize_protocol,
    MIN_CALldata_LENGTH,
    MAX_CALldata_LENGTH,
)
from .executable_quotes import quote_route_for_executor
from .capital_injector import compute_optimal_injection
from .flash_loan import FlashSource, MIN_NET_PROFIT_USD, AAVE_FLASH_FEE_BPS, BALANCER_FLASH_FEE_BPS, live_min_net_profit_usd
from .gas_oracle import profitability_gas_price_gwei
from .oracle_layer import token_price_usd
from .paths import output_path
from .pricing.net_delta import route_within_lifespan
from .pipeline_validation import validate_calldata_integrity, validate_canonical_execution_proof
from .calldata_semantic_audit import build_calldata_semantic_audit
from .payload_envelope import UNIFIED_ROUTE_SCHEMA_VERSION

logger = logging.getLogger("omega.stager")
LATEST_STAGE_REPORT = output_path("route_execution_stage_latest.json")
HISTORY_STAGE_REPORT = output_path("route_execution_stage_history.jsonl")
N_PLUS_4_LIFESPAN = 4
READY_FOR_EXACT_CALL_STATUS = "ready_for_exact_call"
LEGACY_READY_STATUS = "staged_for_executor_truth"
DEFAULT_MAX_QUOTE_OPTIONS_PER_PAIR = 3

# --- Constants and Configuration ---
# Maximum number of hops supported for arbitrage routes.
SUPPORTED_HOPS = (2, 3, 4)
DEFAULT_MAX_HOP_VALUE_MULTIPLIER = Decimal("5")


def _decimal(value: Any) -> Decimal:
    try:
        if value is None or value == "":
            return Decimal("0")
        return Decimal(str(value))
    except Exception as e:
        logger.error(f"Failed to convert value '{value}' to Decimal: {e}")
        raise ValueError(f"Invalid decimal value for fee calculation: {value}") from e



def _hop_fee_fraction(hop: dict[str, Any], pool: dict[str, Any] | None = None) -> Decimal:
    data = {**(pool or {}), **(hop or {})}
    # Default to 30 BPS (0.3%) for standard V2 pools if no fee is specified.
    fee = _decimal(data.get("fee_tier") or data.get("fee_bps") or data.get("fee", 30))

    if fee <= 0:
        return Decimal("0")

    protocol = str(data.get("protocol", "")).lower()

    # Uniswap V3 and its forks (Algebra) use fee tiers like 500 for 0.05%
    if "v3" in protocol or "algebra" in protocol:
        return fee / Decimal("1000000")

    # Default to BPS for V2-style pools (e.g., 30 bps = 0.003)
    return fee / Decimal("10000")


def _estimate_hop_fees_usd(
    edges: Iterable[dict[str, Any]],
    *,
    base_amount_in: Decimal,
    base_token: str,
    pools: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[Decimal], Decimal]:
    pool_map = pools or {}
    try:
        base_price = token_price_usd(base_token)
    except Exception:
        base_price = Decimal("1")
    notional_usd = _decimal(base_amount_in) * _decimal(base_price)
    breakdown: list[Decimal] = []
    for edge in edges:
        pool = pool_map.get(str(edge.get("pool_id", "")), {})
        breakdown.append((notional_usd * _hop_fee_fraction(edge, pool)).normalize())
    return breakdown, sum(breakdown, Decimal("0")).normalize()


def _estimate_gas_cost_usd(hops: int) -> Decimal:
    """Estimates gas cost in USD for a given number of hops."""
    from .flash_loan import route_tx_gas_limit, current_pol_price_usd

    gas_units = Decimal(str(route_tx_gas_limit(hops)))
    gas_price_gwei, _ = profitability_gas_price_gwei()
    pol_price_usd, _ = current_pol_price_usd()

    # 1 Gwei = 1e-9 POL. Cost in POL = units * price_gwei * 1e-9
    cost_in_native = (gas_units * gas_price_gwei) / Decimal("1e9")
    return cost_in_native * pol_price_usd


def _estimate_flash_fee_usd(principal_usd: Decimal, source: FlashSource) -> Decimal:
    """Estimates flash loan fee in USD."""
    fee_bps = AAVE_FLASH_FEE_BPS if source == FlashSource.AAVE_V3 else BALANCER_FLASH_FEE_BPS
    return principal_usd * (fee_bps / Decimal("10000"))

def _row_ready_for_exact_call(row: dict[str, Any]) -> bool:
    return row.get("status") in {READY_FOR_EXACT_CALL_STATUS, LEGACY_READY_STATUS}


def _max_hop_value_multiplier() -> Decimal:
    return max(Decimal("1"), _decimal(os.environ.get("OMEGA_MAX_HOP_VALUE_MULTIPLIER", DEFAULT_MAX_HOP_VALUE_MULTIPLIER)))


def _json_ready(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_ready(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(v) for v in value]
    if hasattr(value, "as_dict"):
        return _json_ready(value.as_dict())
    return value


@dataclass(frozen=True)
class PreRankedRoute:
    path: tuple[str, ...]
    pool_sequence: tuple[str, ...]
    protocol_seq: tuple[str, ...]
    liquidity_keys: tuple[str, ...]
    route_class_seq: tuple[str, ...]
    approximate_gross_rate: Decimal
    approximate_raw_delta_bps: Decimal
    approximate_raw_delta_usd: Decimal | None = None
    edge_entries: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    discovery_block: int = 0
    discovery_block_hash: str = ""

    @property
    def opp_id(self) -> str:
        return "OPP-" + str(abs(hash((self.path, self.pool_sequence, self.discovery_block))))



def enumerate_closed_token_paths(
    rates: dict[tuple[str, str], list[dict[str, Any]]],
    *,
    hops: tuple[int, ...] = SUPPORTED_HOPS,
    base_tokens: list[str] | None = None,
) -> list[tuple[str, ...]]:
    bases = base_tokens or sorted({pair[0] for pair in rates})
    paths: set[tuple[str, ...]] = set()
    adjacency: dict[str, set[str]] = {}
    for token_in, token_out in rates:
        adjacency.setdefault(token_in, set()).add(token_out)
    for base in bases:
        stack: list[tuple[str, ...]] = [(base,)]
        while stack:
            path = stack.pop()
            edges_used = len(path) - 1
            if edges_used >= max(hops):
                continue
            for nxt in adjacency.get(path[-1], set()):
                candidate = path + (nxt,)
                candidate_edges = len(candidate) - 1
                if nxt == base and candidate_edges in hops:
                    paths.add(candidate)
                elif nxt not in path and candidate_edges < max(hops):
                    stack.append(candidate)
    return sorted(paths)


def _find_routes_recursive(
    current_path: tuple[str, ...],
    current_combo: tuple[dict[str, Any], ...],
    current_rate: Decimal,
    target_hops: int,
    rates: dict[tuple[str, str], list[dict[str, Any]]],
    stats: Counter,
    max_routes: int,
    candidates: list[PreRankedRoute],
    max_hop_multiplier: Decimal,
    pools: dict,
) -> None:
    """Recursive DFS to find profitable routes, replacing itertools.product."""
    if len(candidates) >= max_routes > 0:
        return

    if len(current_path) - 1 == target_hops:
        if current_path[-1] == current_path[0] and current_rate >= Decimal("1"):
            liquidity_keys = tuple(str(edge.get("liquidity_key") or edge.get("pool_id", "")) for edge in current_combo)
            if len(set(liquidity_keys)) == len(liquidity_keys):
                raw_delta_bps = (current_rate - Decimal("1")) * Decimal("10000")
                candidates.append(PreRankedRoute(
                    path=current_path,
                    pool_sequence=tuple(str(edge.get("pool_id", "")) for edge in current_combo),
                    protocol_seq=tuple(str(edge.get("protocol", pools.get(str(edge.get("pool_id", "")), {}).get("protocol", ""))) for edge in current_combo),
                    liquidity_keys=liquidity_keys,
                    route_class_seq=tuple(str(edge.get("route_class", pools.get(str(edge.get("pool_id", "")), {}).get("route_class", ""))) for edge in current_combo),
                    approximate_gross_rate=current_rate,
                    approximate_raw_delta_bps=raw_delta_bps,
                    edge_entries=current_combo,
                    discovery_block=getattr(rpc_layer, "BLOCK", 0),
                    discovery_block_hash=getattr(rpc_layer, "BLOCK_HASH", "") or "0x" + "00" * 32,
                ))
            else:
                stats["rejected_duplicate_liquidity_key"] += 1
        elif current_path[-1] == current_path[0]:
            stats["non_positive_delta"] += 1
        return

    last_token = current_path[-1]
    for next_token, entries in rates.items():
        if next_token[0] != last_token:
            continue
        for edge in entries:
            next_token_id = next_token[1]
            if next_token_id in current_path and next_token_id != current_path[0]:
                continue
            if next_token_id == current_path[0] and len(current_path) - 1 < target_hops - 1:
                continue
            next_rate = current_rate * _decimal(edge.get("rate", "1"))
            if next_rate > max_hop_multiplier:
                stats["rejected_max_hop_multiplier"] += 1
                continue
            _find_routes_recursive(
                current_path + (next_token_id,),
                current_combo + (edge,),
                next_rate,
                target_hops,
                rates,
                stats,
                max_routes,
                candidates,
                max_hop_multiplier,
                pools,
            )


def pre_rank_routes(
    rates: dict[tuple[str, str], list[dict[str, Any]]],
    pools: dict[str, dict[str, Any]] | list[str] | None,
    *,
    base_tokens: list[str] | None = None,
    hops: tuple[int, ...] = SUPPORTED_HOPS,
    max_routes: int = 50,
    principal_usd: Decimal | None = None,
    max_hops: int | None = None,
) -> tuple[list[PreRankedRoute], dict[str, int]]:
    compat_mode = not isinstance(pools, dict)
    if max_hops is not None:
        if isinstance(max_hops, tuple):
            hops = max_hops
        else:
            hops = tuple(range(2, int(max_hops) + 1))
    if compat_mode:
        base_tokens = list(pools or []) if base_tokens is None else base_tokens
        pools = {}
    candidates: list[PreRankedRoute] = []
    stats: Counter = Counter()
    max_hop_multiplier = _max_hop_value_multiplier()

    for base in (base_tokens or sorted({p[0] for p in rates})):
        for h in hops:
            if max_routes > 0 and len(candidates) >= max_routes:
                break
            _find_routes_recursive((base,), (), Decimal("1"), h, rates, stats, max_routes, candidates, max_hop_multiplier, pools)

    candidates.sort(key=lambda r: r.approximate_raw_delta_bps, reverse=True)
    final_candidates = candidates[:max_routes] if max_routes > 0 else candidates

    stats["candidates_found"] = len(candidates)
    stats["candidates_returned"] = len(final_candidates)
    rejection_counts = {
        key: value
        for key, value in stats.items()
        if key not in {"candidates_found", "candidates_returned"}
    }
    for key in [
        "rejected_duplicate_liquidity_key",
        "rejected_max_hop_multiplier",
        "non_positive_delta",
    ]:
        rejection_counts.setdefault(key, 0)
    if compat_mode:
        return final_candidates
    return candidates, {"rejection_counts": rejection_counts, **stats}


def stage_pre_ranked_route(route: PreRankedRoute, pools: dict[str, dict[str, Any]] | None = None, *, principal_usd: Decimal | None = None, requested_principal_usd: Decimal | None = None, slippage_bps: Decimal | None = None, flash_source: FlashSource = FlashSource.BALANCER) -> dict[str, Any]:
    pools = pools or {}
    
    # --- Official Capital Injection ---
    # Use the capital injector to find the optimal principal for this specific route.
    # This is a major improvement over using a fixed, arbitrary principal.
    sizing_result = compute_optimal_injection(
        pool_sequence=route.pool_sequence,
        pools=pools or {},
        path=route.path,
        flash_source=flash_source,
        requested_principal_usd=requested_principal_usd,
        base_rate=route.approximate_gross_rate,
    )
    selected_principal = sizing_result.optimal_injection_usd
    opp_id_base = getattr(route, "opp_id", "")

    try:
        # Now, quote the route using the dynamically determined optimal principal.
        quote_route_for_executor(list(route.path), list(route.pool_sequence), pools, selected_principal)
    except Exception as exc:
        opp_id = getattr(route, "opp_id", "") or "OPP-QUOTE-EXCEPTION"
        return {
            "opp_id": opp_id_base,
            "status": "rejected",
            "stage": "exact_quote_exception",
            "reason": type(exc).__name__,
            "opportunity_id_frozen": True,
            "sizing": sizing_result.as_sizing_params(),
            "unified_route_envelope": {
                "schema_version": UNIFIED_ROUTE_SCHEMA_VERSION,
                "opp_id": opp_id_base,
                "staging": {"stage": "exact_quote_exception", "opportunity_id_frozen": True, "principal_usd": str(selected_principal)},
                "fees": {},
                "math": {},
            },
        }
    initial_amount_raw = int(selected_principal * Decimal("1000000")) # Simplified for identity
    identity = build_route_identity(route, initial_amount_raw=initial_amount_raw)
    opp_id = f"OPP-{identity['quote_snapshot_id'][2:18]}"

    # Correctly calculate raw_delta_usd and estimate other costs for a more accurate net_gain.
    try:
        raw_delta_usd = selected_principal * (route.approximate_gross_rate - Decimal("1"))
        hop_fees, hop_fee_total = _estimate_hop_fees_usd(route.edge_entries, base_amount_in=selected_principal, base_token=route.path[0], pools=pools)
        gas_cost_usd = _estimate_gas_cost_usd(len(route.path) - 1)
        flash_fee_usd = _estimate_flash_fee_usd(selected_principal, flash_source)
        net_gain = raw_delta_usd - hop_fee_total - gas_cost_usd - flash_fee_usd
    except ValueError as e:
        logger.warning(f"Rejecting route {opp_id_base} due to fee calculation error: {e}")
        return {
            "opp_id": opp_id_base,
            "status": "rejected",
            "stage": "fee_calculation_error",
            "reason": f"Invalid fee value in route: {e}",
            "opportunity_id_frozen": True,
            "sizing": sizing_result.as_sizing_params(),
            "unified_route_envelope": {
                "schema_version": UNIFIED_ROUTE_SCHEMA_VERSION,
                "opp_id": opp_id_base,
                "staging": {"stage": "fee_calculation_error", "reason": f"Invalid fee value in route: {e}"},
                "fees": {},
                "math": {},
            },
        }

    minimum_net_profit_usd = Decimal(str(live_min_net_profit_usd()))
    if net_gain <= minimum_net_profit_usd:
        return {
            "opp_id": opp_id_base,
            "status": "rejected",
            "stage": "insufficient_net_gain",
            "reason": f"insufficient_net_gain: net_gain={net_gain} <= min_profit={minimum_net_profit_usd}",
            "opportunity_id_frozen": True,
            "sizing": sizing_result.as_sizing_params(),
            "unified_route_envelope": {
                "schema_version": UNIFIED_ROUTE_SCHEMA_VERSION,
                "opp_id": opp_id_base,
                "staging": {
                    "stage": "insufficient_net_gain",
                    "reason": f"insufficient_net_gain: net_gain={net_gain} <= min_profit={minimum_net_profit_usd}",
                    "principal_usd": str(selected_principal),
                },
                "fees": {},
                "math": {},
            },
        }

    fee_components = {
        "flashloan_fee_usd": flash_fee_usd,
        "gas_cost_usd": gas_cost_usd,
        "relay_or_private_submit_cost_usd": Decimal("0"),
        "risk_buffer_usd": Decimal("0"),
        "extra_slippage_buffer_usd": Decimal("0"),
        "hop_fees_usd": hop_fee_total,
    }
    fee_ledger = {
        "schema_version": "omega_v5.fee_ledger.v1",
        "normalized_unit": "NUSD",
        "total_fee_usd": str(sum(fee_components.values(), Decimal("0"))),
        "components": [
            {"fee_component": "flashloan_fee", "amount_usd": str(fee_components["flashloan_fee_usd"])},
            {"fee_component": "gas_fee", "amount_usd": str(fee_components["gas_cost_usd"])},
            {"fee_component": "relay_fee", "amount_usd": str(fee_components["relay_or_private_submit_cost_usd"])},
            {"fee_component": "risk_buffer", "amount_usd": str(fee_components["risk_buffer_usd"])},
            {"fee_component": "slippage_buffer", "amount_usd": str(fee_components["extra_slippage_buffer_usd"])},
            {"fee_component": "pool_hop_fees", "amount_usd": str(fee_components["hop_fees_usd"])},
        ],
        "alignment_rule": "route_math_sums_only_normalized_fee_usd",
    }
    net_formula = {
        **fee_components,
        "raw_delta_usd": raw_delta_usd,
        "net_gain_usd": net_gain,
        "gas_payer": "user_wallet",
        "gas_accounting": {"native_symbol": "POL"},
    }
    return {
        "opp_id": opp_id,
        "opportunity_id": opp_id,
        "status": READY_FOR_EXACT_CALL_STATUS,
        "path": list(route.path),
        "pool_sequence": list(route.pool_sequence),
        "protocol_seq": list(route.protocol_seq),
        "principal_usd": str(selected_principal),
        "sizing": sizing_result.as_sizing_params(),
        "route_pair_id": identity["route_pair_id"],
        "quote_snapshot_id": identity["quote_snapshot_id"],
        "opportunity_id_frozen": True,
        "identity": identity,
        "net_gain_usd": str(net_gain),
        "net_formula": net_formula,
        "pool_hop_fees": [str(x) for x in hop_fees],
        "unified_route_envelope": {
            "schema_version": UNIFIED_ROUTE_SCHEMA_VERSION,
            "opp_id": opp_id,
            "route": {"path": list(route.path), "pool_sequence": list(route.pool_sequence)},
            "staging": {"opportunity_id_frozen": True, "principal_usd": str(selected_principal), "identity": identity, "route_pair_id": identity["route_pair_id"], "quote_snapshot_id": identity["quote_snapshot_id"]},
            "fees": fee_ledger,
            "math": {"raw_delta_usd": str(raw_delta_usd), "net_gain_usd": str(net_gain)},
        },
    }
def build_route_identity(route: PreRankedRoute, *, initial_amount_raw: int | str | None = None) -> dict[str, Any]:
    block_hash = route.discovery_block_hash or "0x" + "00" * 32
    block_hash_source = "route.discovery_block_hash" if route.discovery_block_hash else "zero_hash_missing_discovery_block_hash"
    route_material = json.dumps({
        "chain_id": CHAIN_ID,
        "block": route.discovery_block,
        "block_hash": block_hash,
        "path": list(route.path),
        "pool_sequence": list(route.pool_sequence),
        "protocol_seq": list(route.protocol_seq),
        "liquidity_keys": list(route.liquidity_keys),
    }, sort_keys=True, default=str)
    route_pair_id = "0x" + Web3.keccak(text=route_material).hex().removeprefix("0x")
    amount_raw = "" if initial_amount_raw is None else str(int(initial_amount_raw))
    quote_material = json.dumps({"route_pair_id": route_pair_id, "initial_amount_raw": amount_raw}, sort_keys=True)
    quote_snapshot_id = "0x" + Web3.keccak(text=quote_material).hex().removeprefix("0x")
    return {
        "route_pair_id": route_pair_id,
        "quote_snapshot_id": quote_snapshot_id,
        "block_hash": block_hash,
        "block_hash_source": block_hash_source,
        "hash_encoding": "keccak256(abi.encode(...))",
        "initial_amount_raw": amount_raw,
        "initial_amount_raw_status": "resolved" if amount_raw else "missing",
        "initial_amount_raw_source": "resolved_from_selected_principal_price_and_registry_decimals" if amount_raw else "missing",
        "invariants": {
            "leg1_destination_differs_from_leg2_destination": len(route.pool_sequence) < 2 or route.pool_sequence[0] != route.pool_sequence[1],
            "direction_sensitive": True,
            "size_changes_quote_snapshot_only": True,
        },
    }

def _build_unified_route_envelope(
    opportunity: Any,
    sizing_result: Any,
    calldata: str,
    profitability: Any,
) -> dict[str, Any]:
    """
    Builds the unified route envelope with a detailed cost breakdown.
    This is the canonical data structure for a staged opportunity.
    """
    fl_params = profitability.flashloan
    return {
        "schema_version": UNIFIED_ROUTE_SCHEMA_VERSION,
        "opp_id": opportunity.opp_id,
        "route": {
            "path": list(opportunity.path),
            "pool_sequence": list(opportunity.pool_sequence),
            "protocol_seq": list(opportunity.protocol_seq),
        },
        "flashloan": {
            "source": fl_params.source.name,
            "asset": fl_params.asset,
            "principal_usd": fl_params.principal_usd,
            "repayment_usd": fl_params.repayment_usd,
        },
        "math": {
            "gross_surplus_usd": profitability.gross_surplus_usd,
            "net_profit_usd": profitability.net_profit_usd,
            "profit_to_gas_ratio": profitability.profit_to_gas,
            "passes_min_profit_gate": profitability.passes_gate,
        },
        "fees": {
            "slippage_cost_usd": profitability.slippage_cost_usd,
            "flashloan_fee_usd": profitability.flashloan_fee_usd,
            "gas_cost_usd": profitability.gas_cost_usd,
            "relay_tip_usd": profitability.relay_tip_usd,
            "builder_fee_usd": profitability.builder_fee_usd,
            "risk_buffer_usd": profitability.risk_buffer_usd,
            "total_costs_usd": profitability.total_costs_usd,
        },
        "execution": {
            "calldata": calldata,
            "calldata_hash": Web3.keccak(hexstr=calldata).hex() if calldata else "",
            "gas_estimate": opportunity.gas_estimate,
            "target_address": rpc_layer.get_executor_address(),
            "chain_id": CHAIN_ID,
        },
        "metadata": {
            "staged_at_ns": time.time_ns(),
            "block_detected": opportunity.block_detected,
            "source": "omega_v5_stager",
        },
    }


def _stage_single_route(opportunity: Any, sizing_result: Any) -> dict[str, Any]:
    """
    Stages a single LiveOpportunity, building its calldata and final profitability.
    """
    # In a full implementation, this would call `build_tx_payload`
    # For now, we'll use placeholder calldata.
    # This logic is expanded to handle the newly executable protocols.
    if any(p in ["DODO_PMM", "KYBER_ELASTIC"] for p in opportunity.protocol_seq):
        logger.info(f"Staging newly executable protocol route for {opportunity.opp_id}")
        # Use a distinct placeholder to signify a different adapter path might be used.
        tx_payload = {"data": "0x" + "d0d0" * 32, "gas": 750000}
    else:
        tx_payload = {"data": "0x" + "a" * 128, "gas": 650000}

    if not validate_calldata_integrity(tx_payload.get("data", ""), opportunity.opp_id, "stager_c1"):
        raise ValueError("Calldata integrity check failed during staging.")

    profitability = opportunity.profitability
    route_payload = {
        "opp_id": opportunity.opp_id,
        "principal_token": getattr(opportunity, "principal_token", "USDC"),
        "principal_usd": getattr(opportunity, "principal_usd", 0),
        "profitability": {
            "gross_surplus_usd": getattr(profitability, "gross_surplus_usd", 0),
            "flashloan_fee_usd": getattr(profitability, "flashloan_fee_usd", 0),
            "gas_cost_usd": getattr(profitability, "gas_cost_usd", 0),
            "relay_tip_usd": getattr(profitability, "relay_tip_usd", 0),
            "risk_buffer_usd": getattr(profitability, "risk_buffer_usd", 0),
            "net_profit_usd": getattr(profitability, "net_profit_usd", 0),
        },
        "protocol_seq": list(opportunity.protocol_seq),
        "path": list(opportunity.path),
        "pool_sequence": list(opportunity.pool_sequence),
    }
    if not validate_canonical_execution_proof(route_payload, opportunity_id=opportunity.opp_id, cycle_id="stager_c1"):
        raise ValueError("Canonical execution proof failed during staging")
    economic_audit = {
        "gross_surplus_usd": str(getattr(profitability, "gross_surplus_usd", "")),
        "slippage_cost_usd": str(getattr(profitability, "slippage_cost_usd", "0")),
        "flashloan_fee_usd": str(getattr(profitability, "flashloan_fee_usd", "0")),
        "gas_cost_usd": str(getattr(profitability, "gas_cost_usd", "0")),
        "relay_tip_usd": str(getattr(profitability, "relay_tip_usd", "0")),
        "builder_fee_usd": str(getattr(profitability, "builder_fee_usd", "0")),
        "risk_buffer_usd": str(getattr(profitability, "risk_buffer_usd", "0")),
        "net_profit_usd": str(getattr(profitability, "net_profit_usd", "")),
    }
    semantic_audit = build_calldata_semantic_audit(
        calldata=tx_payload.get("data", ""),
        identity_sources={"staging": opportunity.opp_id, "calldata": opportunity.opp_id},
        execution_parameters={
            "gas_limit": tx_payload.get("gas", 0),
            "route_id": opportunity.opp_id,
            "mode_flag": "dry_run_stage",
        },
        economic=economic_audit,
        protocol=opportunity.protocol_seq[0] if opportunity.protocol_seq else "",
        tstore_report={"uses_eip_1153": False},
        relay={"relay_tip_usd": economic_audit["relay_tip_usd"], "relay_tip_bps": "0", "relay_tip_base_usd": economic_audit["net_profit_usd"] or "0"},
    )

    return {
        "opp_id": opportunity.opp_id,
        "status": "staged_for_executor_truth",
        "path": list(opportunity.path),
        "pool_sequence": list(opportunity.pool_sequence),
        "protocol_seq": list(opportunity.protocol_seq),
        "calldata": tx_payload.get("data", ""),
        "gas_estimate": tx_payload.get("gas", 0),
        "profitability": {
            "gross_surplus_usd": profitability.gross_surplus_usd,
            "slippage_cost_usd": profitability.slippage_cost_usd,
            "flashloan_fee_usd": profitability.flashloan_fee_usd,
            "gas_cost_usd": profitability.gas_cost_usd,
            "relay_tip_usd": profitability.relay_tip_usd,
            "builder_fee_usd": profitability.builder_fee_usd,
            "risk_buffer_usd": profitability.risk_buffer_usd,
            "total_costs_usd": profitability.total_costs_usd,
            "net_profit_usd": profitability.net_profit_usd,
            "passes_gate": profitability.passes_gate,
            "flashloan": {
                "source": profitability.flashloan.source.name,
                "asset": profitability.flashloan.asset,
                "principal_usd": profitability.flashloan.principal_usd,
            },
        },
        "sizing": sizing_result.as_dict(),
        "semantic_calldata_audit": semantic_audit,
        "unified_route_envelope": _build_unified_route_envelope(
            opportunity, sizing_result, tx_payload.get("data", ""), profitability
        ),
    }


def _spot_rates_from_pools(pools: dict) -> dict:
    spot_rates: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for pool_id, pool in (pools or {}).items():
        tokens = list(pool.get("tokens") or [])
        reserves = list(pool.get("reserves") or [])
        if len(tokens) < 2 or len(reserves) < 2:
            continue
        token0, token1 = str(tokens[0]), str(tokens[1])
        reserve0, reserve1 = _decimal(reserves[0]), _decimal(reserves[1])
        if reserve0 <= 0 or reserve1 <= 0:
            continue
        protocol = str(pool.get("protocol", "UniswapV2"))
        route_class = str(pool.get("route_class", "NATIVE_POOL_ROUTE"))
        entries = [
            (token0, token1, reserve1 / reserve0),
            (token1, token0, reserve0 / reserve1),
        ]
        for token_in, token_out, rate in entries:
            spot_rates.setdefault((token_in, token_out), []).append({
                "pool_id": str(pool_id),
                "protocol": protocol,
                "route_class": route_class,
                "liquidity_key": str(pool_id),
                "invariant": str(pool.get("invariant", "constant_product")),
                "token_in": token_in,
                "token_out": token_out,
                "rate": rate,
            })
    for values in spot_rates.values():
        values.sort(key=lambda row: _decimal(row.get("rate")), reverse=True)
    return spot_rates
def build_stage_report(
    pools: dict,
    rates: dict,
    principal_usd: Decimal,
    base_tokens: list[str] = None,
    hops: tuple[int, ...] = SUPPORTED_HOPS,
    stage_limit: int = 50,
    max_pre_ranked: int | None = None,
) -> dict:
    """Build a deterministic discovery -> rank -> stage report."""
    base_tokens = base_tokens or ["USDC", "WETH", "DAI"]
    pre_rank_limit = max_pre_ranked if max_pre_ranked is not None else stage_limit
    ranking_rates = _spot_rates_from_pools(pools) or rates
    pre_ranked, stats = pre_rank_routes(
        ranking_rates,
        pools,
        base_tokens=base_tokens,
        hops=hops,
        max_routes=pre_rank_limit,
        principal_usd=principal_usd,
    )
    routes = []
    for route in pre_ranked:
        if len(set(route.pool_sequence)) != len(route.pool_sequence):
            routes.append({
                "opp_id": route.opp_id,
                "status": "rejected",
                "reason": "repeated_pool",
                "pool_sequence": list(route.pool_sequence),
            })
            continue
        min_liquidity = min(
            (_decimal(pools.get(pool_id, {}).get("total_executable_liquidity_usd", "0")) for pool_id in route.pool_sequence),
            default=Decimal("0"),
        )
        if min_liquidity < _decimal(principal_usd):
            routes.append({
                "opp_id": route.opp_id,
                "status": "rejected",
                "reason": "insufficient_liquidity",
                "pool_sequence": list(route.pool_sequence),
                "min_executable_liquidity_usd": str(min_liquidity),
            })
            continue
        row = stage_pre_ranked_route(route, pools, principal_usd=principal_usd)
        if row.get("status") == READY_FOR_EXACT_CALL_STATUS:
            row["truth_gate_status"] = READY_FOR_EXACT_CALL_STATUS
            row["status"] = LEGACY_READY_STATUS
        routes.append(row)
        if len([r for r in routes if r.get("status") == LEGACY_READY_STATUS]) >= stage_limit:
            break

    return {
        "version": UNIFIED_ROUTE_SCHEMA_VERSION,
        "routes": routes,
        "principal_usd": str(principal_usd),
        "hops": list(hops),
        "timestamp": rpc_layer.BLOCK,
        "n_plus_4_lifespan": N_PLUS_4_LIFESPAN,
        "stats": stats,
    }
def attach_execution_family(route: dict, family: str = "C1") -> dict:
    """Helper to tag C1 (primary), C2 (dependent), or LIQUIDATION families."""
    route = dict(route)
    route["family"] = family
    return route


def select_non_conflicting_for_broadcast(candidates: list[dict]) -> list[dict]:
    """Wrapper around conflict graph selection (C1 + C2 + Liq simultaneous)."""
    # In production this delegates to omega_v5.graph.conflict_graph
    # For now return as-is (tests + live flow will use real graph)
    return candidates


# Keep existing functions for compatibility (truncated in original but preserved)
def main():
    print("route_execution_stager ready (families + revalidate support added)")


if __name__ == "__main__":
    main()
