#!/usr/bin/env python3
"""Compact route execution staging layer with buy-low/sell-high proof."""

from __future__ import annotations

import itertools
import argparse
import json
import logging
import os
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable

from web3 import Web3

from . import rpc_layer
from .config import CHAIN_ID, normalize_protocol
from .executable_quotes import quote_route_for_executor
from .flash_loan import FlashSource, MIN_NET_PROFIT_USD
from .oracle_layer import token_price_usd
from .paths import output_path
from .pricing.net_delta import route_within_lifespan
from .payload_envelope import UNIFIED_ROUTE_SCHEMA_VERSION

logger = logging.getLogger("omega.stager")
LATEST_STAGE_REPORT = output_path("route_execution_stage_latest.json")
HISTORY_STAGE_REPORT = output_path("route_execution_stage_history.jsonl")
SUPPORTED_HOPS = (2, 3, 4)
N_PLUS_4_LIFESPAN = 4
READY_FOR_EXACT_CALL_STATUS = "ready_for_exact_call"
LEGACY_READY_STATUS = "staged_for_executor_truth"
DEFAULT_MAX_QUOTE_OPTIONS_PER_PAIR = 3
DEFAULT_MAX_HOP_VALUE_MULTIPLIER = Decimal("5")


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value if value is not None else "0"))
    except Exception:
        return Decimal("0")




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
    approximate_raw_delta_usd: Decimal
    approximate_raw_delta_bps: Decimal
    edge_entries: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    discovery_block: int = 0
    discovery_block_hash: str = ""

    @property
    def opp_id(self) -> str:
        return "OPP-PRE-" + Web3.keccak(text=json.dumps(_json_ready({
            "path": self.path,
            "pools": self.pool_sequence,
            "block": self.discovery_block,
        }), sort_keys=True))[:8].hex()

    def as_dict(self) -> dict[str, Any]:
        return {
            "opp_id": self.opp_id,
            "path": list(self.path),
            "pool_sequence": list(self.pool_sequence),
            "protocol_seq": list(self.protocol_seq),
            "liquidity_keys": list(self.liquidity_keys),
            "route_class_seq": list(self.route_class_seq),
            "approximate_gross_rate": str(self.approximate_gross_rate),
            "approximate_raw_delta_usd": str(self.approximate_raw_delta_usd),
            "approximate_raw_delta_bps": str(self.approximate_raw_delta_bps),
            "discovery_block": self.discovery_block,
            "discovery_block_hash": self.discovery_block_hash,
        }


def _hop_fee_fraction(hop: dict[str, Any] | None = None, pool: dict[str, Any] | None = None) -> Decimal:
    raw: Any = None
    if hop:
        raw = hop.get("fee", hop.get("fee_tier", hop.get("fee_bps")))
    if raw is None and pool:
        raw = pool.get("fee_tier", pool.get("fee", pool.get("fee_bps", pool.get("swap_fee"))))
    if raw is None:
        raw = 3000
    fee = _decimal(raw)
    if fee < 0:
        return Decimal("0")
    if fee <= Decimal("1"):
        return fee
    if fee >= Decimal("100"):
        return fee / Decimal("1000000")
    return fee / Decimal("10000")


def _estimate_hop_fees_usd(
    edge_entries: Iterable[dict[str, Any]],
    *,
    base_amount_in: Decimal,
    base_token: str,
    pools: dict[str, dict],
    pool_sequence: Iterable[str] | None = None,
) -> tuple[list[Decimal], Decimal]:
    entries = list(edge_entries or [])
    pool_ids = list(pool_sequence or [str(e.get("pool_id", "")) for e in entries])
    try:
        px = Decimal(str(token_price_usd(base_token)))
    except Exception:
        px = Decimal("1")
    notional = _decimal(base_amount_in) * px
    breakdown: list[Decimal] = []
    for idx, entry in enumerate(entries):
        pool = pools.get(pool_ids[idx], {}) if idx < len(pool_ids) else {}
        breakdown.append(notional * _hop_fee_fraction(entry, pool))
    return breakdown, sum(breakdown, Decimal("0"))


def enumerate_closed_token_paths(
    rates: dict,
    *,
    hops: Iterable[int] = SUPPORTED_HOPS,
    base_tokens: Iterable[str] | None = None,
    max_token_paths: int = 0,
) -> list[tuple[str, ...]]:
    adjacency: dict[str, set[str]] = {}
    for token_in, token_out in rates:
        adjacency.setdefault(str(token_in), set()).add(str(token_out))
    bases = list(base_tokens or sorted(adjacency))
    hop_set = {int(h) for h in hops}
    out: list[tuple[str, ...]] = []

    def walk(base: str, node: str, remaining: int, path: list[str]) -> None:
        if max_token_paths and len(out) >= max_token_paths:
            return
        if remaining == 0:
            if node == base and len(path) > 1:
                out.append(tuple(path))
            return
        for nxt in sorted(adjacency.get(node, set())):
            walk(base, nxt, remaining - 1, [*path, nxt])

    for base in bases:
        for hop_count in sorted(hop_set):
            walk(str(base), str(base), hop_count, [str(base)])
    return out


def _entry_rate(entry: dict[str, Any]) -> Decimal:
    return _decimal(entry.get("rate"))


def pre_rank_routes(
    rates: dict,
    pools: dict[str, dict],
    *,
    principal_usd: Decimal = Decimal("0"),
    hops: Iterable[int] = SUPPORTED_HOPS,
    max_quote_options_per_pair: int = 0,
    max_token_paths: int = 0,
    max_pre_ranked: int = 0,
    base_tokens: Iterable[str] | None = None,
) -> tuple[list[PreRankedRoute], dict[str, Any]]:
    counters: Counter[str] = Counter()
    scored: list[tuple[PreRankedRoute, Decimal]] = []
    for path in enumerate_closed_token_paths(rates, hops=hops, base_tokens=base_tokens, max_token_paths=max_token_paths):
        option_sets: list[list[dict[str, Any]]] = []
        missing = False
        for idx in range(len(path) - 1):
            options = list(rates.get((path[idx], path[idx + 1]), []))
            if max_quote_options_per_pair > 0:
                options = options[:max_quote_options_per_pair]
            if not options:
                missing = True
                break
            option_sets.append(options)
        if missing:
            counters["missing_directional_edge"] += 1
            continue
        if len(path) == 3:
            best_buy = max((_entry_rate(e) for e in option_sets[0]), default=Decimal("0"))
            option_sets[0] = [e for e in option_sets[0] if _entry_rate(e) == best_buy]
        for combo in itertools.product(*option_sets):
            liquidity_keys = tuple(str(e.get("liquidity_key") or e.get("pool_id") or "") for e in combo)
            if len(liquidity_keys) != len(set(liquidity_keys)):
                counters["rejected_duplicate_liquidity_key"] += 1
                continue
            route_classes = tuple(str(e.get("route_class") or "NATIVE_POOL_ROUTE") for e in combo)
            if any(c != "NATIVE_POOL_ROUTE" for c in route_classes):
                counters["rejected_non_native_route_class"] += 1
                continue
            pool_sequence = tuple(str(e.get("pool_id") or "") for e in combo)
            if any(pid not in pools for pid in pool_sequence):
                counters["rejected_missing_live_pool"] += 1
                continue
            if len(path) == 3 and len(combo) == 2:
                buy_rate = _entry_rate(combo[0])
                sell_rate = _entry_rate(combo[1])
                buy_price = Decimal("1") / buy_rate if buy_rate > 0 else Decimal("0")
                if buy_price <= 0 or sell_rate <= buy_price:
                    counters["rejected_two_leg_buy_sell_price_misaligned"] += 1
                    continue
            gross = Decimal("1")
            for entry in combo:
                gross *= _entry_rate(entry)
            protocols = []
            for entry in combo:
                raw = str(entry.get("protocol") or "")
                try:
                    protocols.append(normalize_protocol(raw))
                except Exception:
                    protocols.append(raw)
            route = PreRankedRoute(
                path=tuple(path),
                pool_sequence=pool_sequence,
                protocol_seq=tuple(protocols),
                liquidity_keys=liquidity_keys,
                route_class_seq=route_classes,
                approximate_gross_rate=gross,
                approximate_raw_delta_usd=(gross - Decimal("1")) * _decimal(principal_usd),
                approximate_raw_delta_bps=(gross - Decimal("1")) * Decimal("10000"),
                edge_entries=tuple(dict(e) for e in combo),
                discovery_block=int(getattr(rpc_layer, "BLOCK", 0) or 0),
            )
            scored.append((route, gross))
    scored.sort(key=lambda item: item[1], reverse=True)
    if max_pre_ranked > 0:
        scored = scored[:max_pre_ranked]
    return [r for r, _ in scored], {
        "token_paths_considered": len(enumerate_closed_token_paths(rates, hops=hops, base_tokens=base_tokens, max_token_paths=max_token_paths)),
        "candidates_generated": len(scored),
        "rejection_counts": dict(counters),
        "discovery_block": int(getattr(rpc_layer, "BLOCK", 0) or 0),
    }


def _raw_units_for_identity(symbol: str, amount: Decimal) -> tuple[int, str]:
    decimals = int(getattr(rpc_layer, "TOKEN_DECIMALS", {}).get(symbol, 18))
    raw = int((_decimal(amount) * (Decimal(10) ** decimals)).to_integral_value())
    return raw, "resolved_from_selected_principal_price_and_registry_decimals"


def _block_hash(route: PreRankedRoute) -> tuple[str, str]:
    if route.discovery_block_hash:
        return route.discovery_block_hash, "route.discovery_block_hash"
    return "0x" + "00" * 32, "unavailable_zero_hash"


def build_route_identity(
    route: PreRankedRoute,
    *,
    initial_amount_raw: int = 0,
    initial_amount_raw_source: str = "provided_raw_uint256",
) -> dict[str, Any]:
    block_hash, block_hash_source = _block_hash(route)
    route_seed = json.dumps(_json_ready({
        "chain_id": CHAIN_ID,
        "path": route.path,
        "pool_sequence": route.pool_sequence,
        "protocol_seq": route.protocol_seq,
        "block_hash": block_hash,
    }), sort_keys=True, separators=(",", ":"))
    route_pair_id = "0x" + Web3.keccak(text=route_seed).hex()
    quote_seed = json.dumps({"route_pair_id": route_pair_id, "initial_amount_raw": str(int(initial_amount_raw))}, sort_keys=True)
    quote_snapshot_id = "0x" + Web3.keccak(text=quote_seed).hex()
    return {
        "schema_version": "omega_v5.route_identity.v1",
        "hash_encoding": "keccak256(abi.encode(...))",
        "chain_id": CHAIN_ID,
        "block_hash": block_hash,
        "block_hash_source": block_hash_source,
        "route_pair_id": route_pair_id,
        "quote_snapshot_id": quote_snapshot_id,
        "initial_amount_raw": str(int(initial_amount_raw)),
        "initial_amount_raw_source": initial_amount_raw_source,
        "initial_amount_raw_status": "resolved" if int(initial_amount_raw) > 0 else "unresolved_at_current_stager_boundary",
        "invariants": {
            "path_is_closed": bool(route.path and route.path[0] == route.path[-1]),
            "route_pool_order_preserved": True,
            "leg1_destination_differs_from_leg2_destination": len(route.path) >= 3 and route.path[1] != route.path[2],
        },
    }


def _hop_value_sanity(
    route: PreRankedRoute,
    pools: dict[str, dict],
    base_amount_in: Decimal,
) -> tuple[bool, str, list[dict[str, str]]]:
    amount = _decimal(base_amount_in)
    rows: list[dict[str, str]] = []
    multiplier = _max_hop_value_multiplier()
    for hop_idx, pool_id in enumerate(route.pool_sequence):
        if hop_idx + 1 >= len(route.path):
            return False, "path_pool_length_mismatch", rows
        token_in = route.path[hop_idx]
        token_out = route.path[hop_idx + 1]
        try:
            px_in = Decimal(str(token_price_usd(token_in)))
            px_out = Decimal(str(token_price_usd(token_out)))
            quote = quote_route_for_executor([token_in, token_out], [pool_id], pools, amount)
        except Exception as exc:
            return False, f"hop_quote_or_price_unavailable:{type(exc).__name__}", rows
        out_amount = _decimal(getattr(quote, "amount_out", 0))
        in_value = amount * px_in
        out_value = out_amount * px_out
        ratio = (out_value / in_value) if in_value > 0 else Decimal("0")
        rows.append({
            "hop": str(hop_idx + 1),
            "pool_id": str(pool_id),
            "token_in": str(token_in),
            "token_out": str(token_out),
            "amount_in": str(amount),
            "amount_out": str(out_amount),
            "input_value_usd": str(in_value),
            "output_value_usd": str(out_value),
            "value_ratio": str(ratio),
        })
        if out_amount <= 0 or in_value <= 0 or out_value <= 0:
            return False, "non_positive_hop_quote_or_value", rows
        if ratio > multiplier:
            return False, f"hop_value_ratio_exceeds_{multiplier}", rows
        amount = out_amount
    return True, "hop_value_sanity_passed", rows

def _execution_sequence(route: PreRankedRoute, base_amount_in: Decimal, amount_out: Decimal, amount_out_min: Decimal) -> dict[str, Any]:
    applies = len(route.path) == 3 and len(route.edge_entries) >= 2
    if not applies:
        return {"schema_version": "omega_v5.execution_sequence.v1", "applies": False, "passes": True, "reason": "multi_hop_round_trip_gate"}
    buy_mid_out = base_amount_in * _entry_rate(route.edge_entries[0])
    sell_mid_in = buy_mid_out
    buy_price = base_amount_in / buy_mid_out if buy_mid_out > 0 else Decimal("0")
    sell_price_min = amount_out_min / sell_mid_in if sell_mid_in > 0 else Decimal("0")
    passes = buy_price > 0 and sell_price_min > buy_price
    return {
        "schema_version": "omega_v5.execution_sequence.v1",
        "applies": True,
        "passes": passes,
        "policy": "BUY_LOWEST_EXECUTABLE_BASE_PER_MID_THEN_SELL_HIGHER_BACK_TO_BASE",
        "buy_leg": {"executable_buy_price_base_per_mid": buy_price},
        "sell_leg": {"executable_sell_price_min_base_per_mid": sell_price_min},
        "spread_base_per_mid_min": sell_price_min - buy_price,
        "reason": "sell_min_price_above_buy_price" if passes else "sell_min_price_not_above_buy_price",
    }


def _unified_schema(route: PreRankedRoute, row: dict[str, Any], fees: dict[str, Any] | None, math: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "schema_version": UNIFIED_ROUTE_SCHEMA_VERSION,
        "chain_id": CHAIN_ID,
        "opp_id": row.get("opp_id", route.opp_id),
        "status": row.get("status", "rejected"),
        "route": {"path": list(route.path), "pool_sequence": list(route.pool_sequence), "protocol_seq": list(route.protocol_seq)},
        "blocks": {"discovery_block": route.discovery_block, "current_block": row.get("current_block", 0)},
        "discovery": {},
        "intake": {},
        "ranking": {},
        "staging": _json_ready(row),
        "fees": _json_ready(fees or {}),
        "math": _json_ready(math or {}),
        "quote": {},
        "simulation": {},
        "payload": {},
        "submission": {},
        "settlement": {},
        "trace": {},
    }


def stage_pre_ranked_route(
    route: PreRankedRoute,
    principal_usd: Decimal | dict | None = None,
    pools: dict | None = None,
    flash_source: FlashSource = FlashSource.BALANCER,
    slippage_bps: Decimal = Decimal("0"),
    *,
    requested_principal_usd: Decimal | None = None,
) -> dict[str, Any]:
    if pools is None and isinstance(principal_usd, dict):
        pools = principal_usd
        principal_usd = requested_principal_usd
    pools = pools or {}
    selected_principal = _decimal(requested_principal_usd if requested_principal_usd is not None else principal_usd)
    if selected_principal <= 0:
        selected_principal = Decimal("10000")
    current_block = int(getattr(rpc_layer, "BLOCK", 0) or 0)
    base_token = route.path[0] if route.path else ""
    try:
        px = Decimal(str(token_price_usd(base_token)))
    except Exception:
        px = Decimal("1")
    base_amount_in = selected_principal / px if px > 0 else Decimal("0")
    initial_raw, initial_source = _raw_units_for_identity(base_token, base_amount_in)

    def rejected(stage: str, reason: str, detail: str = "") -> dict[str, Any]:
        row = {
            "status": "rejected",
            "stage": stage,
            "reason": reason,
            "detail": detail,
            "path": route.path,
            "pool_sequence": route.pool_sequence,
            "protocol_seq": route.protocol_seq,
            "principal_usd": str(selected_principal),
            "opp_id": route.opp_id,
            "opportunity_id": route.opp_id,
            "opportunity_id_frozen": True,
            "current_block": current_block,
        }
        row["unified_route_envelope"] = _unified_schema(route, row, {}, {})
        return row

    if not route_within_lifespan(route.discovery_block, current_block, N_PLUS_4_LIFESPAN):
        return rejected("lifespan_expired", "n+4 block lifespan exceeded")

    try:
        quote = quote_route_for_executor(list(route.path), list(route.pool_sequence), pools, base_amount_in)
    except Exception as exc:
        return rejected("exact_quote_exception", type(exc).__name__, str(exc))

    amount_out = _decimal(getattr(quote, "amount_out", 0))
    slip = _decimal(slippage_bps) if _decimal(slippage_bps) > 0 else Decimal("15")
    min_factor = max(Decimal("0"), Decimal("1") - slip / Decimal("10000"))
    amount_out_min = amount_out * min_factor
    out_usd = amount_out * px
    out_usd_min = out_usd * min_factor
    extra_slippage_buffer_usd = out_usd - out_usd_min
    hop_breakdown, hop_fees_total = _estimate_hop_fees_usd(route.edge_entries, base_amount_in=base_amount_in, base_token=base_token, pools=pools, pool_sequence=route.pool_sequence)
    execution_sequence = _execution_sequence(route, base_amount_in, amount_out, amount_out_min)
    hop_sanity_passes, hop_sanity_reason, hop_sanity_rows = _hop_value_sanity(route, pools, base_amount_in)

    flashloan_fee_usd = Decimal("0")
    gas_cost_usd = Decimal("0")
    relay_fee_usd = Decimal("0")
    risk_buffer_usd = Decimal("0")
    raw_delta_usd = out_usd - selected_principal
    net_gain_usd = raw_delta_usd - flashloan_fee_usd - gas_cost_usd - relay_fee_usd - risk_buffer_usd - extra_slippage_buffer_usd
    passes = net_gain_usd > MIN_NET_PROFIT_USD and bool(execution_sequence.get("passes", True)) and hop_sanity_passes
    status = READY_FOR_EXACT_CALL_STATUS if passes else "rejected"
    identity = build_route_identity(route, initial_amount_raw=initial_raw, initial_amount_raw_source=initial_source)
    opp_id = f"OPP-{identity['quote_snapshot_id'][2:18]}"
    fee_components = {
        "flashloan_fee_usd": flashloan_fee_usd,
        "gas_cost_usd": gas_cost_usd,
        "relay_or_private_submit_cost_usd": relay_fee_usd,
        "risk_buffer_usd": risk_buffer_usd,
        "extra_slippage_buffer_usd": extra_slippage_buffer_usd,
        "hop_fees_usd": hop_fees_total,
    }
    fee_ledger = {
        "schema_version": "omega_v5.fee_ledger.v1",
        "normalized_unit": "NUSD",
        "components": [
            {"fee_component": "flashloan_fee", "amount_usd": str(flashloan_fee_usd)},
            {"fee_component": "gas_fee", "amount_usd": str(gas_cost_usd)},
            {"fee_component": "relay_fee", "amount_usd": str(relay_fee_usd)},
            {"fee_component": "risk_buffer", "amount_usd": str(risk_buffer_usd)},
            {"fee_component": "slippage_buffer", "amount_usd": str(extra_slippage_buffer_usd)},
            {"fee_component": "pool_hop_fees", "amount_usd": str(hop_fees_total)},
        ],
        "total_fee_usd": str(sum(fee_components.values(), Decimal("0"))),
        "alignment_rule": "route_math_sums_only_normalized_fee_usd",
    }
    formula = {
        "raw_delta_usd": raw_delta_usd,
        **fee_components,
        "net_gain_usd": net_gain_usd,
        "gas_payer": "user_wallet",
        "gas_accounting": {"native_symbol": "POL", "gas_cost_source": "evaluate_profitability"},
    }
    row = {
        "path": route.path,
        "pool_sequence": route.pool_sequence,
        "protocol_seq": route.protocol_seq,
        "opportunity_id_frozen": True,
        "principal_usd": str(selected_principal),
        "sizing": {"selected_principal_usd": str(selected_principal)},
        "flash_source": flash_source.value if hasattr(flash_source, "value") else str(flash_source),
        "raw_gate_eligible": route.approximate_gross_rate > Decimal("1"),
        "status": status,
        "stage": status,
        "reason": "ready_for_exact_call_profitability_gate_passed" if passes else execution_sequence.get("reason", "profitability_gate_failed"),
        "discovery_block": route.discovery_block,
        "current_block": current_block,
        "hop_fees_usd": str(hop_fees_total),
        "hop_fee_breakdown": [str(x) for x in hop_breakdown],
        "amount_out": str(amount_out),
        "amount_out_min": str(amount_out_min),
        "out_usd": str(out_usd),
        "out_usd_min": str(out_usd_min),
        "raw_delta_usd": raw_delta_usd,
        "net_gain_usd": net_gain_usd,
        "extra_slippage_buffer_usd": str(extra_slippage_buffer_usd),
        "hop_value_sanity": {"passes": hop_sanity_passes, "reason": hop_sanity_reason, "max_value_ratio": str(_max_hop_value_multiplier()), "hops": hop_sanity_rows},
        "truth_gate": {"exact_call_required": True, "exact_call_passed": False, "live_submit_allowed": False, "reason": "awaiting_exact_call_truth"},
        "legacy_status": LEGACY_READY_STATUS if passes else "rejected",
        "execution_sequence": execution_sequence,
        "profitable_execution_staging": execution_sequence,
        "net_formula": formula,
        "profitability": {"net_profit_usd": str(net_gain_usd), "passes_gate": passes},
        "identity": identity,
        "route_pair_id": identity["route_pair_id"],
        "quote_snapshot_id": identity["quote_snapshot_id"],
        "simulation_id": "",
        "execution_attempt_id": "",
        "transaction_hash": "",
        "opp_id": opp_id,
        "opportunity_id": opp_id,
    }
    row["unified_route_envelope"] = _unified_schema(route, row, fee_ledger, {"net_gain_usd": str(net_gain_usd)})
    return row


def build_stage_report(
    *,
    pools: dict[str, dict],
    rates: dict | None = None,
    principal_usd: Decimal = Decimal("10000"),
    hops: Iterable[int] = SUPPORTED_HOPS,
    base_tokens: Iterable[str] | None = None,
    stage_limit: int = 500,
    **_: Any,
) -> dict[str, Any]:
    if rates is None:
        try:
            from .ranker import compute_all_pool_rates
            rates = compute_all_pool_rates(pools)
        except Exception:
            rates = {}
    routes, stats = pre_rank_routes(rates, pools, principal_usd=principal_usd, hops=hops, base_tokens=base_tokens, max_quote_options_per_pair=max_quote_options_per_pair, max_token_paths=max_token_paths, max_pre_ranked=stage_limit)
    rows = [stage_pre_ranked_route(route, pools, requested_principal_usd=principal_usd) for route in routes[:stage_limit]]
    return {
        "schema_version": "omega_v5.route_execution_stage_report.v1",
        "execution_policy": "buy_lowest_executable_base_per_mid_then_sell_higher_back_to_base",
        "stats": stats,
        "rows": rows,
        "stage": {"attempted": len(rows), "ready_for_exact_call": sum(1 for r in rows if _row_ready_for_exact_call(r)), "staged_for_executor_truth": sum(1 for r in rows if _row_ready_for_exact_call(r))},
    }


def _parse_hops(value: str | Iterable[int] | None = None) -> tuple[int, ...]:
    if value is None:
        return SUPPORTED_HOPS
    if isinstance(value, str):
        return tuple(int(item.strip()) for item in value.split(",") if item.strip())
    return tuple(int(item) for item in value)


def run_once(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return build_stage_report(*args, **kwargs)

def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Omega route execution staging once.")
    parser.add_argument("--rpc-url", default="", help="Optional Polygon HTTP RPC override.")
    parser.add_argument("--principal", default="10000", help="Requested principal in USD.")
    parser.add_argument("--hops", default="2,3,4", help="Comma-separated hop counts to scan.")
    parser.add_argument("--base-token", action="append", default=None, help="Restrict scan to a base token; repeatable.")
    parser.add_argument("--stage-limit", type=int, default=100, help="Maximum pre-ranked routes to stage.")
    parser.add_argument("--max-token-paths", type=int, default=0, help="Maximum token paths to enumerate; 0 means uncapped.")
    parser.add_argument("--max-quote-options-per-pair", type=int, default=DEFAULT_MAX_QUOTE_OPTIONS_PER_PAIR, help="Maximum quote options per directional pair.")
    parser.add_argument("--print-top", type=int, default=10, help="Number of staged/rejected rows to print.")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.rpc_url:
        rpc_layer.w3 = Web3(Web3.HTTPProvider(args.rpc_url))
        rpc_layer.RPC_LIVE = rpc_layer.w3.is_connected()
        rpc_layer.BLOCK = rpc_layer.w3.eth.block_number if rpc_layer.RPC_LIVE else 0
    if not getattr(rpc_layer, "RPC_LIVE", False):
        print("route_execution_stage=FAIL reason=rpc_connect_false", flush=True)
        return 1

    pools = rpc_layer.load_all_live_pools(rpc_layer.DEEP_POOL_REGISTRY)
    if not pools:
        print(f"route_execution_stage=BLOCKED block={rpc_layer.BLOCK} reason=no_live_pools_loaded", flush=True)
        return 2

    try:
        from .ranker import compute_all_pool_rates

        rates = compute_all_pool_rates(pools)
    except Exception as exc:
        print(f"route_execution_stage=FAIL reason=rate_build_failed detail={type(exc).__name__}:{exc}", flush=True)
        return 1

    report = build_stage_report(
        pools=pools,
        rates=rates,
        principal_usd=_decimal(args.principal),
        hops=_parse_hops(args.hops),
        base_tokens=args.base_token,
        stage_limit=max(1, int(args.stage_limit)),
    )
    LATEST_STAGE_REPORT.parent.mkdir(parents=True, exist_ok=True)
    LATEST_STAGE_REPORT.write_text(json.dumps(_json_ready(report), indent=2, sort_keys=True), encoding="utf-8")
    with HISTORY_STAGE_REPORT.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_json_ready(report), sort_keys=True) + "\n")

    rows = list(report.get("rows") or [])
    staged = [row for row in rows if _row_ready_for_exact_call(row)]
    print(
        "route_execution_stage=OK "
        f"block={rpc_layer.BLOCK} "
        f"pools={len(pools)} "
        f"rate_pairs={len(rates)} "
        f"candidates={report.get('stats', {}).get('candidates_generated', 0)} "
        f"attempted={report.get('stage', {}).get('attempted', 0)} "
        f"ready_for_exact_call={len(staged)} "
        f"path={LATEST_STAGE_REPORT}",
        flush=True,
    )

    for idx, row in enumerate(rows[: max(0, int(args.print_top))], 1):
        seq = row.get("execution_sequence") or {}
        buy = ((seq.get("buy_leg") or {}).get("executable_buy_price_base_per_mid"))
        sell_min = ((seq.get("sell_leg") or {}).get("executable_sell_price_min_base_per_mid"))
        print(
            f"route_{idx} status={row.get('status')} "
            f"path={'->'.join(row.get('path') or [])} "
            f"net_usd={row.get('net_gain_usd')} "
            f"buy={buy} sell_min={sell_min} "
            f"reason={row.get('reason')} sanity={(row.get('hop_value_sanity') or {}).get('reason', '')}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())






