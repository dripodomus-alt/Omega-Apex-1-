#!/usr/bin/env python3
# ==============================================================================
# main.py  --  CLI orchestrator for the Omega V5 autonomous arbitrage engine
# ==============================================================================

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

# Windows consoles often default to cp1252; force UTF-8 when possible.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from .arbitrage import ArbitrageGraphEngine
from .config import ENABLE_LIQUIDATION_PIPELINE
from .rpc_layer import connect, load_all_live_pools, DEEP_POOL_REGISTRY
from .oracle_layer import refresh_token_prices, TOKEN_USD_PRICE
from .flash_loan import FlashSource
from .liquidity_registry import build_verified_pool_registry, registry_summary
from .opportunity_ranker import (
    LiveOpportunity,
    score_pegged_stable_spreads,
    score_cross_pool_spreads,
    score_opportunities,
    print_live_opportunities,
)
from .execution_truth import final_truth_rank, route_semantic_signature, truth_summary
from .execution import run_execution_loop, _await_next_block, execution_guard_status, execution_armed
from .route_execution_stager import PreRankedRoute
from . import route_execution_stager
from .ranker import compute_all_pool_rates, detect_cross_pool_two_leg_spreads
from .stable_strategies import detect_pegged_stable_spreads, spread_key
from .paths import output_path


def _apply_surplus_scan_config() -> dict[str, str]:
    """
    Min-out / min-profit settings that allow minimum -> maximum surplus capture.

    Discovery stays wide (tiny min net). Execution still applies real market
    slippage via amountOutMin = quoted_out * (1 - slippage_bps/10000).
    """
    defaults = {
        "MIN_NET_PROFIT_USD": "0.01",
        "MIN_PROFIT_TO_GAS_RATIO": "0",
        "RISK_BUFFER_USD": "0.10",
        "RELAY_TIP_USD": "0.10",
        "STABLE_MIN_NET_PROFIT_USD": "0.01",
        "STABLE_RISK_BUFFER_USD": "0.05",
        "DEFAULT_SLIPPAGE_BPS": "15",
        "MIN_AMOUNT_OUT_BPS": "0",
        "PREFERRED_FLASH_SOURCE": "Balancer_Vault",
        "OMEGA_TICKS": "25",
    }
    applied: dict[str, str] = {}
    for key, value in defaults.items():
        if not str(os.environ.get(key, "") or "").strip():
            os.environ[key] = value
            applied[key] = value
        else:
            applied[key] = str(os.environ.get(key))
    return applied


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="omega_v5",
        description="Omega V5 - Multi-protocol DeFi arbitrage engine for Polygon",
    )
    p.add_argument(
        "--ticks",
        type=int,
        default=int(os.environ.get("OMEGA_TICKS", "25") or "25"),
        help="Number of macro scan ticks to run (default: 25; 0 = infinite)",
    )
    p.add_argument(
        "--principal",
        "--principal-usd",
        dest="principal_usd",
        type=float,
        default=10_000,
        help="Flash-loan principal in USD (default: 10,000)",
    )
    p.add_argument(
        "--no-scan",
        action="store_true",
        help="Skip real-time scanner demo and go straight to arbitrage detection",
    )
    p.add_argument("--rpc-url", default="", help="HTTP RPC URL override for this run")
    p.add_argument(
        "--print-top-routes",
        type=int,
        default=50,
        help="Number of profitable ranked routes to print (default: 50)",
    )
    p.add_argument(
        "--execute-top",
        type=int,
        choices=[1, 5, 10, 15],
        default=5,
        help="Number of top ranked routes to stage/execute per cycle (default: 5)",
    )
    p.add_argument(
        "--canary-mode",
        action="store_true",
        help="Force exactly one staged/executed route while preserving execute-top batch size",
    )
    p.add_argument(
        "--slippage-bps",
        type=float,
        default=float(os.environ.get("DEFAULT_SLIPPAGE_BPS", "15") or "15"),
        help="Real-market slippage buffer in bps applied after math quotes (default: 15)",
    )
    return p.parse_args()


def _update_discovery_window_offset(cycle: int) -> None:
    window_size = int(os.environ.get("DISCOVERY_PAIR_WINDOW_SIZE", "0") or "0")
    if window_size > 0:
        os.environ["DISCOVERY_PAIR_WINDOW_OFFSET"] = str(cycle * window_size)
        print(
            f"   Discovery window offset updated for cycle {cycle}: "
            f"{os.environ['DISCOVERY_PAIR_WINDOW_OFFSET']}"
        )


def _raw_cycle_signature(candidate: Any) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if hasattr(candidate, "path") and hasattr(candidate, "edge_entries"):
        path = tuple(str(token) for token in getattr(candidate, "path", ()) or ())
        pools = tuple(
            str(edge.get("pool_id") or "")
            for edge in getattr(candidate, "edge_entries", ()) or ()
            if edge
        )
        return path, pools
    if isinstance(candidate, dict):
        path = tuple(str(token) for token in candidate.get("path", []) or [])
        pools = tuple(
            str(edge.get("pool_id") or "")
            for edge in candidate.get("edges", []) or []
            if edge
        )
        return path, pools
    if isinstance(candidate, PreRankedRoute):
        path = tuple(str(token) for token in getattr(candidate, "path", ()) or ())
        pools = tuple(
            str(edge.get("pool_id") or "")
            for edge in getattr(candidate, "edge_entries", ()) or ()
            if edge
        )
        return path, pools
    return (), ()


def _dedupe_raw_cycle_candidates(candidates: list[Any]) -> list[Any]:
    merged: list[Any] = []
    seen: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
    for candidate in candidates:
        signature = _raw_cycle_signature(candidate)
        if not signature[0] or signature in seen:
            continue
        seen.add(signature)
        merged.append(candidate)
    return merged


def _route_sig(path: Any, pools: Any) -> tuple[tuple[str, ...], tuple[str, ...]]:
    return (
        tuple(str(t) for t in (path or ())),
        tuple(str(p) for p in (pools or ())),
    )


def _json_ready(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_ready(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(v) for v in value]
    return value


def collect_and_score_opportunities(
    live_pools: dict,
    principal_usd: Decimal,
    *,
    slippage_bps: Decimal = Decimal("15"),
) -> tuple[list[LiveOpportunity], dict[tuple[tuple[str, ...], tuple[str, ...]], dict[str, Any]], list[dict[str, Any]]]:
    """
    Single logistics funnel for discovery + scoring.

    Returns:
      ranked_opps,
      pre_math_lookup[(path, pools)] -> pre-math stats,
      raw_positive_rows (all gross-rate > 1 candidates before net gate)
    """
    all_rates = compute_all_pool_rates(live_pools)

    two_leg_spreads = detect_cross_pool_two_leg_spreads(all_rates)
    stable_spreads = detect_pegged_stable_spreads(two_leg_spreads)
    stable_keys = {spread_key(item.spread) for item in stable_spreads}
    non_stable_two_leg = [s for s in two_leg_spreads if spread_key(s) not in stable_keys]

    arb_engine = ArbitrageGraphEngine(all_rates)
    bellman_cycles = arb_engine.bellman_ford_all_sources()

    staged_blueprints, pre_rank_stats = route_execution_stager.pre_rank_routes(
        all_rates,
        live_pools,
        principal_usd=principal_usd,
        hops=(2, 3, 4),
    )

    pre_math_lookup: dict[tuple[tuple[str, ...], tuple[str, ...]], dict[str, Any]] = {}
    raw_positive_rows: list[dict[str, Any]] = []

    print(f"   Pre-math blueprints found: {len(staged_blueprints)}")
    print(
        f"   Pre-math stats: "
        f"total_routes={pre_rank_stats.get('total_routes_considered', 0)} "
        f"raw_positive={pre_rank_stats.get('rejection_counts', {}).get('raw_positive_candidates', 0)} "
        f"rejections={pre_rank_stats.get('rejection_counts', {})}"
    )
    for bp in staged_blueprints:
        sig = _route_sig(bp.path, bp.pool_sequence)
        rate = Decimal(str(bp.approximate_gross_rate or "0"))
        raw_delta_usd = (rate - Decimal("1")) * principal_usd
        row = {
            "source": "stager_pre_math",
            "path": list(bp.path),
            "pool_sequence": list(bp.pool_sequence),
            "protocol_seq": list(bp.protocol_seq),
            "pre_math_gross_rate": str(rate),
            "raw_positive_delta_usd": str(raw_delta_usd),
            "raw_positive": bool(rate > Decimal("1")),
        }
        pre_math_lookup[sig] = row
        if rate > Decimal("1"):
            raw_positive_rows.append(row)
            if len(raw_positive_rows) <= 200:
                print(
                    f"     #{len(raw_positive_rows):03d} RAW_POS_DELTA "
                    f"path={'->'.join(bp.path)} "
                    f"rate={rate:.8f} "
                    f"raw_delta_usd={raw_delta_usd:.6f}"
                )

    for bp in staged_blueprints[: min(5, len(staged_blueprints))]:
        try:
            stage_res = route_execution_stager.stage_pre_ranked_route(
                bp,
                live_pools,
                requested_principal_usd=principal_usd,
                slippage_bps=slippage_bps,
            )
            if stage_res.get("status") == "staged_for_executor_truth":
                print(
                    f"   STAGED blueprint path={stage_res.get('path')} "
                    f"net_gain={stage_res.get('net_formula', {}).get('net_gain_usd')}"
                )
        except Exception as exc:
            print(f"   stage_preview_error={type(exc).__name__}: {exc}")

    cycle_candidates = _dedupe_raw_cycle_candidates([*staged_blueprints, *bellman_cycles])
    print(
        "   cycle_blueprints="
        f"stager:{len(staged_blueprints)} "
        f"bellman:{len(bellman_cycles)} "
        f"merged:{len(cycle_candidates)} "
        f"raw_positive:{len(raw_positive_rows)} "
        f"rejections:{pre_rank_stats.get('rejection_counts', {})}"
    )

    ranked_cycles = score_opportunities(
        cycle_candidates,
        live_pools,
        principal_usd=principal_usd,
        slippage_bps=slippage_bps,
    )
    ranked_two_leg = score_cross_pool_spreads(
        non_stable_two_leg,
        live_pools,
        principal_usd=principal_usd,
        slippage_bps=slippage_bps,
    )
    ranked_stable = score_pegged_stable_spreads(
        stable_spreads,
        live_pools,
        principal_usd=principal_usd,
        slippage_bps=slippage_bps,
    )
    print(
        f"   Post-math candidates: "
        f"cycles={len(ranked_cycles)} "
        f"two_leg={len(ranked_two_leg)} "
        f"stable={len(ranked_stable)}"
    )

    all_opps = ranked_stable + ranked_two_leg + ranked_cycles
    best_by_signature: dict[str, LiveOpportunity] = {}
    for op in all_opps:
        signature = route_semantic_signature(op)
        prev = best_by_signature.get(signature)
        if prev is None or op.profitability.net_profit_usd > prev.profitability.net_profit_usd:
            best_by_signature[signature] = op

    ranked = sorted(
        best_by_signature.values(),
        key=lambda x: x.profitability.net_profit_usd,
        reverse=True,
    )
    return ranked, pre_math_lookup, raw_positive_rows


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_json_ready(row), ensure_ascii=True) + "\n")


def _log_delta_accuracy(
    *,
    cycle: int,
    pre_math_lookup: dict[tuple[tuple[str, ...], tuple[str, ...]], dict[str, Any]],
    ranked_opps: list[LiveOpportunity],
    truth_ranked: list[LiveOpportunity],
    raw_positive_rows: list[dict[str, Any]],
    slippage_bps: Decimal,
    principal_usd: Decimal,
) -> None:
    print("STEP 3a: Delta Accuracy Analysis (Pre-Math vs Post-Slippage)")
    print(f"   raw_positive_pre_math={len(raw_positive_rows)} slippage_bps={slippage_bps}")

    delta_log = output_path("delta_accuracy_25_cycles.jsonl")
    latest_path = output_path("delta_accuracy_latest.json")

    comparisons: list[dict[str, Any]] = []

    for row in raw_positive_rows:
        path_t = tuple(row.get("path") or [])
        pools_t = tuple(row.get("pool_sequence") or [])
        sig = (path_t, pools_t)
        scored = next(
            (op for op in ranked_opps if _route_sig(op.path, op.pool_sequence) == sig),
            None,
        )
        truth = next(
            (op for op in truth_ranked if _route_sig(op.path, op.pool_sequence) == sig),
            None,
        )
        pre_math_profit = Decimal(str(row.get("raw_positive_delta_usd") or "0"))
        post_math = (
            Decimal(str(scored.profitability.net_profit_usd)) if scored is not None else None
        )
        post_truth = (
            Decimal(str(truth.profitability.net_profit_usd)) if truth is not None else None
        )
        comparison = {
            "cycle": cycle,
            "path": list(path_t),
            "pool_sequence": list(pools_t),
            "pre_math_gross_rate": row.get("pre_math_gross_rate"),
            "pre_math_raw_delta_usd": str(pre_math_profit),
            "post_math_slippage_net_usd": str(post_math) if post_math is not None else None,
            "post_truth_net_usd": str(post_truth) if post_truth is not None else None,
            "decay_pre_to_post_math_usd": (
                str(pre_math_profit - post_math) if post_math is not None else None
            ),
            "decay_pre_to_truth_usd": (
                str(pre_math_profit - post_truth) if post_truth is not None else None
            ),
            "slippage_bps": str(slippage_bps),
            "principal_usd": str(principal_usd),
            "passed_score_gate": scored is not None,
            "passed_truth_gate": truth is not None,
            "amount_out_min_mode": "quoted_out*(1-slippage_bps/10000)",
            "min_amount_out_bps": os.environ.get("MIN_AMOUNT_OUT_BPS", "0"),
            "min_net_profit_usd": os.environ.get("MIN_NET_PROFIT_USD", "0.01"),
        }
        comparisons.append(comparison)
        _append_jsonl(delta_log, comparison)

    printable = comparisons[:50]
    if not printable:
        print("   No raw-positive pre-math routes this cycle.")
    else:
        for item in printable:
            path_s = "->".join(item["path"])
            print(f"   - {path_s}")
            print(
                f"     Pre-Math dUSD: {item['pre_math_raw_delta_usd']} | "
                f"Post-Math/Slip: {item['post_math_slippage_net_usd']} | "
                f"Truth: {item['post_truth_net_usd']} | "
                f"Decay(pre->math): {item['decay_pre_to_post_math_usd']}"
            )

    latest = {
        "cycle": cycle,
        "raw_positive_count": len(raw_positive_rows),
        "scored_count": len(ranked_opps),
        "truth_count": len(truth_ranked),
        "slippage_bps": str(slippage_bps),
        "principal_usd": str(principal_usd),
        "comparisons_logged": len(comparisons),
        "log_path": str(delta_log),
        "top": comparisons[:20],
        "updated_at": time.time(),
    }
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(json.dumps(_json_ready(latest), indent=2), encoding="utf-8")
    print(f"   delta_log={delta_log}")
    print(f"   delta_latest={latest_path}")


async def run(
    ticks: int = 25,
    principal_usd: Decimal = Decimal("10000"),
    no_scan: bool = False,
    rpc_url: str = "",
    print_top_routes: int = 50,
    execute_top: int = 5,
    canary_mode: bool = False,
    slippage_bps: Decimal = Decimal("15"),
) -> None:
    """Full autonomous cycle: connect -> load pools -> scan -> rank -> arb -> stage."""
    from .gas_oracle import base_fee_gwei as _base_fee_gwei

    cfg = _apply_surplus_scan_config()
    print("")
    print("=" * 90)
    print("OMEGA V5 - Autonomous Multi-Protocol DeFi Arbitrage Engine (Chain 137)")
    print("=" * 90)
    print("")
    print("   SURPLUS_SCAN_CONFIG:")
    for key, value in cfg.items():
        print(f"     {key}={value}")
    print(f"   run_ticks={ticks} principal_usd={principal_usd} slippage_bps={slippage_bps}")
    print("")

    for i in range(ticks) if ticks > 0 else range(999_999_999):
        cycle_no = i + 1
        print(
            f"STEP 1: RPC Connection & State Load (Cycle {cycle_no}/{ticks or 'inf'})"
        )
        if not connect(http_urls=[rpc_url] if rpc_url else None, wss_url=None, prefer_wss=False):
            raise RuntimeError("RPC connection failed; production runtime refuses offline fallback")
        _update_discovery_window_offset(i)
        live_pools = load_all_live_pools(DEEP_POOL_REGISTRY)
        print(f"LIVE_POOLS ready: {len(live_pools)} pools")
        refresh_token_prices(force=True)
        print("")

        print(
            "   LIVE_FLAGS: LIVE_EXECUTION=%s SHADOW_MODE=%s EXECUTION_DISABLED=%s"
            % (
                os.environ.get("LIVE_EXECUTION", "false"),
                os.environ.get("SHADOW_MODE", "false"),
                os.environ.get("EXECUTION_DISABLED", "false"),
            )
        )
        print("   execution_armed=%s" % execution_armed())
        print("   guard_status=%s" % execution_guard_status())

        print("STEP 2: Opportunity Discovery & Ranking")
        ranked_opps, pre_math_lookup, raw_positive_rows = collect_and_score_opportunities(
            live_pools,
            principal_usd,
            slippage_bps=slippage_bps,
        )
        print(f"   Discovered {len(ranked_opps)} post-math/slippage opportunities.")
        print(f"   Raw-positive pre-math deltas logged: {len(raw_positive_rows)}")
        print_live_opportunities(ranked_opps, max_count=print_top_routes)
        print("")

        print("STEP 3: Executor-Truth Final Ranking")
        base_fee_gwei, base_fee_source = _base_fee_gwei()
        print(f"   gas_fee_source={base_fee_source} base_fee_gwei={base_fee_gwei}")
        truth_max_candidates = min(max(10, execute_top * 3), max(1, print_top_routes))
        truth_ranked, truth_results = final_truth_rank(
            ranked_opps,
            live_pools,
            base_fee_gwei=base_fee_gwei,
            max_candidates=truth_max_candidates,
        )
        summary = truth_summary(truth_results)
        print(
            f"   inspected={summary['inspected']} "
            f"executor_truth_executable={summary['executable']} "
            f"exact_calls={summary['exact_calls']} "
            f"rejection_classes={summary['rejection_classes']}"
        )
        if truth_ranked:
            print("   Final execution queue is exact-call backed and sorted by decoded executor profit.")
            print_live_opportunities(truth_ranked, max_count=print_top_routes)
        else:
            print("   No route passed executor exact-call truth at any tested size this cycle.")
        print("")

        _log_delta_accuracy(
            cycle=cycle_no,
            pre_math_lookup=pre_math_lookup,
            ranked_opps=ranked_opps,
            truth_ranked=truth_ranked,
            raw_positive_rows=raw_positive_rows,
            slippage_bps=slippage_bps,
            principal_usd=principal_usd,
        )
        print("")

        print("STEP 4: Execution Loop")
        await run_execution_loop(
            opportunities=truth_ranked,
            live_pools=live_pools,
            max_per_cycle=execute_top,
            canary_mode=canary_mode,
        )
        print("")

        if ticks > 1 and cycle_no < (ticks if ticks > 0 else cycle_no + 1):
            await _await_next_block()

    print("")
    print("=" * 90)
    print("OMEGA V5 - All autonomous cycles complete.")
    print(f"   Delta log: {output_path('delta_accuracy_25_cycles.jsonl')}")
    print(f"   Latest:    {output_path('delta_accuracy_latest.json')}")
    print("=" * 90)
    print("")


def main() -> None:
    _apply_surplus_scan_config()
    args = _parse_args()
    args.principal_usd = Decimal(str(args.principal_usd))
    args.slippage_bps = Decimal(str(args.slippage_bps))
    asyncio.run(
        run(
            ticks=args.ticks,
            principal_usd=args.principal_usd,
            no_scan=args.no_scan,
            rpc_url=args.rpc_url,
            print_top_routes=args.print_top_routes,
            execute_top=args.execute_top,
            canary_mode=args.canary_mode,
            slippage_bps=args.slippage_bps,
        )
    )


def _run_liquidation_scan(live_pools: dict) -> list:
    try:
        return AaveLiquidationScanner(live_pools).scan()
    except Exception as exc:
        print(f"   liquidation_lane=BLOCKED detail={type(exc).__name__}: {exc}")
        return []


if __name__ == "__main__":
    main()
