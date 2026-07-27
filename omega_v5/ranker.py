# ==============================================================================
# ranker.py  —  Cross-pool rate computation and ranked comparison
# Extracted from Cell 4 of notebooks/omega_v5.ipynb
# ==============================================================================

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List

from .amm_adapters import quote_pool
from .rpc_layer import canonical_liquidity_key

QUOTE_AMOUNT = Decimal("1000")  # Normalised input amount for all rate comparisons


PROTOCOL_INVARIANT = {
    "UniswapV2": "constant_product",
    "UniswapV3": "concentrated_liquidity",
    "QuickSwapV3": "algebra_concentrated_liquidity",
    "Algebra": "algebra_concentrated_liquidity",
    "Curve": "stable_swap",
    "Balancer": "weighted_invariant",
}


@dataclass(frozen=True)
class CrossPoolSpread:
    """Two-leg cross-pool arb: buy leg1 cheap, sell leg2 rich."""

    path: list[str]
    pool_sequence: list[str]
    protocol_seq: list[str]
    buy_pool_id: str
    sell_pool_id: str
    buy_liquidity_key: str
    sell_liquidity_key: str
    buy_protocol: str
    sell_protocol: str
    buy_rate: Decimal
    sell_rate: Decimal
    buy_price: Decimal
    sell_price: Decimal
    round_trip_rate: Decimal
    gross_profit_pct: Decimal
    cross_protocol: bool
    cross_invariant: bool
    route_class: str = "NATIVE_POOL_ROUTE"
    comparable: bool = True


def _quote_entry(
    pool_id: str,
    pool: dict,
    token_in: str,
    token_out: str,
    rate: Decimal,
    amount_out: Decimal,
) -> dict:
    proto = pool["protocol"]
    invariant = PROTOCOL_INVARIANT.get(proto, proto)
    return {
        "pool_id": pool_id,
        "protocol": proto,
        "route_class": pool.get("route_class", "NATIVE_POOL_ROUTE"),
        "liquidity_key": pool.get("liquidity_key") or canonical_liquidity_key(pool_id, pool),
        "invariant": invariant,
        "token_in": token_in,
        "token_out": token_out,
        "rate": rate,
        "amount_out": amount_out,
    }


def compute_all_pool_rates(pools: dict) -> dict:
    """
    Iterates every pool and computes the effective exchange rate
    (amount_out / amount_in) for each directional token pair it supports.

    Returns
    -------
    dict
        rates[(token_in, token_out)] = [
            {"pool_id": str, "protocol": str, "rate": Decimal, "amount_out": Decimal},
            ...
        ]
        Each list is sorted by rate descending (best rate first).
    """
    rates: dict = defaultdict(list)

    for pool_id, pool in pools.items():
        try:
            quotes = quote_pool(pool, QUOTE_AMOUNT)
        except (KeyError, ValueError, ArithmeticError, TypeError):
            continue

        for quote in quotes:
            if quote.amount_out > 0:
                entry = _quote_entry(
                    pool_id,
                    pool,
                    quote.token_in,
                    quote.token_out,
                    quote.amount_out / QUOTE_AMOUNT,
                    quote.amount_out,
                )
                entry["invariant"] = quote.invariant
                rates[(quote.token_in, quote.token_out)].append(entry)

    for pair in rates:
        rates[pair].sort(key=lambda x: x["rate"], reverse=True)

    return dict(rates)


def detect_cross_pool_two_leg_spreads(
    rates: dict,
    min_profit_bps: Decimal = Decimal("0"),
) -> list[CrossPoolSpread]:
    """
    Detect direct two-leg spreads:
      leg1: token_a -> token_b on the pool giving the lower effective buy price
      leg2: token_b -> token_a on a different pool giving the higher sell price

    The condition is:
      buy_price(token_b in token_a) < sell_price(token_b in token_a)
    which is equivalent to:
      (token_a -> token_b rate) * (token_b -> token_a rate) > 1
    """
    spreads: list[CrossPoolSpread] = []
    seen: set[tuple[str, str, str, str]] = set()
    min_profit = min_profit_bps / Decimal("10000")

    for (token_a, token_b), buy_quotes in rates.items():
        sell_quotes = rates.get((token_b, token_a), [])
        if not sell_quotes:
            continue

        for buy in buy_quotes:
            buy_rate = Decimal(str(buy["rate"]))
            if buy_rate <= 0:
                continue
            buy_price = Decimal("1") / buy_rate

            for sell in sell_quotes:
                if buy.get("route_class") != "NATIVE_POOL_ROUTE" or sell.get("route_class") != "NATIVE_POOL_ROUTE":
                    continue
                if buy["liquidity_key"] == sell["liquidity_key"]:
                    continue

                sell_rate = Decimal(str(sell["rate"]))
                if sell_rate <= 0:
                    continue

                sell_price = sell_rate
                if buy_price >= sell_price:
                    continue

                round_trip = buy_rate * sell_rate
                if round_trip <= Decimal("1") + min_profit:
                    continue

                key = (token_a, token_b, buy["liquidity_key"], sell["liquidity_key"])
                if key in seen:
                    continue
                seen.add(key)

                buy_proto = buy["protocol"]
                sell_proto = sell["protocol"]
                spreads.append(CrossPoolSpread(
                    path=[token_a, token_b, token_a],
                    pool_sequence=[buy["pool_id"], sell["pool_id"]],
                    protocol_seq=[buy_proto, sell_proto],
                    buy_pool_id=buy["pool_id"],
                    sell_pool_id=sell["pool_id"],
                    buy_liquidity_key=buy["liquidity_key"],
                    sell_liquidity_key=sell["liquidity_key"],
                    buy_protocol=buy_proto,
                    sell_protocol=sell_proto,
                    buy_rate=buy_rate,
                    sell_rate=sell_rate,
                    buy_price=buy_price,
                    sell_price=sell_price,
                    round_trip_rate=round_trip,
                    gross_profit_pct=(round_trip - Decimal("1")) * Decimal("100"),
                    cross_protocol=buy_proto != sell_proto,
                    cross_invariant=buy["invariant"] != sell["invariant"],
                    route_class="NATIVE_POOL_ROUTE",
                    comparable=True,
                ))

    spreads.sort(key=lambda s: s.gross_profit_pct, reverse=True)
    return spreads


def print_ranked_rates(rates: dict, top_n: int = 5) -> None:
    """
    Prints a ranked table for every token pair covered by more than one pool,
    i.e. pairs where cross-pool comparison is meaningful.
    """
    multi_pool_pairs = {k: v for k, v in rates.items() if len(v) >= 2}

    print("📊 CROSS-POOL PRICE RANKING REPORT")
    print(f"   Pairs with multi-pool coverage: {len(multi_pool_pairs)} | "
          f"Total directional quotes: {sum(len(v) for v in rates.values())}")
    print("=" * 90)

    for (token_in, token_out), pool_list in sorted(multi_pool_pairs.items(), key=lambda x: x[0]):
        best      = pool_list[0]
        worst     = pool_list[-1]
        spread_pct = float(
            (best["rate"] - worst["rate"]) / worst["rate"] * 100
        ) if worst["rate"] > 0 else 0.0

        print(f"\n  {token_in:>12s} → {token_out:<12s}  "
              f"[{len(pool_list)} pools | spread: {spread_pct:+.4f}%]")
        print(f"  {'Rank':<5} {'Pool ID':<40} {'Protocol':<12} {'Rate':>12} {'Δ vs Best':>12}")
        print(f"  {'-' * 85}")

        for rank, entry in enumerate(pool_list[:top_n], 1):
            delta_pct = float((entry["rate"] - best["rate"]) / best["rate"] * 100)
            marker    = "★ BEST" if rank == 1 else ("▼ WORST" if rank == len(pool_list[:top_n]) else "")
            print(f"  #{rank:<4} {entry['pool_id']:<40} {entry['protocol']:<12} "
                  f"{float(entry['rate']):>12.6f} {delta_pct:>+11.4f}%  {marker}")

    print("\n" + "=" * 90)
    print(f"✅ Price ranking complete across {len(rates)} directional token-pair routes.")


def print_cross_pool_spreads(spreads: list[CrossPoolSpread], top_n: int = 10) -> None:
    print("🔁 TWO-LEG CROSS-POOL SPREAD REPORT")
    print(f"   Buy-leg lower than sell-leg opportunities: {len(spreads)}")
    print("=" * 90)

    if not spreads:
        print("  ↳ No two-leg cross-pool spreads pass the current gross spread threshold.")
        print("=" * 90)
        return

    for idx, spread in enumerate(spreads[:top_n], 1):
        print(
            f"\n  #{idx:<3} {' → '.join(spread.path)}  "
            f"gross={spread.gross_profit_pct:+.6f}%  "
            f"cross_dex={spread.cross_protocol} cross_invariant={spread.cross_invariant}"
        )
        print(
            f"       BUY  {spread.path[1]} with {spread.path[0]} on "
            f"{spread.buy_protocol:<12} {spread.buy_pool_id}  "
            f"price={spread.buy_price:.12f}"
        )
        print(
            f"       SELL {spread.path[1]} for {spread.path[0]} on "
            f"{spread.sell_protocol:<12} {spread.sell_pool_id}  "
            f"price={spread.sell_price:.12f}"
        )

    if len(spreads) > top_n:
        print(f"\n  ... and {len(spreads) - top_n} additional two-leg spreads.")
    print("=" * 90)


