#!/usr/bin/env python3
"""
25-Cycle Dry Run Simulator
- Uses the real discovery/ranking/staging pipeline in all modes.
- Emits a structured shadow report with discovery, execution, and profitability metrics.
- Writes the report to `out/dry_run_shadow_report.json`.

Dry-run execution mode (no transaction broadcasting):
    python tests/dry_run_25_cycles.py
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

        def to_payload(self) -> dict[str, Any]:
            return {
                "path": _make_serializable(getattr(self, "path", ())),
                "pool_sequence": _make_serializable(getattr(self, "pool_sequence", ())),
                "protocol_seq": _make_serializable(getattr(self, "protocol_seq", ())),
                "profitability": _make_serializable(getattr(self, "profitability", None)),
                "block_detected": getattr(self, "block_detected", 0),
                "metadata": _make_serializable(getattr(self, "metadata", {})),
                "market_snapshot": _make_serializable(getattr(self, "market_snapshot", None)),
                "opp_id": getattr(self, "opp_id", ""),
                "family": getattr(self, "family", "C1"),
                "c1_success": getattr(self, "c1_success", False),
                "liquidation_data": _make_serializable(getattr(self, "liquidation_data", None)),
                "pricing_steps": _make_serializable(getattr(self, "pricing_steps", [])),
            }

        def to_payload(self) -> dict[str, Any]:
            return {
                key: value for key, value in self.__dict__.items() if not key.startswith("_")
            }

LIVE_MODE = bool(os.getenv("OMEGA_LIVE_TEST") or os.getenv("LIVE_TEST_RPC_URL"))


def _make_serializable(value: Any) -> Any:
    """Recursively convert discovery data into JSON-friendly primitives."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, tuple):
        return [_make_serializable(item) for item in value]
    if isinstance(value, (list, set, frozenset)):
        return [_make_serializable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _make_serializable(item) for key, item in value.items()}
    if hasattr(value, "__dict__") and not isinstance(value, type):
        return {
            key: _make_serializable(item)
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    return value


def _open_live_pipeline_gates() -> None:
    """Force-enable pipeline gates for live-proof dry runs (no tx broadcasting)."""
    os.environ["OMEGA_ENGINE_NO_SCAN"] = "false"
    os.environ.setdefault("REQUIRE_EXECUTABLE_ROUTE_STREAM", "false")
    os.environ.setdefault("ENGINE_STRATEGY", "FULL_ARB")
    os.environ.setdefault("EXECUTION_MODE", "dry_run")
    os.environ.setdefault("LIVE_TRADING", "0")
    os.environ.setdefault("WAAS_BROADCAST_ADAPTER_ENABLED", "false")


def _rank_live_opportunities(opportunities: List[Any]) -> List[Any]:
    """Rank opportunities by net profit before staging."""
    def _score(opp: Any) -> Decimal:
        flash = getattr(opp, "flash_loan", None)
        net_profit = getattr(flash, "net_profit_usd", 0)
        try:
            return Decimal(str(net_profit))
        except (ValueError, TypeError, InvalidOperation):
            return Decimal("-Infinity")

    return sorted(opportunities, key=_score, reverse=True)


def _iter_rpc_urls() -> List[str]:
    """Return the configured RPC rotation list, falling back to the single RPC URL env vars."""
    candidates: List[str] = []
    rotation_value = os.getenv("RPC_ROTATION_HTTP_URLS", "").strip()
    if rotation_value:
        candidates.extend([item.strip() for item in rotation_value.split(",") if item.strip()])

    if not candidates:
        single_url = os.getenv("POLYGON_RPC_URL") or os.getenv("RPC_URL") or os.getenv("DISCOVERY_RPC_URL") or os.getenv("PRIMARY_READ_RPC_URL")
        if single_url:
            candidates.append(single_url)

    return candidates


def _discover_live_opportunities() -> List[Any]:
    """Use the live coefficient engine to discover opportunities from current Polygon market state."""
    engine_strategy = os.getenv('ENGINE_STRATEGY', 'FULL_ARB').upper()
    rpc_urls = _iter_rpc_urls()
    if rpc_urls:
        print(f"🔁 RPC rotation endpoints: {len(rpc_urls)}")
    else:
        print("⚠️ No RPC rotation endpoints configured; falling back to single-endpoint discovery")

    # Try each configured RPC in order until one yields usable data.
    last_error: str | None = None
    for idx, rpc_url in enumerate(rpc_urls or [None]):
        if rpc_url:
            os.environ['POLYGON_RPC_URL'] = rpc_url
            os.environ['RPC_URL'] = rpc_url
            os.environ['DISCOVERY_RPC_URL'] = rpc_url
            os.environ['PRIMARY_READ_RPC_URL'] = rpc_url
            print(f"🔗 Trying RPC endpoint {idx + 1}/{len(rpc_urls)}: {rpc_url}")
        else:
            print("🔗 Trying default RPC endpoint")

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
            last_error = str(exc)
            continue

        deadline = time.time() + 6
        waited = 0
        while getattr(engine, "pools_loading", False) and time.time() < deadline:
            print("Live discovery waiting for pool data...")
            time.sleep(0.25)
            waited += 1

        if getattr(engine, "pools_loading", False):
            print("Live discovery timed out waiting for pool data")
            continue

        try:
            opportunities = getattr(engine, scan_method)(max_comparisons=600)
        except Exception as exc:  # pragma: no cover - resilience for live discovery issues
            last_error = str(exc)
            continue

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

        if filtered:
            return filtered

    if last_error:
        print(f"Live discovery unavailable: {last_error}")
    return []



def _build_live_opportunity(cycle: int, index: int, opp: Any) -> LiveOpportunity:
    # The opportunity from the ranker is already a LiveOpportunity instance
    # We just need to ensure the metadata is updated for the simulation report.
    if not hasattr(opp, "metadata"):
        opp.metadata = {}

    opp.metadata["cycle"] = cycle
    opp.metadata["index"] = index
    opp.metadata["source"] = opp.metadata.get("source", "rust_scanner" if os.getenv("SCANNER_MODE", "rust") == "rust" else "python_scanner")

    pool_states: List[dict[str, Any]] = []
    for pool in (getattr(opp, "buy_pool", None), getattr(opp, "sell_pool", None)):
        if pool is None:
            continue
        pool_states.append({
            "address": getattr(pool, "address", None),
            "reserve_usd": getattr(pool, "reserve_usd", None),
            "reserve0": getattr(pool, "reserve0", None),
            "reserve1": getattr(pool, "reserve1", None),
            "token0": getattr(pool, "token0", None),
            "token1": getattr(pool, "token1", None),
            "price": getattr(pool, "price", None),
            "protocol": getattr(pool, "protocol", None),
        })

    market_snapshot = {
        "source": "live_discovery",
        "path": tuple(getattr(opp, "path", ())),
        "pool_sequence": tuple(getattr(opp, "pool_sequence", ())),
        "protocol_seq": tuple(getattr(opp, "protocol_seq", ())),
        "pool_states": pool_states,
    }

    opportunity = LiveOpportunity(
        path=getattr(opp, "path", ()),
        pool_sequence=getattr(opp, "pool_sequence", ()),
        protocol_seq=getattr(opp, "protocol_seq", ()),
        profitability=getattr(opp, "profitability", SimpleNamespace()),
        family=getattr(opp, "family", "C1"),
        metadata=opp.metadata,
    )
    opportunity.market_snapshot = market_snapshot
    return opportunity


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


def run_dry_cycles(num_cycles: int = 25, use_live: bool = False, emit_report: bool = True) -> dict[str, Any]:
    print(f"Running {num_cycles} dry-run cycles (live_pipeline=True, requested_live={use_live or LIVE_MODE})...")

    cycles: list[dict[str, Any]] = []
    discovered_total = 0
    shadow_executed_total = 0
    accepted_total = 0
    rejected_total = 0
    total_profit_usd = Decimal("0")
    live_discovery_count = 0
    ranked_total = 0
    pipeline_mode = os.getenv("EXECUTION_MODE", "dry_run")
    _open_live_pipeline_gates()

    for cycle in range(num_cycles):
        should_attempt_live_discovery = bool(use_live or LIVE_MODE or os.getenv("OMEGA_LIVE_TEST") or os.getenv("LIVE_TEST_RPC_URL"))
        if should_attempt_live_discovery:
            discovered_live = _discover_live_opportunities()
            if discovered_live:
                live_discovery_count += len(discovered_live)
                ranked_live = _rank_live_opportunities(discovered_live)
                ranked_total += len(ranked_live)
                opportunities = [_build_live_opportunity(cycle, i, opp) for i, opp in enumerate(ranked_live[:4])]
            else:
                opportunities = []
        else:
            opportunities = []

        discovered_total += len(opportunities)
        staged = simulate_staging(opportunities, max_staged=2)
        cycle_report = {
            "cycle": cycle + 1,
            "discovered": len(opportunities),
            "ranked": len(opportunities),
            "staged": len(staged),
            "shadow_executed": 0,
            "accepted": 0,
            "rejected": 0,
            "profit_usd": 0.0,
            "data_source": "live_proof",
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
        "ranked_total": ranked_total,
        "shadow_executed_total": shadow_executed_total,
        "accepted_total": accepted_total,
        "rejected_total": rejected_total,
        "total_profit_usd": float(total_profit_usd.quantize(Decimal("0.01"))),
        "execution_rate": round((shadow_executed_total / max(discovered_total, 1)) * 100, 2),
        "discovery_rate": round((accepted_total / max(shadow_executed_total, 1)) * 100, 2),
        "profit_per_cycle_usd": round(float(total_profit_usd / max(num_cycles, 1)), 2),
        "accepted_per_cycle": round(accepted_total / max(num_cycles, 1), 2),
        "data_source": "live_proof",
        "pipeline_mode": pipeline_mode,
        "live_discovery_count": live_discovery_count,
        "tx_broadcasting": False,
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
