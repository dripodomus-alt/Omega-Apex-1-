#!/usr/bin/env python3
"""
run_benchmark.py -- stage-only profitable execution benchmark.

The benchmark intentionally stops at staging/truth-prep. It does not sign or
broadcast transactions. Its scoring invariant is explicit: buy the mid token at
the lowest executable base-per-mid price first, then sell back to the base asset
only when the executable sell price is higher.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from omega_v5 import route_execution_stager as stager  # noqa: E402
from omega_v5.paths import output_path  # noqa: E402
from omega_v5.ranker import compute_all_pool_rates  # noqa: E402
from omega_v5.route_execution_stager import build_stage_report  # noqa: E402


TOKEN_PRICES = {
    "USDC": Decimal("1"),
    "USDT": Decimal("1"),
    "DAI": Decimal("1"),
    "WETH": Decimal("3345"),
    "WBTC": Decimal("67500"),
}


def _json_ready(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


def _v2_pool(tokens: tuple[str, str], reserves: tuple[str, str], address_tail: int) -> dict[str, Any]:
    return {
        "protocol": "UniswapV2",
        "tokens": list(tokens),
        "reserves": [Decimal(reserves[0]), Decimal(reserves[1])],
        "fee": Decimal("0.003"),
        "fee_bps": Decimal("30"),
        "route_class": "NATIVE_POOL_ROUTE",
        "liquidity_key": f"{tokens[0]}:{tokens[1]}:{address_tail}",
        "address": "0x" + f"{address_tail:040x}"[-40:],
        "total_executable_liquidity_usd": Decimal("1000000000"),
    }


def _synthetic_pools() -> dict[str, dict[str, Any]]:
    return {
        # Best buy: lowest USDC per WETH, because 1 USDC buys more WETH here.
        "BUY_LOW_USDC_WETH": _v2_pool(("USDC", "WETH"), ("1000000000", "330000"), 1),
        # Worse buy pool. The pre-rank stage should remove this buy option.
        "BUY_HIGH_USDC_WETH": _v2_pool(("USDC", "WETH"), ("1000000000", "290000"), 2),
        # Sell leg returns more USDC per WETH than the selected buy leg costs.
        "SELL_HIGH_WETH_USDC": _v2_pool(("WETH", "USDC"), ("300000", "1040000000"), 3),
        # Extra non-conflicting pair keeps conflict staging behavior exercised.
        "BUY_LOW_USDC_WBTC": _v2_pool(("USDC", "WBTC"), ("1000000000", "16000"), 4),
        "SELL_HIGH_WBTC_USDC": _v2_pool(("WBTC", "USDC"), ("15000", "1030000000"), 5),
    }


def _load_pools(path: str = "") -> dict[str, dict[str, Any]]:
    if not path:
        return _synthetic_pools()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _token_price_usd(symbol: str) -> Decimal:
    return TOKEN_PRICES.get(str(symbol), Decimal("1"))


def run_benchmark(args: argparse.Namespace) -> dict[str, Any]:
    pools = _load_pools(args.pools_json)
    stager.token_price_usd = _token_price_usd
    rates = compute_all_pool_rates(pools)
    cycles: list[dict[str, Any]] = []
    for cycle in range(1, args.cycles + 1):
        report = build_stage_report(
            pools=pools,
            rates=rates,
            principal_usd=Decimal(str(args.principal_usd)),
            stage_limit=args.max_parallel_tx,
            hops=(2,),
            max_quote_options_per_pair=0,
            max_pre_ranked=args.max_pre_ranked,
            base_tokens=["USDC"],
            slippage_bps=Decimal(str(args.slippage_bps)),
        )
        routes = report.get("routes", [])
        eligible = [row for row in routes if row.get("status") == "staged_for_executor_truth"]
        cycles.append({
            "cycle": cycle,
            "stage": report.get("stage", {}),
            "pre_rank": report.get("pre_rank", {}),
            "eligible_routes": len(eligible),
            "top_routes": routes[: args.print_top],
        })

    result = {
        "schema_version": "omega_v5.benchmark.profitable_execution.v1",
        "mode": args.mode,
        "submission_policy": "stage_only_no_signing_no_broadcast",
        "execution_policy": "buy_lowest_executable_base_per_mid_then_sell_higher_back_to_base",
        "cycles_requested": args.cycles,
        "generated_at_ns": time.time_ns(),
        "cycles": cycles,
    }
    output = output_path("benchmark_profitable_execution_latest.json")
    output.write_text(json.dumps(_json_ready(result), indent=2), encoding="utf-8")
    result["output_path"] = str(output)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the profitable execution staging benchmark.")
    parser.add_argument("--mode", choices=("anvil", "live", "dry-run"), default="dry-run")
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--max-parallel-tx", type=int, default=8)
    parser.add_argument("--min-profit-usd", type=Decimal, default=Decimal("0.001"))
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--confirm-live-fire", action="store_true")
    parser.add_argument("--principal-usd", type=Decimal, default=Decimal("10000"))
    parser.add_argument("--slippage-bps", type=Decimal, default=Decimal("10"))
    parser.add_argument("--max-pre-ranked", type=int, default=100)
    parser.add_argument("--print-top", type=int, default=5)
    parser.add_argument("--pools-json", default="", help="Optional pool JSON file. Defaults to deterministic synthetic pools.")
    args = parser.parse_args(argv)

    if args.mode == "live" and not args.confirm_live_fire:
        print("live mode requires --confirm-live-fire")
        return 2
    if args.cycles <= 0:
        print("cycles must be positive")
        return 2

    result = run_benchmark(args)
    total_eligible = sum(int(cycle.get("eligible_routes", 0)) for cycle in result["cycles"])
    print("Omega V5 profitable execution staging benchmark")
    print(f"mode={result['mode']} cycles={result['cycles_requested']} eligible_routes={total_eligible}")
    print(f"policy={result['execution_policy']}")
    print(f"submission_policy={result['submission_policy']}")
    print(f"report={result['output_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())