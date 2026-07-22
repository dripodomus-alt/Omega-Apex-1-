#!/usr/bin/env python3
# ==============================================================================
# truth_scan.py -- fast exact-call-backed route eligibility scan.
# ==============================================================================

from __future__ import annotations

import argparse
from decimal import Decimal
from typing import Iterable

from . import rpc_layer
from .arbitrage import ArbitrageGraphEngine, detect_four_leg_cycles, detect_three_leg_cycles, merge_cycle_sets
from .execution_truth import final_truth_rank, truth_summary
from .flash_loan import FlashSource
from .opportunity_ranker import score_cross_pool_spreads, score_opportunities, score_pegged_stable_spreads
from .oracle_layer import refresh_token_prices
from .ranker import compute_all_pool_rates, detect_cross_pool_two_leg_spreads
from .rpc_layer import DEEP_POOL_REGISTRY
from .stable_strategies import detect_pegged_stable_spreads, spread_key


def scan(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Exact-call-backed final route truth scan")
    parser.add_argument("--rpc-url", default="", help="Polygon RPC URL")
    parser.add_argument("--principal", default="50000", help="Requested principal USD")
    parser.add_argument("--max-opps", type=int, default=50, help="Top ranked routes to truth-test")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not rpc_layer.connect(http_urls=[args.rpc_url] if args.rpc_url else None, wss_url="", prefer_wss=False):
        print("truth_scan=FAIL reason=rpc_connect_false", flush=True)
        return 1
    print(f"truth_scan_rpc=OK block={rpc_layer.BLOCK}", flush=True)

    pools = rpc_layer.load_all_live_pools(DEEP_POOL_REGISTRY)
    print(f"truth_scan_pools={len(pools)}", flush=True)
    if not pools:
        print("truth_scan=BLOCKED reason=no_live_pools_loaded rpc_capacity_or_archive_state_unavailable", flush=True)
        return 2
    refresh_token_prices(force=True)
    rates = compute_all_pool_rates(pools)
    two_leg = detect_cross_pool_two_leg_spreads(rates)
    stable = detect_pegged_stable_spreads(two_leg)
    stable_keys = {spread_key(item.spread) for item in stable}
    non_stable = [spread for spread in two_leg if spread_key(spread) not in stable_keys]
    engine = ArbitrageGraphEngine(rates)
    cycles = merge_cycle_sets(
        engine.bellman_ford_all_sources(),
        detect_three_leg_cycles(rates),
        detect_four_leg_cycles(rates),
    )
    principal = Decimal(str(args.principal))
    ranked = sorted(
        score_pegged_stable_spreads(stable, pools, principal, FlashSource.BALANCER)
        + score_cross_pool_spreads(non_stable, pools, principal, FlashSource.BALANCER)
        + score_opportunities(cycles, pools, rates, principal, FlashSource.BALANCER),
        key=lambda item: item.profitability.net_profit_usd,
        reverse=True,
    )
    print(f"truth_scan_theoretical_ranked={len(ranked)}", flush=True)

    try:
        from .gas_oracle import base_fee_gwei as _base_fee_gwei

        base_fee_gwei, gas_fee_source = _base_fee_gwei()
        print(f"truth_scan_gas_fee_source={gas_fee_source} base_fee_gwei={base_fee_gwei}", flush=True)
    except Exception as exc:
        print(f"truth_scan=BLOCKED reason=gas_price_read_failed detail={type(exc).__name__}: {exc}", flush=True)
        return 2
    executable, results = final_truth_rank(
        ranked,
        pools,
        base_fee_gwei=base_fee_gwei,
        max_candidates=max(1, args.max_opps),
    )
    summary = truth_summary(results)
    print(
        f"truth_scan_executor_executable={summary['executable']} "
        f"inspected={summary['inspected']} "
        f"rejections={summary['rejection_classes']}",
        flush=True,
    )
    for idx, row in enumerate(results[:10], 1):
        print(
            f"truth_result_{idx}=opp:{row.original.opp_id} "
            f"path:{'->'.join(row.original.path)} "
            f"executable:{row.executable} "
            f"selected_size:{row.selected_size_usd or 'NONE'} "
            f"tested:{','.join(row.tested_sizes_usd)} "
            f"reject:{row.rejection_class or 'NONE'}",
            flush=True,
        )
    for idx, op in enumerate(executable[:10], 1):
        print(
            f"truth_executable_{idx}=opp:{op.opp_id} "
            f"path:{'->'.join(op.path)} "
            f"net_usd:{op.profitability.net_profit_usd} "
            f"principal_usd:{op.profitability.flashloan.principal_usd}",
            flush=True,
        )
    print("truth_scan=PASS", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(scan())
