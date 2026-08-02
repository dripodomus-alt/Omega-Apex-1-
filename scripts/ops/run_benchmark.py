#!/usr/bin/env python3
"""
run_benchmark.py - High-performance SDK-driven execution benchmark orchestrator.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from omega_v5 import config  # noqa: E402
from omega_v5 import route_execution_stager as stager  # noqa: E402
from omega_v5.execution import sdk_core  # noqa: E402
from omega_v5.paths import output_path  # noqa: E402
from omega_v5.ranker import compute_all_pool_rates  # noqa: E402
from omega_v5.route_execution_stager import build_stage_report  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger(__name__)


TOKEN_PRICES = {
    "USDC": Decimal("1"),
    "USDT": Decimal("1"),
    "DAI": Decimal("1"),
    "WETH": Decimal("3345"),
    "WBTC": Decimal("67500"),
}

def _get_env_or_fail(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise ValueError(f"Required environment variable '{key}' is not set.")
    return value

def _json_ready(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


def format_top_route_summary(routes: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    """Return a compact summary for the top routes for logging and reporting."""
    summaries = []
    for row in routes[:limit]:
        profitability = row.get("profitability") or {}
        if isinstance(profitability, dict):
            net_profit_usd = profitability.get("net_profit_usd")
        else:
            net_profit_usd = getattr(profitability, "net_profit_usd", None)

        summaries.append(
            {
                "opp_id": row.get("opp_id") or row.get("route_id") or "unknown",
                "status": row.get("status"),
                "net_profit_usd": str(net_profit_usd) if net_profit_usd is not None else None,
                "path": row.get("path") or [],
            }
        )
    return summaries


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


def run_orchestrator(args: argparse.Namespace) -> dict[str, Any]:
    """Main orchestrator for discovery, staging, and execution."""
    pools = _load_pools(args.pools_json)
    stager.token_price_usd = _token_price_usd
    rates = compute_all_pool_rates(pools)
    cycles: list[dict[str, Any]] = []

    for cycle_num in range(1, args.cycles + 1):
        report = build_stage_report(
            pools=pools,
            rates=rates,
            principal_usd=Decimal(str(args.principal_usd)),
            stage_limit=args.max_parallel_tx,
            hops=(2,),
            max_pre_ranked=args.max_pre_ranked,
            base_tokens=["USDC"],
        )
        routes = report.get("routes", [])
        staged_routes = [
            row for row in routes if row.get("status") == "staged_for_executor_truth"
        ]

        cycle_result = {
            "cycle": cycle_num,
            "stage": report.get("stage", {}),
            "pre_rank": report.get("pre_rank", {}),
            "staged_routes_count": len(staged_routes),
            "top_staged_routes": format_top_route_summary(staged_routes, limit=args.print_top),
            "submissions": [],
            "receipts": [],
        }

        logger.info(
            "Cycle %s: staged=%s, top_routes=%s",
            cycle_num,
            len(staged_routes),
            json.dumps(cycle_result["top_staged_routes"], default=str),
        )

        if args.mode in ("live", "anvil") and staged_routes:
            logger.info(f"Cycle {cycle_num}: Found {len(staged_routes)} routes to execute.")
            rpc_url = (
                config.BROADCAST_RPC_URL if args.mode == "live" else config.FORK_RPC_URL
            )
            private_key = _get_env_or_fail("EXECUTOR_PRIVATE_KEY")
            executor_address = config.C1_PAYLOAD_TARGET

            w3 = sdk_core.get_web3_instance(rpc_url)
            chain_id = w3.eth.chain_id

            submissions = sdk_core.submit_staged_routes(
                staged_routes, w3, private_key, chain_id, executor_address
            )
            cycle_result["submissions"] = submissions

            if submissions:
                receipt_results = sdk_core.wait_for_receipts(
                    w3, submissions, args.timeout
                )
                cycle_result["receipts"] = receipt_results
        else:
            logger.info(
                f"Cycle {cycle_num}: Mode is '{args.mode}'. "
                f"Found {len(staged_routes)} staged routes. No execution will be performed."
            )

        cycles.append(cycle_result)

    result = {
        "schema_version": "omega_v5.benchmark.sdk_orchestrator.v1",
        "mode": args.mode,
        "submission_policy": (
            "sdk_sign_and_broadcast"
            if args.mode in ("live", "anvil")
            else "stage_only_no_broadcast"
        ),
        "cycles_requested": args.cycles,
        "generated_at_ns": time.time_ns(),
        "cycles": cycles,
    }
    output = output_path("sdk_benchmark_latest.json")
    output.write_text(json.dumps(_json_ready(result), indent=2), encoding="utf-8")
    result["output_path"] = str(output)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the profitable execution staging benchmark.")
    parser.add_argument("--mode", choices=("anvil", "live", "dry_run"), default="dry_run")
    parser.add_argument("--cycles", type=int, default=10, help="Number of benchmark cycles to run.")
    parser.add_argument("--max-parallel-tx", type=int, default=16, help="Maximum number of non-conflicting routes to stage per cycle.")
    parser.add_argument("--min-profit-usd", type=float, default=0.01)
    parser.add_argument("--timeout", type=int, default=30, help="Timeout in seconds for waiting for transaction receipts.")
    parser.add_argument("--confirm-live-fire", action="store_true")
    parser.add_argument("--principal-usd", type=Decimal, default=Decimal("10000"))
    parser.add_argument("--slippage-bps", type=Decimal, default=Decimal("10"))
    parser.add_argument("--max-pre-ranked", type=int, default=500, help="Maximum number of routes to consider in the pre-ranking stage.")
    parser.add_argument("--print-top", type=int, default=5)
    parser.add_argument("--pools-json", default="", help="Optional pool JSON file. Defaults to deterministic synthetic pools.")
    args = parser.parse_args(argv)

    if args.mode == "live" and not args.confirm_live_fire:
        logger.error("FATAL: Live mode requires the '--confirm-live-fire' flag.")
        return 2
    if args.cycles <= 0:
        logger.error("FATAL: --cycles must be a positive integer.")
        return 2

    result = run_orchestrator(args)
    total_staged = sum(int(cycle.get("staged_routes_count", 0)) for cycle in result["cycles"])
    total_submitted = sum(len(cycle.get("submissions", [])) for cycle in result["cycles"])
    total_receipts = sum(len(cycle.get("receipts", [])) for cycle in result["cycles"])

    logger.info("=" * 50)
    logger.info("SDK Benchmark Orchestrator Summary")
    logger.info(f"Mode: {result['mode']}, Cycles: {result['cycles_requested']}")
    logger.info(f"Total Staged: {total_staged}, Total Submitted: {total_submitted}, Total Receipts: {total_receipts}")
    logger.info(f"Submission Policy: {result['submission_policy']}")
    logger.info(f"Full report saved to: {result['output_path']}")
    logger.info("=" * 50)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())