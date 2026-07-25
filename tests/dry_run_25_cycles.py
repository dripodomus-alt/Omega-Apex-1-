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
from omega_v5.execution import build_tx_payload
try:
    from omega_v5.main import collect_and_score_opportunities
except Exception:
    def collect_and_score_opportunities(*args, **kwargs):
        raise RuntimeError("collect_and_score_opportunities is unavailable in this checkout")
from omega_v5.opportunity_ranker import LiveOpportunity
from omega_v5.flash_loan import ( # type: ignore
    GAS_PRICE_GWEI,
    FlashSource,
    live_min_net_profit_usd,
)
from unittest.mock import patch


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

def get_dna_from_opp(cycle: int, rank: int, opp: LiveOpportunity, pools: dict) -> dict[str, Any]:
    """Print full transparent DNA of a route."""
    # The LiveOpportunity object already contains the full profitability breakdown.
    # We just need to extract it and build the payload for inspection.
    profitability = opp.profitability
    payload = build_tx_payload(opp, pools, nonce=0, base_fee_gwei=GAS_PRICE_GWEI)

    # The economics object is now part of the LiveOpportunity's profitability
    # attribute, but it's a different structure. We adapt to the new structure.
    # The `calculate_route_economics` object was more detailed than the new
    # `Profitability` object. We'll extract what we can.
    net_profit = profitability.net_profit_usd
    min_profit = live_min_net_profit_usd()

    return {
        "cycle": cycle,
        "rank": rank,
        "route_id": opp.metadata.get("opp_id", "N/A"),
        "legs": len(opp.path) - 1,
        "spread_type": opp.metadata.get("strategy", "N/A"),
        "spread_bps": (opp.gross_rate - 1) * 10000 if opp.gross_rate else 0,
        "flash_principal_usd": profitability.flashloan.principal_usd,
        "gross_sell_out_usd": opp.gross_out_usd,
        "gross_surplus_usd": profitability.raw_delta_usd,
        "flash_fee_usd": profitability.flash_fee_usd,
        "gas_cost_usd": profitability.gas_cost_usd,
        "relay_tip_usd": profitability.relay_tip_usd,
        "risk_buffer_usd": profitability.risk_buffer_usd,
        "impact_penalty_usd": opp.metadata.get("sizing", {}).get("impact_penalty_usd", "0"),
        "minimum_profit_usd": min_profit,
        "economic_net_profit_usd": net_profit,
        "headroom_usd": net_profit - min_profit,
        "passes_gate": profitability.passes_gate,
        "payload_target": payload.get("to"),
        "calldata": payload.get("data", "0xERROR"),
        "calldata_bytes": (len(payload.get("data", "0x")) - 2) // 2,
    }


def print_route_dna(cycle: int, rank: int, dna: dict[str, Any]):
    """Prints the full transparent DNA of a route, using the processed DNA dictionary."""
    print(f"\n  [{cycle:02d}] Rank #{rank:02d} | Legs={dna['legs']} | Type={dna['spread_type']} | Spread BPS={dna.get('spread_bps', 0)}")
    print(f"      {'Component':<28} | {'Normalized USD':>24}")
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


def _create_mock_pools() -> Dict[str, Any]:
    """Creates a static set of mock pools with reserves designed to yield opportunities."""
    return {
        # 2-leg: USDC -> WETH -> USDC
        "P_USDC_WETH_A": {
            "protocol": "UniswapV2", "tokens": ["USDC", "WETH"],
            "reserves": [Decimal("1000000"), Decimal("300")], # Price WETH = 3333 USDC
            "fee": Decimal("0.003"), "fee_bps": 30, "address": "0x0000000000000000000000000000000000000001",
        },
        "P_WETH_USDC_B": {
            "protocol": "UniswapV2", "tokens": ["WETH", "USDC"],
            "reserves": [Decimal("300"), Decimal("1005000")], # Price WETH = 3350 USDC
            "fee": Decimal("0.003"), "fee_bps": 30, "address": "0x0000000000000000000000000000000000000002",
        },
        # 3-leg: USDC -> WETH -> WBTC -> USDC
        "P_USDC_WETH_C": {
            "protocol": "UniswapV3", "tokens": ["USDC", "WETH"], "fee": Decimal("0.0005"), "fee_bps": 500,
            "sqrtPriceX96": Decimal("2731314143865541125333533838535"), # WETH price ~3340 USDC
            "liquidity": Decimal("1e18"), "address": "0x0000000000000000000000000000000000000003",
        },
        "P_WETH_WBTC_D": {
            "protocol": "UniswapV3", "tokens": ["WETH", "WBTC"], "fee": Decimal("0.0005"), "fee_bps": 500,
            "sqrtPriceX96": Decimal("13151314143865541125333533838535"), # WBTC price ~20 WETH
            "liquidity": Decimal("1e18"), "address": "0x0000000000000000000000000000000000000004",
        },
        "P_WBTC_USDC_E": {
            "protocol": "UniswapV3", "tokens": ["WBTC", "USDC"], "fee": Decimal("0.0005"), "fee_bps": 500,
            "sqrtPriceX96": Decimal("8131314143865541125333533838535"), # WBTC price ~67000 USDC
            "liquidity": Decimal("1e18"), "address": "0x0000000000000000000000000000000000000005",
        },
    }


def _perturb_pools(pools: Dict[str, Any]) -> Dict[str, Any]:
    """Slightly and randomly adjusts reserves to simulate market changes."""
    new_pools = json.loads(json.dumps(_json_ready(pools))) # Deep copy
    for pool in new_pools.values():
        if "reserves" in pool:
            for i in range(len(pool["reserves"])):
                change = 1 + (random.random() - 0.5) * 0.005 # +/- 0.25%
                pool["reserves"][i] = str(Decimal(pool["reserves"][i]) * Decimal(change))
        if "sqrtPriceX96" in pool:
            change = 1 + (random.random() - 0.5) * 0.001 # +/- 0.05%
            pool["sqrtPriceX96"] = str(Decimal(pool["sqrtPriceX96"]) * Decimal(change))
    return new_pools


def discover_and_score_opportunities(
    pools: Dict[str, Any], principal_usd: Decimal
) -> List[LiveOpportunity]:
    """
    Uses the canonical discovery and scoring pipeline from the main application
    to ensure this test stays in sync with the production logic.
    """
    ranked_opps, _, _ = collect_and_score_opportunities(
        live_pools=pools,
        principal_usd=principal_usd,
        slippage_bps=Decimal("15"),  # Use a typical default slippage
    )
    return ranked_opps


# === Staging Simulator (based on payload_stager.py logic) ===
def _decimal_or_none(value: Any) -> Decimal | None:
    try:
        parsed = Decimal(str(value))
    except Exception:
        return None
    return parsed if parsed.is_finite() else None


def _nested(mapping: Any, *keys: str) -> Any:
    current = mapping
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return None
    return current


def _execution_sequence_from_opp(opp: LiveOpportunity) -> dict[str, Any]:
    metadata = getattr(opp, "metadata", None)
    if isinstance(metadata, dict):
        sequence = metadata.get("profitable_execution_staging") or metadata.get("execution_sequence")
        if isinstance(sequence, dict):
            return sequence
    sequence = getattr(opp, "profitable_execution_staging", None) or getattr(opp, "execution_sequence", None)
    return sequence if isinstance(sequence, dict) else {}


def _staging_priority(index: int, opp: LiveOpportunity) -> tuple[Any, ...]:
    sequence = _execution_sequence_from_opp(opp)
    if not sequence:
        return (1, index)
    passes = bool(sequence.get("passes"))
    buy_price = _decimal_or_none(_nested(sequence, "buy_leg", "executable_buy_price_base_per_mid"))
    sell_price = _decimal_or_none(_nested(sequence, "sell_leg", "executable_sell_price_min_base_per_mid"))
    spread = (sell_price - buy_price) if buy_price is not None and sell_price is not None else Decimal("0")
    net_profit = _decimal_or_none(_nested(getattr(opp, "metadata", {}), "net_formula", "net_gain_usd"))
    if net_profit is None:
        profitability = getattr(opp, "profitability", None)
        net_profit = _decimal_or_none(getattr(profitability, "net_profit_usd", None)) or Decimal("0")
    return (
        0 if passes else 2,
        buy_price if buy_price is not None else Decimal("Infinity"),
        -spread,
        -net_profit,
        index,
    )


def simulate_staging(ranked_opps: List[LiveOpportunity], max_staged: int = 8) -> List[LiveOpportunity]:
    """
    Simulates payload_stager behavior by selecting non-conflicting routes.

    When executable sequence proof is present, buy-low alignment comes first:
    the lowest executable base-asset price per mid-token unit is staged before
    weaker buy legs, and the sell leg must prove a higher base/mid return. When
    no proof is present, the prior ranked order is preserved for compatibility.
    """
    staged_opps: List[LiveOpportunity] = []
    used_pools: set[str] = set()
    ordered_opps = [opp for _, opp in sorted(
        enumerate(ranked_opps),
        key=lambda item: _staging_priority(item[0], item[1]),
    )]

    for opp in ordered_opps:
        if len(staged_opps) >= max_staged:
            break

        # A conflict exists if any pool in the current opportunity's sequence
        # has already been used by a previously staged opportunity.
        has_conflict = any(pool_id in used_pools for pool_id in opp.pool_sequence)

        if not has_conflict:
            staged_opps.append(opp)
            used_pools.update(opp.pool_sequence)

    return staged_opps

def main():
    print("=" * 70)
    print("25 CYCLE DRY RUN - FULL ROUTE DNA + STAGING ANALYSIS")
    print("=" * 70)

    # Clear the log file at the start of the run
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    if LOG_FILE.exists():
        LOG_FILE.unlink()

    # Create a static set of mock pools to discover opportunities from.
    mock_pools = _create_mock_pools()

    # Mock the oracle to provide prices for our mock tokens
    def mock_token_price_usd(symbol: str) -> Decimal:
        return {"USDC": Decimal("1"), "WETH": Decimal("3345"), "WBTC": Decimal("67500")}.get(symbol, Decimal("0"))

    total_2leg_staged = 0
    total_3leg_staged = 0
    cycles_with_more_2leg = 0
    cycles_with_more_3leg = 0

    for cycle in range(1, 26):
        print(f"\n{'='*70}")
        print(f"CYCLE {cycle:02d}")
        print(f"{'='*70}")

        # In each cycle, slightly perturb the pool reserves to simulate market changes
        perturbed_pools = _perturb_pools(mock_pools)

        with patch("omega_v5.oracle_layer.token_price_usd", mock_token_price_usd):
            ranked_opps = discover_and_score_opportunities(
                perturbed_pools, principal_usd=Decimal("10000")
            )

        # Log all profitable routes to the file
        with LOG_FILE.open("a", encoding="utf-8") as f:
            for idx, opp in enumerate(ranked_opps, 1):
                dna = get_dna_from_opp(cycle, idx, opp, perturbed_pools)
                f.write(json.dumps(_json_ready(dna)) + "\n")

        print(f"\nFound {len(ranked_opps)} profitable routes. Logged all to {LOG_FILE}")

        top10 = ranked_opps[:10]

        print(f"\nTop 10 routes (after gate filter + ranking by net surplus):")
        for idx, opp in enumerate(top10, 1):
            dna = get_dna_from_opp(cycle, idx, opp, perturbed_pools)
            print_route_dna(cycle, idx, dna)

        # Simulate staging
        staged = simulate_staging(ranked_opps, max_staged=8)

        two_leg = [opp for opp in staged if len(opp.path) - 1 == 2]
        three_leg = [opp for opp in staged if len(opp.path) - 1 > 2]

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
