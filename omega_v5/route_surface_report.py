#!/usr/bin/env python3
# ==============================================================================
# route_surface_report.py -- route/edge coverage and raw-delta proof artifact.
# ==============================================================================

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from decimal import Decimal
from typing import Any

from . import rpc_layer
from .arbitrage import ArbitrageGraphEngine, detect_four_leg_cycles, detect_three_leg_cycles, merge_cycle_sets
from .config import ASSET_UNIVERSE, CHAIN_ID, HTTP_URL
from .execution import AdapterSemanticError, build_tx_payload, execution_guard_status
from .flash_loan import FlashSource
from .liquidity_registry import build_verified_pool_registry, registry_summary
from .opportunity_ranker import score_cross_pool_spreads, score_opportunities, score_pegged_stable_spreads
from .oracle_layer import PriceUnavailable, refresh_token_prices, token_price_usd
from .paths import output_path
from .pool_quality import route_quality_passed
from .ranker import CrossPoolSpread, compute_all_pool_rates, detect_cross_pool_two_leg_spreads
from .stable_strategies import detect_pegged_stable_spreads, spread_key


REPORT_PATH = output_path("route_surface_report_latest.json")
QUOTE_NOTIONAL = Decimal("1000")


def _json_ready(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(item) for item in value]
    return value


def _token_price(symbol: str) -> Decimal:
    try:
        return token_price_usd(symbol)
    except PriceUnavailable:
        return Decimal("0")


def _count_possible_two_leg_routes(rates: dict) -> dict[str, Any]:
    possible = 0
    pairs_with_reverse = 0
    pairs_with_distinct_liquidity = 0
    for (token_a, token_b), buy_quotes in rates.items():
        sell_quotes = rates.get((token_b, token_a), [])
        if not sell_quotes:
            continue
        pairs_with_reverse += 1
        pair_count = 0
        for buy in buy_quotes:
            for sell in sell_quotes:
                if buy.get("route_class") != "NATIVE_POOL_ROUTE" or sell.get("route_class") != "NATIVE_POOL_ROUTE":
                    continue
                if buy.get("liquidity_key") == sell.get("liquidity_key"):
                    continue
                pair_count += 1
        if pair_count:
            pairs_with_distinct_liquidity += 1
            possible += pair_count
    return {
        "two_leg_pairs_with_reverse_quotes": pairs_with_reverse,
        "two_leg_pairs_with_distinct_liquidity": pairs_with_distinct_liquidity,
        "two_leg_route_combinations_possible": possible,
    }


def raw_delta_for_spread(spread: CrossPoolSpread, amount_in: Decimal = QUOTE_NOTIONAL) -> dict[str, Any]:
    mid_out = amount_in * spread.buy_rate
    final_out = mid_out * spread.sell_rate
    raw_delta_base = final_out - amount_in
    price = _token_price(spread.path[0])
    raw_delta_usd = raw_delta_base * price if price > 0 else Decimal("0")
    return {
        "path": list(spread.path),
        "pool_sequence": list(spread.pool_sequence),
        "protocol_seq": list(spread.protocol_seq),
        "buy_pool_id": spread.buy_pool_id,
        "sell_pool_id": spread.sell_pool_id,
        "base_token": spread.path[0],
        "mid_token": spread.path[1],
        "amount_in_base": amount_in,
        "mid_out": mid_out,
        "final_out_base": final_out,
        "raw_delta_base": raw_delta_base,
        "raw_delta_usd": raw_delta_usd,
        "raw_delta_bps": (spread.round_trip_rate - Decimal("1")) * Decimal("10000"),
        "round_trip_rate": spread.round_trip_rate,
        "gross_profit_pct": spread.gross_profit_pct,
        "cross_protocol": spread.cross_protocol,
        "cross_invariant": spread.cross_invariant,
        "formula": "raw_delta_base = amount_in_base * buy_rate * sell_rate - amount_in_base",
    }


def _raw_cycle_row(cycle: dict, amount_in: Decimal = QUOTE_NOTIONAL) -> dict[str, Any]:
    cumulative = Decimal(str(cycle.get("cumulative_rate", "0") or "0"))
    path = list(cycle.get("path") or [])
    base = path[0] if path else ""
    raw_delta_base = (amount_in * cumulative) - amount_in
    price = _token_price(base) if base else Decimal("0")
    return {
        "path": path,
        "pool_sequence": [edge.get("pool_id", "") for edge in cycle.get("edges", []) if edge],
        "protocol_seq": [edge.get("protocol", "") for edge in cycle.get("edges", []) if edge],
        "base_token": base,
        "amount_in_base": amount_in,
        "final_out_base": amount_in * cumulative,
        "raw_delta_base": raw_delta_base,
        "raw_delta_usd": raw_delta_base * price if price > 0 else Decimal("0"),
        "raw_delta_bps": (cumulative - Decimal("1")) * Decimal("10000"),
        "cumulative_rate": cumulative,
        "detector": cycle.get("detector", "BELLMAN_CYCLE"),
        "formula": "raw_delta_base = amount_in_base * cumulative_rate - amount_in_base",
    }


def _top_rows(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda item: (
            Decimal(str(item.get("raw_delta_usd") or "0")),
            Decimal(str(item.get("raw_delta_bps") or "0")),
        ),
        reverse=True,
    )[:limit]


def _cycle_execution_candidate(cycle: dict, pools: dict[str, dict]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    edges = [edge for edge in cycle.get("edges", []) if edge]
    pool_sequence = [str(edge.get("pool_id", "")) for edge in edges]
    if not pool_sequence:
        reasons.append("missing_pool_sequence")
        return False, reasons
    if any(pool_id not in pools for pool_id in pool_sequence):
        reasons.append("missing_live_pool")
    liquidity_keys = [
        pools[pool_id].get("liquidity_key", pool_id)
        for pool_id in pool_sequence
        if pool_id in pools
    ]
    if len(liquidity_keys) != len(pool_sequence) or len(set(liquidity_keys)) != len(liquidity_keys):
        reasons.append("duplicate_or_missing_liquidity_key")
    if any((pools.get(pool_id, {}).get("route_class", "NATIVE_POOL_ROUTE") != "NATIVE_POOL_ROUTE") for pool_id in pool_sequence):
        reasons.append("non_native_route_class")
    if not route_quality_passed(pool_sequence, pools):
        reasons.append("pool_quality_gate_failed")
    path = list(cycle.get("path") or [])
    if len(path) < 3 or path[0] != path[-1]:
        reasons.append("path_not_closed")
    if len(pool_sequence) != max(0, len(path) - 1):
        reasons.append("pool_hop_count_mismatch")
    return not reasons, reasons


def _assets_from_pools(pools: dict[str, dict]) -> set[str]:
    assets: set[str] = set()
    for pool in pools.values():
        assets.update(str(token) for token in pool.get("tokens") or [])
    return {asset for asset in assets if asset}


def _mid_tokens_from_routes(two_leg: list[CrossPoolSpread], cycles: list[dict]) -> set[str]:
    mids = {spread.path[1] for spread in two_leg if len(spread.path) >= 3}
    for cycle in cycles:
        path = list(cycle.get("path") or [])
        if len(path) > 2:
            mids.update(path[1:-1])
    return {token for token in mids if token}


def _calldata_probe(ranked: list, max_candidates: int) -> dict[str, Any]:
    attempts = []
    buildable = 0
    for op in ranked[:max(0, max_candidates)]:
        try:
            tx = build_tx_payload(op, nonce=0, base_fee_gwei=Decimal("50"), allow_pool_target_fallback=False)
            buildable += 1
            attempts.append({
                "opp_id": op.opp_id,
                "path": list(op.path),
                "strategy": op.strategy,
                "buildable": True,
                "to": tx.get("to", ""),
                "selector": str(tx.get("data", ""))[:10],
            })
        except AdapterSemanticError as exc:
            attempts.append({
                "opp_id": op.opp_id,
                "path": list(op.path),
                "strategy": op.strategy,
                "buildable": False,
                "reason": "adapter_semantics",
                "detail": str(exc)[:300],
            })
        except Exception as exc:
            attempts.append({
                "opp_id": op.opp_id,
                "path": list(op.path),
                "strategy": op.strategy,
                "buildable": False,
                "reason": type(exc).__name__,
                "detail": str(exc)[:300],
            })
    return {
        "attempted": len(attempts),
        "buildable": buildable,
        "failed": len(attempts) - buildable,
        "attempts": attempts,
        "note": "calldata build only; no signing, no broadcast",
    }


def build_route_surface_report(*, rpc_url: str = "", top: int = 25, calldata_probe: int = 5) -> dict[str, Any]:
    started = time.time()
    if not rpc_layer.connect(http_urls=[rpc_url or HTTP_URL], wss_url="", prefer_wss=False):
        raise RuntimeError("RPC connection failed")

    pools = rpc_layer.load_all_live_pools(rpc_layer.DEEP_POOL_REGISTRY)
    refresh_token_prices(force=True)
    rates = compute_all_pool_rates(pools)
    two_leg_spreads = detect_cross_pool_two_leg_spreads(rates)
    stable_spreads = detect_pegged_stable_spreads(two_leg_spreads)
    stable_keys = {spread_key(item.spread) for item in stable_spreads}
    non_stable_two_leg = [
        spread for spread in two_leg_spreads
        if spread_key(spread) not in stable_keys
    ]

    graph = ArbitrageGraphEngine(rates)
    bellman_cycles = graph.bellman_ford_all_sources()
    three_leg_cycles = detect_three_leg_cycles(rates)
    four_leg_cycles = detect_four_leg_cycles(rates)
    cycles = merge_cycle_sets(bellman_cycles, three_leg_cycles, four_leg_cycles)

    ranked_cycles = score_opportunities(cycles, pools, rates, principal_usd=Decimal("10000"), flash_source=FlashSource.BALANCER)
    ranked_two_leg = score_cross_pool_spreads(non_stable_two_leg, pools, principal_usd=Decimal("10000"), flash_source=FlashSource.BALANCER)
    ranked_stable = score_pegged_stable_spreads(stable_spreads, pools, principal_usd=Decimal("10000"), flash_source=FlashSource.BALANCER)
    ranked = sorted(
        ranked_stable + ranked_two_leg + ranked_cycles,
        key=lambda item: item.profitability.net_profit_usd,
        reverse=True,
    )

    raw_two_leg = [raw_delta_for_spread(spread) for spread in two_leg_spreads]
    raw_cycles = []
    execution_candidate_cycles = []
    rejected_cycle_reasons: Counter[str] = Counter()
    for cycle in cycles:
        row = _raw_cycle_row(cycle)
        candidate_ok, reject_reasons = _cycle_execution_candidate(cycle, pools)
        row["execution_candidate"] = candidate_ok
        row["candidate_reject_reasons"] = reject_reasons
        raw_cycles.append(row)
        if candidate_ok:
            execution_candidate_cycles.append(row)
        else:
            for reason in reject_reasons:
                rejected_cycle_reasons[reason] += 1
    discovered_assets = _assets_from_pools(pools)
    mid_tokens = _mid_tokens_from_routes(two_leg_spreads, cycles)
    registry_rows = build_verified_pool_registry(pools)

    report = {
        "ok": True,
        "mode": "read_only_no_broadcast",
        "chain_id": CHAIN_ID,
        "block": rpc_layer.BLOCK,
        "elapsed_seconds": Decimal(str(round(time.time() - started, 3))),
        "asset_universe_configured": {
            "flash_capital_assets": list(ASSET_UNIVERSE.flash_capital_assets),
            "base_route_assets": list(ASSET_UNIVERSE.base_route_assets),
            "mid_token_assets": list(ASSET_UNIVERSE.mid_token_assets),
            "swappable_assets": list(ASSET_UNIVERSE.swappable_assets),
            "pool_state_assets": list(ASSET_UNIVERSE.pool_state_assets),
            "price_assets": list(ASSET_UNIVERSE.price_assets),
            "counts": {
                "flash_capital": len(ASSET_UNIVERSE.flash_capital_assets),
                "base_route": len(ASSET_UNIVERSE.base_route_assets),
                "mid_token": len(ASSET_UNIVERSE.mid_token_assets),
                "swappable": len(ASSET_UNIVERSE.swappable_assets),
                "pool_state": len(ASSET_UNIVERSE.pool_state_assets),
                "price": len(ASSET_UNIVERSE.price_assets),
            },
            "runtime_token_registry_count": len(rpc_layer.TOKEN_ADDRESSES),
        },
        "discovered_assets": {
            "pool_asset_count": len(discovered_assets),
            "pool_assets": sorted(discovered_assets),
            "mid_token_asset_count": len(mid_tokens),
            "mid_token_assets": sorted(mid_tokens),
        },
        "asset_pools": {
            "base_registry_size": len(rpc_layer.DEEP_POOL_REGISTRY),
            "loaded_rankable_pools": len(pools),
            "protocol_counts": dict(Counter(pool.get("protocol") for pool in pools.values())),
            "verified_registry_rows": len(registry_rows),
            "verified_registry_summary": registry_summary(registry_rows),
            "discovery_stats": {
                "factory": rpc_layer.FACTORY_DISCOVERY_STATS,
                "polygon_token_list": rpc_layer.POLYGON_TOKEN_LIST_DISCOVERY_STATS,
                "dynamic_pool_registry": rpc_layer.DYNAMIC_POOL_REGISTRY_STATS,
                "curve_pool_registry": rpc_layer.CURVE_POOL_REGISTRY_STATS,
                "subgraph_pool_intel": rpc_layer.SUBGRAPH_POOL_INTEL_STATS,
            },
            "quality": rpc_layer.LAST_POOL_QUALITY_STATS,
        },
        "opportunity_route_surface": {
            "rate_pairs": len(rates),
            "directional_quotes": sum(len(items) for items in rates.values()),
            "possible": _count_possible_two_leg_routes(rates),
            "raw_positive_two_leg": len(two_leg_spreads),
            "raw_positive_stable": len(stable_spreads),
            "raw_positive_cycles_all": len(cycles),
            "raw_positive_cycles_execution_candidates": len(execution_candidate_cycles),
            "raw_positive_cycle_reject_reasons": dict(rejected_cycle_reasons),
            "bellman_cycles": len(bellman_cycles),
            "explicit_three_leg_cycles": len(three_leg_cycles),
            "explicit_four_leg_cycles": len(four_leg_cycles),
            "net_gate_passed": {
                "stable": len(ranked_stable),
                "two_leg": len(ranked_two_leg),
                "cycles": len(ranked_cycles),
                "total": len(ranked),
            },
        },
        "raw_delta_leaderboard": {
            "notional_base_amount": str(QUOTE_NOTIONAL),
            "two_leg_top": _top_rows(raw_two_leg, top),
            "cycle_top_all": _top_rows(raw_cycles, top),
            "cycle_top_execution_candidates": _top_rows(execution_candidate_cycles, top),
        },
        "calldata_success_surface": _calldata_probe(ranked, calldata_probe),
        "accuracy_and_revert_risk_controls": {
            "pool_quality_gate": rpc_layer.LAST_POOL_QUALITY_STATS,
            "execution_guards": execution_guard_status(probe=False),
            "submission_policy": "no signing and no broadcast from this report",
            "revert_prevention_order": [
                "canonical token address audit",
                "on-chain decimals/reserve/liquidity audit",
                "distinct liquidity key check",
                "quote math and size ladder",
                "net-profit and impact gates",
                "adapter semantic calldata build",
                "fork/exact-call truth before live submission",
            ],
        },
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(_json_ready(report), indent=2, sort_keys=True), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Omega route surface and raw-delta report.")
    parser.add_argument("--rpc-url", default="", help="HTTP RPC URL override.")
    parser.add_argument("--top", type=int, default=25, help="Top raw-delta rows to persist.")
    parser.add_argument("--calldata-probe", type=int, default=5, help="Ranked net-gated calldata build attempts.")
    args = parser.parse_args()
    report = build_route_surface_report(rpc_url=args.rpc_url, top=max(1, args.top), calldata_probe=max(0, args.calldata_probe))
    surface = report["opportunity_route_surface"]
    print(
        "route_surface_report=OK "
        f"assets={report['discovered_assets']['pool_asset_count']} "
        f"pools={report['asset_pools']['loaded_rankable_pools']} "
        f"quotes={surface['directional_quotes']} "
        f"raw_two_leg={surface['raw_positive_two_leg']} "
        f"raw_cycles_all={surface['raw_positive_cycles_all']} "
        f"raw_cycles_exec={surface['raw_positive_cycles_execution_candidates']} "
        f"net_passed={surface['net_gate_passed']['total']} "
        f"path={REPORT_PATH}",
        flush=True,
    )


if __name__ == "__main__":
    main()
