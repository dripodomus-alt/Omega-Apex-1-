#!/usr/bin/env python3
# ==============================================================================
# omega_v5/stable_swap_pricer.py
#
# High-precision stable-to-stable reference pricing. It reuses the repository's
# live oracle stack, which already prefers Chainlink on-chain prices via
# Multicall3 and falls back to supported REST sources without hardcoded prices.
# Redis caches the derived reference rate briefly to avoid repeated oracle work
# inside a scanner cycle.
# ==============================================================================

from __future__ import annotations

from decimal import Decimal, getcontext
from typing import Any, Optional

from . import redis_cache
from .oracle_layer import PriceUnavailable, TOKEN_USD_SOURCE, refresh_token_prices, token_price_usd

getcontext().prec = 36


class StableSwapPricer:
    """Calculates live reference rates between pegged assets."""

    def __init__(self, cache_ttl_seconds: int = 15):
        self.cache_ttl_seconds = max(1, int(cache_ttl_seconds))

    def _get_live_usd_price(self, symbol: str) -> Optional[Decimal]:
        cache_key = redis_cache.key("stable_pricer", "usd", symbol)
        cached = redis_cache.get_json(cache_key)
        if isinstance(cached, dict) and cached.get("price"):
            try:
                return Decimal(str(cached["price"]))
            except Exception:
                pass

        try:
            refresh_token_prices(force=False)
            price = token_price_usd(symbol)
        except (PriceUnavailable, ArithmeticError):
            return None
        if price <= 0:
            return None

        redis_cache.set_json(
            cache_key,
            {
                "symbol": symbol,
                "price": str(price),
                "source": TOKEN_USD_SOURCE.get(symbol, "oracle_layer"),
            },
            ttl=self.cache_ttl_seconds,
        )
        return price

    def get_stable_to_stable_rate(self, from_stable: str, to_stable: str) -> Optional[Decimal]:
        quote = self.get_stable_to_stable_quote(from_stable, to_stable)
        if not quote.get("ok"):
            return None
        return Decimal(str(quote["rate"]))

    def get_stable_to_stable_quote(self, from_stable: str, to_stable: str) -> dict[str, Any]:
        from_price_usd = self._get_live_usd_price(from_stable)
        to_price_usd = self._get_live_usd_price(to_stable)
        if from_price_usd is None or to_price_usd is None or to_price_usd <= 0:
            return {
                "ok": False,
                "from_stable": from_stable,
                "to_stable": to_stable,
                "from_price_usd": str(from_price_usd) if from_price_usd is not None else "0",
                "to_price_usd": str(to_price_usd) if to_price_usd is not None else "0",
                "rate": "0",
                "reason": "missing_live_stable_oracle_price",
                "from_source": TOKEN_USD_SOURCE.get(from_stable, ""),
                "to_source": TOKEN_USD_SOURCE.get(to_stable, ""),
            }

        rate = from_price_usd / to_price_usd
        return {
            "ok": True,
            "from_stable": from_stable,
            "to_stable": to_stable,
            "from_price_usd": str(from_price_usd),
            "to_price_usd": str(to_price_usd),
            "rate": str(rate),
            "from_source": TOKEN_USD_SOURCE.get(from_stable, "oracle_layer"),
            "to_source": TOKEN_USD_SOURCE.get(to_stable, "oracle_layer"),
            "rate_formula": "from_price_usd / to_price_usd",
            "cache_ttl_seconds": self.cache_ttl_seconds,
        }