#!/usr/bin/env python3
"""
25-Cycle Dry Run Simulator
- Generates synthetic opportunities.
- Applies ranking using the canonical raw gate.
- Emits a structured shadow report with discovery, execution, and profitability metrics.
- Writes the report to `out/dry_run_shadow_report.json`.

Live mode:
    OMEGA_LIVE_TEST=1 python tests/dry_run_25_cycles.py
    (will attempt real discovery when possible)
"""

import json
import os
import sys
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import SimpleNamespace
from typing import Any, List

# Ensure the main project is in the path to import production logic
ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "out" / "imports" / "backend_review" / "backend"
for path in (str(ROOT_DIR), str(BACKEND_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

try:
    from omega_v5.execution import revalidate_profitability_at_broadcast
except ImportError:  # pragma: no cover - fallback for minimal environments
    def revalidate_profitability_at_broadcast(op: Any, payload: dict[str, Any]) -> bool:
        net_profit = getattr(getattr(op, "profitability", None), "net_profit_usd", None)
        if net_profit is None:
            return False
        try:
            return Decimal(str(net_profit)) >= Decimal("5.0")
        except (ValueError, TypeError):
            return bool(net_profit)

try:
    from omega_v5.opportunity_ranker import LiveOpportunity, find_opportunities
except Exception:  # pragma: no cover
    class LiveOpportunity:  # type: ignore[override]
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

LIVE_MODE = bool(os.getenv("OMEGA_LIVE_TEST") or os.getenv("LIVE_TEST_RPC_URL"))


def _discover_live_opportunities() -> List[Any]:
    """Use the live coefficient engine to discover opportunities from current Polygon market state."""
    engine_strategy = os.getenv('ENGINE_STRATEGY', 'FULL_ARB').upper()

    try:
        if engine_strategy == 'COEFFICIENT':
            print("🚦 Using COEFFICIENT engine for live discovery...")
            from coefficient_arbitrage_engine import get_coefficient_engine
            engine = get_coefficient_engine()
            scan_method = "scan_for_coefficient_opportunities"
        else:
            print("🚦 Using FULL_ARB engine for live discovery...")
            from arbitrage_engine import get_arbitrage_engine
            engine = get_arbitrage_engine()
            scan_method = "scan_for_spreads"
    except ImportError as exc:  # pragma: no cover - live discovery fallback
        print(f"Live discovery unavailable: {exc}")
        return []

    deadline = time.time() + 6
    waited = 0
    while getattr(engine, "pools_loading", False) and time.time() < deadline:
        print("Live discovery waiting for pool data...")
        time.sleep(0.25)
        waited += 1

    if getattr(engine, "pools_loading", False):
        print("Live discovery timed out waiting for pool data")
        return []

    try:
        opportunities = getattr(engine, scan_method)(max_comparisons=600)
    except Exception as exc:  # pragma: no cover - resilience for live discovery issues
        print(f"Live discovery scan failed: {exc}")
        return []

    filtered: List[Any] = []
    for opp in opportunities:
        flash_loan_data = getattr(opp, "flash_loan", None)
        if not flash_loan_data:
            continue

        if engine_strategy == 'COEFFICIENT' and not hasattr(opp, 'min_reserve_usd'):
            opp.min_reserve_usd = min(getattr(opp.buy_pool, "reserve_usd", 0), getattr(opp.sell_pool, "reserve_usd", 0))
            if not hasattr(flash_loan_data, 'loan_amount_usd'):
                flash_loan_data.loan_amount_usd = getattr(opp, 'optimal_loan_usd', 0)

        min_liq = getattr(opp, "min_reserve_usd", 0)
        if min_liq < 25000:
            continue

        optimal_loan_usd = getattr(flash_loan_data, "loan_amount_usd", 0)
        utilization = optimal_loan_usd / min_liq if min_liq > 0 else 0
        if utilization > 0.20:
            continue

        filtered.append(opp)

    return filtered


def _build_live_opportunity(cycle: int, index: int, opp: Any) -> LiveOpportunity:
    # The opportunity from the ranker is already a LiveOpportunity instance
    # We just need to ensure the metadata is updated for the simulation report.
    if not hasattr(opp, "metadata"):
        opp.metadata = {}
    
    opp.metadata["cycle"] = cycle
    opp.metadata["index"] = index
    opp.metadata["source"] = opp.metadata.get("source", "rust_scanner" if os.getenv("SCANNER_MODE", "rust") == "rust" else "python_scanner")

    return LiveOpportunity(
        path=getattr(opp, "path", ()),
        pool_sequence=getattr(opp, "pool_sequence", ()),
        protocol_seq=getattr(opp, "protocol_seq", ()),
        profitability=getattr(opp, "profitability", SimpleNamespace()),
        family=getattr(opp, "family", "C1"),
        metadata=opp.metadata,
    )


def _staging_buy_price(op: Any) -> Decimal:
    sequence = getattr(op, "metadata", {}).get("execution_sequence", {}) if hasattr(op, "metadata") else {}
    buy_leg = sequence.get("buy_leg", {}) if isinstance(sequence, dict) else {}
    raw = buy_leg.get("executable_buy_price_base_per_mid") if isinstance(buy_leg, dict) else None
    try:
        return Decimal(str(raw))
    except (ValueError, TypeError, InvalidOperation):
        return Decimal("Infinity")


def simulate_staging(ranked_opportunities: List[Any], max_staged: int = 8) -> List[Any]:
    """Deterministic dry-run staging proof."""
    if max_staged <= 0:
        return []
    ordered = sorted(enumerate(ranked_opportunities), key=lambda item: (_staging_buy_price(item[1]), item[0]))
    staged: List[Any] = []
    used_pools: set[str] = set()
    for _, opportunity in ordered:
        pools = tuple(str(pool) for pool in getattr(opportunity, "pool_sequence", ()) if pool)
        if any(pool in used_pools for pool in pools):
            continue
        staged.append(opportunity)
        used_pools.update(pools)
        if len(staged) >= max_staged:
            break
    return staged


def _build_synthetic_opportunity(cycle: int, index: int, profitable: bool) -> LiveOpportunity:
    net_profit = Decimal("12.3") if profitable else Decimal("3.1")
    metadata = {
        "cycle": cycle,
        "index": index,
        "family": "C1" if index == 0 else "C2",
        "execution_sequence": {"buy_leg": {"executable_buy_price_base_per_mid": Decimal("1000.00") + Decimal(index) - Decimal(cycle * 0.01)}},
    }
    profitability = type("P", (), {"net_profit_usd": net_profit, "flashloan": type("F", (), {"principal_usd": Decimal("5000")})()})()
    return LiveOpportunity(
        path=("USDC", "WETH", "USDC"),
        pool_sequence=(f"p{cycle}-{index}", f"p{cycle}-{index + 1}"),
        protocol_seq=("UniswapV2", "UniswapV2"),
        profitability=profitability,
        family="C1" if index == 0 else "C2",
        metadata=metadata,
    )


def run_dry_cycles(num_cycles: int = 25, use_live: bool = False, emit_report: bool = True) -> dict[str, Any]:
    print(f"Running {num_cycles} dry-run cycles (live={use_live or LIVE_MODE})...")

    cycles: list[dict[str, Any]] = []
    discovered_total = 0
    shadow_executed_total = 0
    accepted_total = 0
    rejected_total = 0
    total_profit_usd = Decimal("0")
    live_discovery_count = 0
    pipeline_mode = "live" if (use_live or LIVE_MODE) else "synthetic"

    for cycle in range(num_cycles):
        if use_live or LIVE_MODE:
            discovered_live = _discover_live_opportunities()
            live_discovery_count += len(discovered_live)
            if discovered_live:
                opportunities = [_build_live_opportunity(cycle, i, opp) for i, opp in enumerate(discovered_live[:4])]
                data_source = "live"
            else:
                opportunities = [_build_synthetic_opportunity(cycle, i, profitable=(i % 2 == 0)) for i in range(3)]
                data_source = "synthetic_fallback"
        else:
            opportunities = [_build_synthetic_opportunity(cycle, i, profitable=(i % 2 == 0)) for i in range(3)]
            data_source = "synthetic"

        discovered_total += len(opportunities)
        staged = simulate_staging(opportunities, max_staged=2)
        cycle_report = {
            "cycle": cycle + 1,
            "discovered": len(opportunities),
            "staged": len(staged),
            "shadow_executed": 0,
            "accepted": 0,
            "rejected": 0,
            "profit_usd": 0.0,
        }

        for opportunity in staged:
            shadow_executed_total += 1
            cycle_report["shadow_executed"] += 1
            accepted = revalidate_profitability_at_broadcast(opportunity, {})
            if accepted:
                accepted_total += 1
                cycle_report["accepted"] += 1
                total_profit_usd += Decimal(str(getattr(opportunity.profitability, "net_profit_usd", 0)))
                cycle_report["profit_usd"] += float(getattr(opportunity.profitability, "net_profit_usd", 0))
            else:
                rejected_total += 1
                cycle_report["rejected"] += 1

        cycles.append(cycle_report)

    summary = {
        "cycles": num_cycles,
        "discovered_total": discovered_total,
        "shadow_executed_total": shadow_executed_total,
        "accepted_total": accepted_total,
        "rejected_total": rejected_total,
        "total_profit_usd": float(total_profit_usd.quantize(Decimal("0.01"))),
        "execution_rate": round((shadow_executed_total / max(discovered_total, 1)) * 100, 2),
        "discovery_rate": round((accepted_total / max(shadow_executed_total, 1)) * 100, 2),
        "profit_per_cycle_usd": round(float(total_profit_usd / max(num_cycles, 1)), 2),
        "accepted_per_cycle": round(accepted_total / max(num_cycles, 1), 2),
        "data_source": data_source,
        "pipeline_mode": pipeline_mode,
        "live_discovery_count": live_discovery_count,
    }

    report = {
        "summary": summary,
        "cycles": cycles,
    }

    if emit_report:
        out_dir = Path(__file__).resolve().parents[1] / "out"
        out_dir.mkdir(exist_ok=True)
        report_path = out_dir / "dry_run_shadow_report.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))

    return report


if __name__ == "__main__":
    run_dry_cycles(25, use_live=LIVE_MODE)
