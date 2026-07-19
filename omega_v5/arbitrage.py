# ==============================================================================
# arbitrage.py  —  Arbitrage path graph + Bellman-Ford negative-cycle detection
# Extracted from Cell 5 of notebooks/omega_v5.ipynb
#
# Graph representation
# --------------------
#   Nodes  : token symbols
#   Edges  : (token_in, token_out, weight=-log(rate), pool_id, protocol)
#
# Canonical executable cycle shape
# --------------------------------
#   FLASHLOAN_ASSET
#     -> BUY any mid-token on ANY invariant
#     -> [hop any mid-token on ANY invariant]*
#     -> SELL back to FLASHLOAN_ASSET on ANY invariant
#     -> SURPLUS after repay
#
# Closed path form: [flash, mid_1, ..., mid_k, flash]
#
# Arbitrage condition
# -------------------
#   A cycle  t0 → t1 → … → tn → t0  is profitable when
#       ∏ rate_i  >  1   ⟺   Σ (-log(rate_i))  <  0
#   i.e. a *negative-weight cycle* in the transformed graph.
#   Bellman-Ford detects these in O(V·E) time.
# ==============================================================================

import math
from typing import Dict, List, Tuple

from .cycle_shape import tag_cycle_dict
from .liquidity_registry import PRODUCTION_ROUTING_SPINE
from .rust_engine import rust_bellman_ford_cycles


SHAPE_FORMULA = (
    "FLASHLOAN_ASSET -> BUY_ANY_MID(ANY_INVARIANT) "
    "[-> ANY_MID(ANY_INVARIANT)]* -> SELL_TO_FLASH(ANY_INVARIANT) -> SURPLUS"
)


class ArbitrageGraphEngine:
    """Constructs and analyses a directed exchange-rate graph for arbitrage detection."""

    def __init__(self, rates: dict):
        self.edges:  List[Tuple] = []   # (u, v, weight, pool_id, protocol, rate)
        self.tokens: List[str]   = []
        self._build_graph(rates)

    def _build_graph(self, rates: dict) -> None:
        token_set = set()
        for (tin, tout), pool_list in rates.items():
            token_set.add(tin)
            token_set.add(tout)
            for entry in pool_list:
                r = float(entry["rate"])
                if r <= 0:
                    continue
                weight = -math.log(r)
                self.edges.append((tin, tout, weight, entry["pool_id"], entry["protocol"], r))
        self.tokens = sorted(token_set)
        print(f"📐 Graph built: {len(self.tokens)} nodes (tokens), {len(self.edges)} edges (pool routes)")

    def bellman_ford_all_sources(self) -> List[dict]:
        """Runs the Rust-mandatory Bellman-Ford engine on the graph."""
        rates: dict[tuple[str, str], list[dict]] = {}
        for token_in, token_out, _weight, pool_id, protocol, rate in self.edges:
            rates.setdefault((token_in, token_out), []).append({
                "pool_id": pool_id,
                "protocol": protocol,
                "rate": rate,
            })
        opportunities = rust_bellman_ford_cycles(rates)
        tagged = [tag_cycle_dict(opp) for opp in opportunities]
        print(f"🦀 Rust Bellman-Ford engine returned {len(tagged)} negative-cycle candidate(s)")
        print(f"   Shape: {SHAPE_FORMULA}")
        return tagged


def merge_cycle_sets(*cycle_sets: List[dict]) -> List[dict]:
    merged: dict[tuple, dict] = {}
    for cycles in cycle_sets:
        for cycle in cycles:
            tagged = tag_cycle_dict(cycle)
            pools = tuple(
                edge.get("pool_id", "")
                for edge in tagged.get("edges", [])
                if edge
            )
            key = (tuple(tagged.get("path", [])), pools)
            existing = merged.get(key)
            if existing is None or tagged.get("profit_pct", 0) > existing.get("profit_pct", 0):
                merged[key] = tagged
    return sorted(merged.values(), key=lambda x: x["profit_pct"], reverse=True)


def print_arb_report(opportunities: List[dict], max_show: int = 20) -> None:
    """Pretty-prints ranked arbitrage opportunities in expanded flash-cycle form."""
    if not opportunities:
        print("  ↳ No profitable arbitrage cycles detected in the current pool state.")
        return

    print(f"\n{'=' * 90}")
    print(f"🔥 ARBITRAGE OPPORTUNITY REPORT  —  {len(opportunities)} unique cycle(s) detected")
    print(f"   Shape: {SHAPE_FORMULA}")
    print(f"{'=' * 90}")

    for rank, opp in enumerate(opportunities[:max_show], 1):
        tagged = tag_cycle_dict(opp) if "cycle_shape" not in opp else opp
        path_str = " → ".join(tagged["path"])
        hops     = len(tagged["path"]) - 1
        profit   = tagged["profit_pct"]
        cum      = tagged["cumulative_rate"]
        flash    = tagged.get("flash_asset") or tagged["path"][0]
        mids     = tagged.get("mid_tokens") or tagged["path"][1:-1]
        tier     = "🟢 STRONG" if profit > 1.0 else ("🟡 MARGINAL" if profit > 0.1 else "🔴 MICRO")
        print(f"\n  #{rank:>3}  {tier}")
        print(f"       Path ({hops} hop{'s' if hops != 1 else ''}): {path_str}")
        print(f"       Flash/Mids : FLASH({flash}) mids={mids}")
        print(f"       Cumulative Rate: {cum:.8f}   Gross Profit: {profit:+.6f}%")
        print(f"       Pool Sequence (any invariant per hop):")
        for ep in tagged["edges"]:
            if ep:
                print(
                    f"         ├─ [{ep.get('protocol', '?'):<12}] {ep.get('pool_id')}  "
                    f"rate={float(ep.get('rate', 0)):.6f}  "
                    f"{ep.get('token_in')}->{ep.get('token_out')}"
                )

    if len(opportunities) > max_show:
        print(f"\n  … and {len(opportunities) - max_show} additional cycles (truncated).")

    print(f"\n{'=' * 90}")
    best = tag_cycle_dict(opportunities[0]) if opportunities else {}
    print(f"  ★  Best gross opportunity: {best.get('profit_pct', 0):+.6f}% on path: {' → '.join(best.get('path', []))}")
    print(f"     ⚠️  Note: gross profit does not account for gas costs, slippage, or MEV.")
    print(f"{'=' * 90}\n")
