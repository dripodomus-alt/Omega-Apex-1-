#!/usr/bin/env python3
# ==============================================================================
# amm_adapters.py -- dynamic invariant quote adapters.
# ==============================================================================

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

from .executable_quotes import quote_route_for_executor
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
    pool_id = str(pool.get("pool_id") or pool.get("registry_id") or pool.get("address") or "")
    for i, j in [(0, 1), (1, 0)]:
        executable_quote = quote_route_for_executor(
            [tokens[i], tokens[j]],
            [pool_id],
            {pool_id: pool},
            amount_in,
        )
        if executable_quote.clmm_proven and executable_quote.amount_out > 0:
            quotes.append(Quote(tokens[i], tokens[j], executable_quote.amount_out, "concentrated_liquidity_exact_quote"))
    return quotes


def _quote_curve(pool: dict, amount_in: Decimal) -> list[Quote]:
    tokens = pool["tokens"]
    reserves = pool["reserves"]
    amp = pool["A"]
    quotes: list[Quote] = []
    for i in range(len(tokens)):
        for j in range(len(tokens)):
            if i == j:
                continue
            amounts_in = [Decimal("0")] * len(tokens)
            amounts_in[i] = amount_in
            out = DeFiEngineMath.query_curve_stable(reserves, amounts_in, i, j, amp)
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


register_adapter(QuoteAdapter("UniswapV2", "constant_product", _quote_v2))
register_adapter(QuoteAdapter("UniswapV3", "concentrated_liquidity", _quote_v3))
register_adapter(QuoteAdapter("QuickSwapV3", "algebra_concentrated_liquidity", _quote_v3))
register_adapter(QuoteAdapter("Algebra", "algebra_concentrated_liquidity", _quote_v3))
register_adapter(QuoteAdapter("Curve", "stable_swap", _quote_curve))
register_adapter(QuoteAdapter("Balancer", "weighted_invariant", _quote_balancer))
