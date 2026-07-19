#!/usr/bin/env python3
"""
25-Cycle Dry Run Simulator
- Generates synthetic opportunities.
- Applies ranking using the canonical raw gate.
- Logs FULL DNA of ALL profitable routes to `out/dry_run_full_log.jsonl`.
- Prints top 10 routes to console for quick review.
- Simulates staging behavior.
"""

import json
import time
from decimal import Decimal
from typing import Any, Dict, List
import random
import sys
from pathlib import Path

# Ensure the main project is in the path to import production logic
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from omega_v5.accounting import gas_cost_from_gwei, token_raw_to_units, token_units_to_raw_floor
from omega_v5.pricing.net_delta import raw_execution_gate_passes
from omega_v5.flash_loan import ( # type: ignore
    GAS_PRICE_GWEI, POL_USD_PRICE, live_relay_tip_usd, live_risk_buffer_usd, live_min_net_profit_usd
)

LOG_FILE = Path(__file__).resolve().parents[1] / "out" / "dry_run_full_log.jsonl"


def _json_ready(value: Any) -> Any:
    """Converts Decimals to strings for JSON serialization."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: _json_ready(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_ready(v) for v in value]
    return value


# === Canonical Gate (self-contained) ===

def get_route_dna(cycle: int, rank: int, route: Dict[str, Any]) -> dict[str, Any]:
    """Print full transparent DNA of a route."""
    # Use the corrected economic calculation
    from omega_v5.flash_loan import calculate_route_economics

    # Convert raw units to USD for the economics function
    principal_usd = token_raw_to_units(route['flash_principal_raw'], 18)
    sell_out_usd = token_raw_to_units(route['sell_amount_out_raw'], 18)
    flash_fee_usd = token_raw_to_units(route['flash_fee_raw'], 18)
    gas_cost_usd = token_raw_to_units(route['gas_cost_raw'], 18)
    relay_tip_usd = token_raw_to_units(route['relay_cost_raw'], 18)
    risk_buffer_usd = token_raw_to_units(route['risk_buffer_raw'], 18)
    minimum_profit_usd = token_raw_to_units(route['minimum_profit_raw'], 18)

    economics = calculate_route_economics(
        flash_principal_usd=principal_usd,
        gross_sell_out_usd=sell_out_usd,
        min_tvl_usd=Decimal(str(route.get("min_tvl_usd", "1000000"))),
        flash_fee_usd=flash_fee_usd,
        gas_cost_usd=gas_cost_usd,
        relay_tip_usd=relay_tip_usd,
        builder_fee_usd=Decimal("0"),
        risk_buffer_usd=risk_buffer_usd,
        minimum_profit_usd=minimum_profit_usd,
    )

    return {
        "cycle": cycle,
        "rank": rank,
        "route_id": route["route_id"],
        "legs": route["legs"],
        "spread_type": route["spread_type"],
        "spread_bps": route["spread_bps"],
        "flash_principal_usd": economics.flash_principal_usd,
        "gross_sell_out_usd": sell_out_usd,
        "gross_surplus_usd": economics.gross_surplus_usd,
        "flash_fee_usd": economics.flash_fee_usd,
        "gas_cost_usd": economics.gas_cost_usd,
        "relay_tip_usd": economics.relay_tip_usd,
        "risk_buffer_usd": economics.risk_buffer_usd,
        "impact_penalty_usd": economics.impact_penalty_usd,
        "minimum_profit_usd": economics.minimum_profit_usd,
        "economic_net_profit_usd": economics.economic_net_profit_usd,
        "headroom_usd": economics.headroom_usd,
        "passes_gate": economics.passes_gate,
    }


def print_route_dna(cycle: int, rank: int, dna: dict[str, Any]):
    """Print full transparent DNA of a route."""
    print(f"\n  [{cycle:02d}] Rank #{rank:02d} | Legs={route['legs']} | Type={route['spread_type']} | Spread BPS={route.get('spread_bps', 0)}")
    """Prints the full transparent DNA of a route, using the processed DNA dictionary."""
    print(f"\n  [{cycle:02d}] Rank #{rank:02d} | Legs={dna['legs']} | Type={dna['spread_type']} | Spread BPS={dna.get('spread_bps', 0)}")
    print(f"      {'Component':<28} | {'Normalized USD':>24}")
    print(f"      {'-'*22} | {'-'*28} | {'-'*24}")
    print(f"      {'-'*28} | {'-'*24}")
    print(f"      {'Flash Principal':<28} | ${dna['flash_principal_usd']:>24,.8f}")
    print(f"      {'Gross Sell Out':<28} | ${dna['gross_sell_out_usd']:>24,.8f}")
    print(f"      {'Gross Surplus':<28} | ${dna['gross_surplus_usd']:>24,.8f}")
    print(f"      {'-'*28} | {'-'*24}")
    print(f"      {'Flash Fee':<28} | ${dna['flash_fee_usd']:>24,.8f}")
    print(f"      {'Gas Cost':<28} | ${dna['gas_cost_usd']:>24,.8f}")
    print(f"      {'Relay Tip':<28} | ${dna['relay_tip_usd']:>24,.8f}")
    print(f"      {'Risk Buffer':<28} | ${dna['risk_buffer_usd']:>24,.8f}")
    print(f"      {'Impact Penalty':<28} | ${dna['impact_penalty_usd']:>24,.8f}")
    print(f"      {'-'*28} | {'-'*24}")
    print(f"      {'Economic Net Profit':<28} | ${dna['economic_net_profit_usd']:>24,.8f}")
    print(f"      {'Minimum Profit Threshold':<28} | ${dna['minimum_profit_usd']:>24,.8f}")
    print(f"      {'Headroom (Net - Min)':<28} | ${dna['headroom_usd']:>24,.8f}")
    print(f"      {'Passes Economic Gate':<28} | {str(dna['passes_gate']):>24}")


# === Route Generator (simulates discovery) ===
def generate_mock_routes(cycle: int, num_routes: int = 40) -> List[Dict[str, Any]]:
    routes = []
    random.seed(42 + cycle)  # Reproducible per cycle

    for i in range(num_routes):
        legs = random.choice([2, 3])
        spread_type = "2LEG_HIGH" if legs == 2 else random.choice(["3LEG_TRIANGLE", "3LEG_CROSS"])

        # Base principal in raw units (assume 18 decimals, ~$1000-$50000)
        principal = random.randint(1_000_000_000_000_000_000, 50_000_000_000_000_000_000)

        # Simulate spread
        if legs == 2:
            spread_bps = random.randint(8, 45)   # 2-leg can have higher spreads sometimes
        else:
            spread_bps = random.randint(12, 60)  # 3-leg often wider but more costs

        # Rough sell out before costs
        gross_out = int(principal * (1 + spread_bps / 10000))

        # Costs
        gas_units = Decimal("350000") if legs == 2 else Decimal("500000")
        gas_cost_usd = gas_cost_from_gwei(
            gas_units,
            GAS_PRICE_GWEI,
            POL_USD_PRICE,
            "dry_run_static",
        ).gas_cost_usd

        # Simulate flash fee from either Balancer (0) or Aave (0.05%)
        flash_source = random.choice(["balancer", "aave"])
        flash_fee_bps = Decimal("0") if flash_source == "balancer" else Decimal("5") # 5 bps for Aave
        flash_fee = int(Decimal(principal) * flash_fee_bps / Decimal("10000"))
        
        gas = token_units_to_raw_floor(gas_cost_usd, 18) # Assume base token is 18 dec and price is $1
        relay = token_units_to_raw_floor(live_relay_tip_usd(), 18) # Assume base token is 18 dec and price is $1
        risk = token_units_to_raw_floor(live_risk_buffer_usd(), 18) # Assume base token is 18 dec and price is $1
        min_profit = token_units_to_raw_floor(live_min_net_profit_usd(), 18) # Assume base token is 18 dec and price is $1

        sell_out = gross_out - random.randint(0, int(principal * 0.002))  # small slippage

        route = {
            "route_id": f"C{cycle:02d}-R{i:03d}",
            "legs": legs,
            "spread_type": spread_type,
            "flash_principal_raw": principal,
            "sell_amount_out_raw": sell_out,
            "flash_fee_raw": flash_fee,
            "gas_cost_raw": gas,
            "relay_cost_raw": relay,
            "risk_buffer_raw": risk,
            "minimum_profit_raw": min_profit,
            "spread_bps": spread_bps,
            "cycle": cycle,
        }
        routes.append(route)

    return routes


# === Ranking (applies gate + sorts by net surplus) ===
def rank_routes(routes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    from omega_v5.flash_loan import calculate_route_economics

    passed = []
    for r in routes:
        economics = calculate_route_economics(
            flash_principal_usd=token_raw_to_units(r['flash_principal_raw'], 18),
            gross_sell_out_usd=token_raw_to_units(r['sell_amount_out_raw'], 18),
            min_tvl_usd=Decimal(str(r.get("min_tvl_usd", "1000000"))),
            flash_fee_usd=token_raw_to_units(r['flash_fee_raw'], 18),
            gas_cost_usd=token_raw_to_units(r['gas_cost_raw'], 18),
            relay_tip_usd=token_raw_to_units(r['relay_cost_raw'], 18),
            builder_fee_usd=Decimal("0"),
            risk_buffer_usd=token_raw_to_units(r['risk_buffer_raw'], 18),
            minimum_profit_usd=token_raw_to_units(r['minimum_profit_raw'], 18),
        )
        if economics.passes_gate:
            passed.append((r, economics))

    # Sort by net surplus descending (ranking logic)
    passed.sort(key=lambda item: item[1].economic_net_profit_usd, reverse=True)
    return [item[0] for item in passed]


# === Staging Simulator (based on payload_stager.py logic) ===
def simulate_staging(ranked_routes: List[Dict[str, Any]], max_staged: int = 8) -> List[Dict[str, Any]]:
    """
    Simulates payload_stager behavior.
    - Applies raw gate (already done in ranking)
    - Takes top non-conflicting (we simplify: just take top N)
    - Does NOT explicitly prefer 2-leg or 3-leg
    """
    staged = []
    for r in ranked_routes[:max_staged]:
        r = r.copy()
        r["staged"] = True
        r["stage"] = "STAGED"
        staged.append(r)
    return staged


def main():
    print("=" * 70)
    print("25 CYCLE DRY RUN - FULL ROUTE DNA + STAGING ANALYSIS")
    print("=" * 70)

    # Clear the log file at the start of the run
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    if LOG_FILE.exists():
        LOG_FILE.unlink()

    total_2leg_staged = 0
    total_3leg_staged = 0
    cycles_with_more_2leg = 0
    cycles_with_more_3leg = 0

    for cycle in range(1, 26):
        print(f"\n{'='*70}")
        print(f"CYCLE {cycle:02d}")
        print(f"{'='*70}")

        routes = generate_mock_routes(cycle)
        ranked = rank_routes(routes)

        # Log all profitable routes to the file
        with LOG_FILE.open("a", encoding="utf-8") as f:
            for idx, route in enumerate(ranked, 1):
                dna = get_route_dna(cycle, idx, route)
                f.write(json.dumps(_json_ready(dna)) + "\n")

        print(f"\nFound {len(ranked)} profitable routes. Logged all to {LOG_FILE}")

        top10 = ranked[:10]

        print(f"\nTop 10 routes (after gate filter + ranking by net surplus):")
        for idx, route in enumerate(top10, 1):
            print_route_dna(cycle, idx, route)
            dna = get_route_dna(cycle, idx, route)
            print_route_dna(cycle, idx, dna)

        # Simulate staging
        staged = simulate_staging(ranked, max_staged=8)

        two_leg = [r for r in staged if r["legs"] == 2]
        three_leg = [r for r in staged if r["legs"] == 3]

        total_2leg_staged += len(two_leg)
        total_3leg_staged += len(three_leg)

        if len(two_leg) > len(three_leg):
            cycles_with_more_2leg += 1
        elif len(three_leg) > len(two_leg):
            cycles_with_more_3leg += 1

        print(f"\n  STAGING in this cycle (displaying {len(top10)} ranked, staging {len(staged)}):")
        print(f"    2-leg routes staged: {len(two_leg)}")
        print(f"    3-leg routes staged: {len(three_leg)}")
        print(f"    Total staged: {len(staged)}")

    print("\n" + "=" * 70)
    print("OVERALL STAGING STATISTICS (25 cycles)")
    print("=" * 70)
    print(f"Total 2-leg routes staged across all cycles: {total_2leg_staged}")
    print(f"Total 3-leg routes staged across all cycles: {total_3leg_staged}")
    print(f"Cycles where more 2-leg were staged: {cycles_with_more_2leg}")
    print(f"Cycles where more 3-leg were staged: {cycles_with_more_3leg}")

    print("\n=== STAGING BEHAVIOR CONCLUSION ===")
    if total_3leg_staged > 0 and total_2leg_staged == 0:
        print("Within this 25-cycle test dataset, the current candidate population and net-surplus")
        print("ranking resulted exclusively in three-leg routes being staged.")
    else:
        print("Staging behavior is mixed or inconclusive based on this dataset.")

    print("\nKey observation:")
    print("Staging (payload_stager) does NOT explicitly maximize variations.")
    print("It stages the highest net-surplus routes that pass the raw gate,")
    print("regardless of whether they are 2-leg or 3-leg.")
    print("=" * 70)


if __name__ == "__main__":
    main()
