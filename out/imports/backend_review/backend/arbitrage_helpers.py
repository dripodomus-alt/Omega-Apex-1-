"""
ARBITRAGE HELPERS — Pure functions extracted from arbitrage_engine.py
Phase A refactor: keeps math identical, but isolates concerns for testability.

These helpers contain ONLY pure logic (no engine state). They mirror the
original inline behavior of `_analyze_basic()` step-by-step.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


# Polygon stablecoins (lowercased)
STABLECOINS = (
    "0x2791bca1f2de4661ed88a30c99a7a9449aa84174",  # USDC
    "0xc2132d05d31c914a87c6611c10748aeb04b58e8f",  # USDT
    "0x8f3cf7ad23cd3cadbd9735aff958023239c6a063",  # DAI
)

MAX_SLIPPAGE_PCT_DEFAULT = 2.0  # 2% per leg cap


@dataclass
class PairValidation:
    """Result of validating a candidate pool-pair for arbitrage."""
    ok: bool
    reason: str = ""
    pool1_price: float = 0.0
    pool2_price: float = 0.0
    min_reserve: float = 0.0


@dataclass
class Direction:
    """Selected buy/sell direction with prices."""
    buy_pool: object  # PoolPrice
    sell_pool: object  # PoolPrice
    buy_price: float
    sell_price: float
    tokens_reversed: bool


def validate_pair(pool1, pool2, loan_amount_usd: float, min_reserve_usd: float) -> PairValidation:
    """
    Validate a candidate pool pair for arbitrage.

    Checks (in order, preserving original behavior):
      1. Same token pair
      2. Minimum reserves
      3. Loan size vs MAX_TVL_FRACTION on each pool
      4. Non-zero spot prices
    """
    # 1. Same pair?
    if frozenset([pool1.token0, pool1.token1]) != frozenset([pool2.token0, pool2.token1]):
        return PairValidation(False, "different_pairs")

    # 2. Reserve floor
    min_reserve = min(pool1.reserve_usd, pool2.reserve_usd)
    if min_reserve < min_reserve_usd:
        return PairValidation(False, "below_min_reserve", min_reserve=min_reserve)

    # 3. Spot prices
    p1 = pool1.reserve1 / pool1.reserve0 if pool1.reserve0 > 0 else 0
    p2 = pool2.reserve1 / pool2.reserve0 if pool2.reserve0 > 0 else 0

    # 4. TVL fraction guard
    max_tvl_fraction = float(os.getenv('MAX_TVL_FRACTION', '0.10'))
    if loan_amount_usd > pool1.reserve_usd * max_tvl_fraction:
        return PairValidation(False, "loan_exceeds_pool1_fraction", p1, p2, min_reserve)
    if loan_amount_usd > pool2.reserve_usd * max_tvl_fraction:
        return PairValidation(False, "loan_exceeds_pool2_fraction", p1, p2, min_reserve)

    if p1 <= 0 or p2 <= 0:
        return PairValidation(False, "zero_spot_price", p1, p2, min_reserve)

    return PairValidation(True, "ok", p1, p2, min_reserve)


def select_direction(pool1, pool2, p1: float, p2: float) -> Direction:
    """
    Pick buy (lowest price) and sell (highest price) pool.
    Compute whether sell_pool token order is reversed vs buy_pool.
    """
    if p1 < p2:
        buy_pool, sell_pool = pool1, pool2
        buy_price, sell_price = p1, p2
    else:
        buy_pool, sell_pool = pool2, pool1
        buy_price, sell_price = p2, p1

    tokens_reversed = (
        buy_pool.token0.lower() == sell_pool.token1.lower()
        and buy_pool.token1.lower() == sell_pool.token0.lower()
    )
    tokens_match = (
        buy_pool.token0.lower() == sell_pool.token0.lower()
        and buy_pool.token1.lower() == sell_pool.token1.lower()
    )
    if not tokens_match and not tokens_reversed:
        # Caller should bail; signal via tokens_reversed=False on impossible state
        # (validate_pair already guarantees pair equality, so this should not occur)
        pass

    return Direction(
        buy_pool=buy_pool,
        sell_pool=sell_pool,
        buy_price=buy_price,
        sell_price=sell_price,
        tokens_reversed=tokens_reversed,
    )


def has_stablecoin_anchor(buy_pool) -> bool:
    """Pair must contain a stablecoin so we can anchor USD pricing."""
    return (
        buy_pool.token0.lower() in STABLECOINS
        or buy_pool.token1.lower() in STABLECOINS
    )


def simulate_two_legs(
    swap_simulator,
    direction: Direction,
    loan_amount_token0_normalized: float,
):
    """
    Run leg1 (token0->token1 on buy_pool) and leg2 (token1->token0 on sell_pool).
    Returns (leg1_result, leg2_result, leg1_out_decimals, leg2_out_decimals).

    Handles token-reversal between buy_pool and sell_pool exactly as the
    original inline code did.
    """
    bp = direction.buy_pool
    sp = direction.sell_pool

    leg1_result = swap_simulator.simulate_swap(
        amount_in=loan_amount_token0_normalized,
        reserve_in=bp.reserve0,
        reserve_out=bp.reserve1,
        fee_bps=bp.fee // 100,
        protocol=bp.protocol,
        weight_in=bp.weight0,
        weight_out=bp.weight1,
        sqrt_price_x96=bp.sqrt_price_x96,
        liquidity=bp.liquidity,
        tick=bp.tick,
        token_in_decimals=bp.token0_decimals,
        token_out_decimals=bp.token1_decimals,
    )

    amount_token1 = leg1_result.amount_out

    if direction.tokens_reversed:
        leg2_result = swap_simulator.simulate_swap(
            amount_in=amount_token1,
            reserve_in=sp.reserve0,   # sp.token0 == bp.token1
            reserve_out=sp.reserve1,  # sp.token1 == bp.token0
            fee_bps=sp.fee // 100,
            protocol=sp.protocol,
            weight_in=sp.weight0,
            weight_out=sp.weight1,
            sqrt_price_x96=sp.sqrt_price_x96,
            liquidity=sp.liquidity,
            tick=sp.tick,
            token_in_decimals=sp.token0_decimals,
            token_out_decimals=sp.token1_decimals,
        )
        leg1_out_decimals = bp.token1_decimals
        leg2_out_decimals = sp.token1_decimals
    else:
        leg2_result = swap_simulator.simulate_swap(
            amount_in=amount_token1,
            reserve_in=sp.reserve1,
            reserve_out=sp.reserve0,
            fee_bps=sp.fee // 100,
            protocol=sp.protocol,
            weight_in=sp.weight1,
            weight_out=sp.weight0,
            sqrt_price_x96=sp.sqrt_price_x96,
            liquidity=sp.liquidity,
            tick=sp.tick,
            token_in_decimals=sp.token1_decimals,
            token_out_decimals=sp.token0_decimals,
        )
        leg1_out_decimals = bp.token1_decimals
        leg2_out_decimals = sp.token0_decimals

    return leg1_result, leg2_result, leg1_out_decimals, leg2_out_decimals


def calculate_capped_slippage(
    leg1_amm_pct: float,
    leg2_amm_pct: float,
    loan_amount_usd: float,
    leg1_amount_out_usd: float,
    cap_pct: float = MAX_SLIPPAGE_PCT_DEFAULT,
) -> Tuple[float, float, float, float]:
    """
    Return (leg1_slip_pct_capped, leg2_slip_pct_capped, leg1_slip_usd, leg2_slip_usd).
    """
    leg1_capped = min(leg1_amm_pct, cap_pct)
    leg2_capped = min(leg2_amm_pct, cap_pct)
    leg1_slip_usd = loan_amount_usd * (leg1_capped / 100.0)
    leg2_slip_usd = leg1_amount_out_usd * (leg2_capped / 100.0)
    return leg1_capped, leg2_capped, leg1_slip_usd, leg2_slip_usd
