#!/usr/bin/env python3
# ==============================================================================
# stable_strategies.py -- pegged-asset and stable-swap route promotion.
# Updated: stable spreads now flow to specialized profitability gate in ranker.
# ==============================================================================

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from .config import (
    ENABLE_STABLE_SWAP_STRATEGIES,
    STABLE_SWAP_MAX_PEG_DEVIATION_BPS,
    STABLE_SWAP_MIN_PROFIT_BPS,
)
from .ranker import CrossPoolSpread


PEG_GROUPS: dict[str, set[str]] = {
    "USD_STABLE": {
        "USDC",
        "USDC.e",
        "USDT",
        "DAI",
        "FRAX",
        "crvUSD",
        "miMATIC",
        "MAI",
        "TUSD",
        "pUSD",
    },
    "EUR_STABLE": {
        "EURS",
        "EURT",
        "jEUR",
        "PAR",
        "agEUR",
        "EURe",
        "EURO3",
    },
}


@dataclass(frozen=True)
class PeggedStableSpread:
    spread: CrossPoolSpread
    peg_group: str
    buy_deviation_bps: Decimal
    sell_deviation_bps: Decimal
    max_deviation_bps: Decimal
    strategy: str = "PEGGED_STABLE_TWO_LEG"


def peg_group_for(symbol: str) -> str:
    for group, symbols in PEG_GROUPS.items():
        if symbol in symbols:
            return group
    return ""


def same_peg_group(path: Iterable[str]) -> str:
    groups = {peg_group_for(symbol) for symbol in path}
    groups.discard("")
    return groups.pop() if len(groups) == 1 else ""


def _deviation_bps(price: Decimal, peg: Decimal = Decimal("1")) -> Decimal:
    if peg <= 0:
        return Decimal("0")
    return abs(price - peg) / peg * Decimal("10000")


def detect_pegged_stable_spreads(
    spreads: list[CrossPoolSpread],
    *,
    min_profit_bps: Decimal | None = None,
    max_peg_deviation_bps: Decimal | None = None,
) -> list[PeggedStableSpread]:
    """
    Promote same-peg two-leg spreads into stable strategy candidates.

    These remain adapter/fork-gated later. This layer only proves the route is
    a same-peg A -> B -> A spread with distinct native liquidity destinations
    and bounded peg deviation.

    The specialized stable profitability gate (lower 0.25 USD / 0.10 risk buffer)
    is applied downstream in opportunity_ranker.score_pegged_stable_spreads.
    """
    if not ENABLE_STABLE_SWAP_STRATEGIES:
        return []

    min_profit = STABLE_SWAP_MIN_PROFIT_BPS if min_profit_bps is None else min_profit_bps
    max_deviation = (
        STABLE_SWAP_MAX_PEG_DEVIATION_BPS
        if max_peg_deviation_bps is None
        else max_peg_deviation_bps
    )

    stable: list[PeggedStableSpread] = []
    for spread in spreads:
        if spread.route_class != "NATIVE_POOL_ROUTE" or not spread.comparable:
            continue
        if len(spread.path) != 3 or spread.path[0] != spread.path[-1]:
            continue

        peg_group = same_peg_group(spread.path)
        if not peg_group:
            continue
        if spread.gross_profit_pct * Decimal("100") < min_profit:
            continue

        buy_dev = _deviation_bps(spread.buy_price)
        sell_dev = _deviation_bps(spread.sell_price)
        if max(buy_dev, sell_dev) > max_deviation:
            continue

        stable.append(PeggedStableSpread(
            spread=spread,
            peg_group=peg_group,
            buy_deviation_bps=buy_dev,
            sell_deviation_bps=sell_dev,
            max_deviation_bps=max(buy_dev, sell_dev),
        ))

    stable.sort(key=lambda item: item.spread.gross_profit_pct, reverse=True)
    return stable


def spread_key(spread: CrossPoolSpread) -> tuple:
    return (
        tuple(spread.path),
        tuple(spread.pool_sequence),
        spread.buy_liquidity_key,
        spread.sell_liquidity_key,
    )


def print_pegged_stable_spreads(spreads: list[PeggedStableSpread], top_n: int = 10) -> None:
    print("💱 PEGGED / STABLE TWO-LEG STRATEGY REPORT")
    print(f"   Same-peg stable candidates: {len(spreads)}")
    print("=" * 90)

    if not spreads:
        print("  ↳ No same-peg stable routes pass the current spread and peg-deviation bounds.")
        print("=" * 90)
        return

    for idx, item in enumerate(spreads[:top_n], 1):
        spread = item.spread
        print(
            f"\n  #{idx:<3} {' -> '.join(spread.path)}  "
            f"group={item.peg_group} gross={spread.gross_profit_pct:+.6f}% "
            f"max_depeg={item.max_deviation_bps:.4f}bps"
        )
        print(
            f"       BUY  {spread.buy_pool_id} {spread.buy_protocol:<12} "
            f"price={spread.buy_price:.12f} dev={item.buy_deviation_bps:.4f}bps"
        )
        print(
            f"       SELL {spread.sell_pool_id} {spread.sell_protocol:<12} "
            f"price={spread.sell_price:.12f} dev={item.sell_deviation_bps:.4f}bps"
        )

    if len(spreads) > top_n:
        print(f"\n  ... and {len(spreads) - top_n} additional stable candidates.")
    print("=" * 90)
