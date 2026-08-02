#!/usr/bin/env python3
# ==============================================================================
# amm_adapters.py -- dynamic invariant quote adapters.
# ==============================================================================

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

from .executable_quotes import quote_route_for_executor
from .invariant_math import quote_algebra_clmm
from .math_engine import DeFiEngineMath
from .pool_quality import clmm_audit_passed


@dataclass(frozen=True)
class Quote:
    token_in: str
    token_out: str
    amount_out: Decimal
    invariant: str


QuoteFn = Callable[[dict, Decimal], list[Quote]]


@dataclass(frozen=True)
class QuoteAdapter:
    protocol: str
    invariant: str
    quote: QuoteFn


_ADAPTERS: dict[str, QuoteAdapter] = {}


def register_adapter(adapter: QuoteAdapter) -> None:
    _ADAPTERS[adapter.protocol] = adapter


def adapter_for(protocol: str) -> QuoteAdapter | None:
    return _ADAPTERS.get(protocol)


def quote_pool(pool: dict, amount_in: Decimal) -> list[Quote]:
    adapter = adapter_for(pool.get("protocol", ""))
    if not adapter:
        return []
    if not clmm_audit_passed(pool):
        return []
    return adapter.quote(pool, amount_in)


def _quote_v2(pool: dict, amount_in: Decimal) -> list[Quote]:
    tokens = pool["tokens"]
    reserves = pool["reserves"]
    fee = pool["fee"]
    quotes: list[Quote] = []
    for i, j in [(0, 1), (1, 0)]:
        out = DeFiEngineMath.query_uniswap_v2(reserves[i], reserves[j], amount_in, fee)
        if out > 0:
            quotes.append(Quote(tokens[i], tokens[j], out, "constant_product"))
    return quotes


def _quote_v3(pool: dict, amount_in: Decimal) -> list[Quote]:
    tokens = pool["tokens"]
    quotes: list[Quote] = []
    sqrt_price = Decimal(str(pool.get("sqrtPriceX96", "0")))
    liquidity = Decimal(str(pool.get("liquidity", "0")))
    fee_fraction = Decimal(str(pool.get("fee", "0.0005")))

    if sqrt_price <= 0 or liquidity <= 0:
        return []
 
    for i, j in [(0, 1), (1, 0)]:
        # For Uniswap V3 and its direct forks, we can use the math engine.
        # The `zero_for_one` flag is determined by the swap direction.
        zero_for_one = i == 0
        amount_out = DeFiEngineMath.query_uniswap_v3(
            sqrt_price, liquidity, amount_in, zero_for_one, int(fee_fraction * 1000000)
        )

        if amount_out > 0:
            quotes.append(Quote(tokens[i], tokens[j], amount_out, "concentrated_liquidity"))
    return quotes


def _quote_curve(pool: dict, amount_in: Decimal) -> list[Quote]:
    tokens = pool["tokens"]
    reserves = pool["reserves"]
    amp = pool["A"]
    # Use the fee from the pool data, with a sensible default.
    # Curve fees are often expressed in units of 1/10**10, so we normalize.
    fee_raw = Decimal(str(pool.get("fee", "4000000"))) # Default to 4 bps
    fee = fee_raw / Decimal("1e10")

    quotes: list[Quote] = []
    for i in range(len(tokens)):
        for j in range(len(tokens)):
            if i == j:
                continue
            amounts_in = [Decimal("0")] * len(tokens)
            amounts_in[i] = amount_in
            # Pass a copy of reserves to prevent mutation across loop iterations.
            out = DeFiEngineMath.query_curve_stable(list(reserves), amounts_in, i, j, amp, fee)
            if out > 0:
                quotes.append(Quote(tokens[i], tokens[j], out, "stable_swap"))
    return quotes


def _quote_balancer(pool: dict, amount_in: Decimal) -> list[Quote]:
    tokens = pool["tokens"]
    reserves = pool["reserves"]
    weights = pool["weights"]
    swap_fee = pool["swap_fee"]
    quotes: list[Quote] = []
    for i in range(len(tokens)):
        for j in range(len(tokens)):
            if i == j:
                continue
            out = DeFiEngineMath.query_balancer_weighted(reserves, weights, amount_in, i, j, swap_fee)
            if out > 0:
                quotes.append(Quote(tokens[i], tokens[j], out, "weighted_invariant"))
    return quotes


def _quote_algebra(pool: dict, amount_in: Decimal) -> list[Quote]:
    """Adapter for Algebra-based CLMMs like QuickSwap V3."""
    tokens = pool["tokens"]
    quotes: list[Quote] = []
    sqrt_price = Decimal(str(pool.get("sqrtPriceX96", "0")))
    liquidity = Decimal(str(pool.get("liquidity", "0")))
    fee_fraction = Decimal(str(pool.get("fee", "0.0005")))

    if sqrt_price <= 0 or liquidity <= 0:
        return []

    for i, j in [(0, 1), (1, 0)]:
        zero_for_one = i == 0
        amount_out = quote_algebra_clmm(sqrt_price, liquidity, amount_in, zero_for_one, fee_fraction)
        if amount_out > 0:
            quotes.append(Quote(tokens[i], tokens[j], amount_out, "algebra_concentrated_liquidity"))
    return quotes


register_adapter(QuoteAdapter("UniswapV2", "constant_product", _quote_v2))
register_adapter(QuoteAdapter("UniswapV3", "concentrated_liquidity", _quote_v3))
register_adapter(QuoteAdapter("QuickSwapV3", "algebra_concentrated_liquidity", _quote_algebra))
register_adapter(QuoteAdapter("Algebra", "algebra_concentrated_liquidity", _quote_algebra))
register_adapter(QuoteAdapter("Curve", "stable_swap", _quote_curve))
register_adapter(QuoteAdapter("Balancer", "weighted_invariant", _quote_balancer))
