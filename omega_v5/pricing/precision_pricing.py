# ==============================================================================
# precision_pricing.py -- Canonical integer-only pricing engine.
#
# Python port of the reference APEX-OMEGA TypeScript implementation.
# - All monetary values are integers (Python int has arbitrary precision).
# - Prices and USD values are scaled to 1e18.
# - All math uses integer-only operations (mul_div) to prevent float error.
# - Oracle policies (age, lag, deviation) are strictly enforced.
# ==============================================================================

from __future__ import annotations

import statistics
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


PRICE_SCALE = 10**18


class Rounding(Enum):
    DOWN = 0
    UP = 1


class PricingError(Exception):
    """Custom exception for pricing failures with specific error codes."""

    def __init__(self, message: str, code: str):
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True)
class TokenMetadata:
    chain_id: int
    address: str
    symbol: str
    decimals: int


@dataclass(frozen=True)
class PricingContext:
    chain_id: int
    current_block: int
    current_timestamp: int


class OracleKind(str, Enum):
    ONCHAIN_FEED = "ONCHAIN_FEED"
    DEX_TWAP = "DEX_TWAP"
    OFFCHAIN_API = "OFFCHAIN_API"


@dataclass(frozen=True)
class OracleObservation:
    source_id: str
    source_kind: OracleKind
    answer: int  # Raw oracle answer
    answer_decimals: int
    updated_at: int  # Unix timestamp
    observed_at_block: int
    confidence_bps: int = 9500  # 0-10000


@dataclass(frozen=True)
class TokenOraclePolicy:
    token: str  # Address
    max_age_seconds: int
    max_block_lag: int
    minimum_valid_sources: int
    maximum_deviation_bps: int
    minimum_confidence_bps: int
    source_ids: list[str]
    aggregation: str = "MEDIAN"  # MEDIAN | CONSERVATIVE_LOW | CONSERVATIVE_HIGH


@dataclass(frozen=True)
class PriceResult:
    price_usd_x18: int
    source_ids: list[str]
    aggregation: str
    deviation_bps: int
    max_deviation_bps: int
    min_confidence_bps: int


@dataclass(frozen=True)
class PricePair:
    base_price: PriceResult
    quote_price: PriceResult
    quote_per_base_x18: int


class OracleSource(ABC):
    id: str
    kind: OracleKind

    @abstractmethod
    def read_usd_price(self, token: TokenMetadata, context: PricingContext) -> OracleObservation:
        ...


def pow10(exponent: int) -> int:
    return 10**exponent


def mul_div(a: int, b: int, c: int, rounding: Rounding = Rounding.DOWN) -> int:
    if c == 0:
        raise ValueError("mul_div division by zero")
    if rounding == Rounding.UP:
        return (a * b + c - 1) // c
    return (a * b) // c


def scale_decimals(value: int, from_decimals: int, to_decimals: int) -> int:
    if from_decimals == to_decimals:
        return value
    if from_decimals > to_decimals:
        return value // pow10(from_decimals - to_decimals)
    return value * pow10(to_decimals - from_decimals)


class PrecisionPricingEngine:
    def __init__(
        self,
        tokens: list[TokenMetadata],
        policies: list[TokenOraclePolicy],
        sources: list[OracleSource],
    ):
        self.tokens = {t.address.lower(): t for t in tokens}
        self.policies = {p.token.lower(): p for p in policies}
        self.sources = {s.id: s for s in sources}

    def _validate_observation(
        self, obs: OracleObservation, policy: TokenOraclePolicy, context: PricingContext
    ) -> None:
        if obs.observed_at_block > context.current_block:
            raise PricingError("observation from future block", "INVALID_BLOCK")
        if context.current_block - obs.observed_at_block > policy.max_block_lag:
            raise PricingError("observation exceeds max block lag", "STALE_ORACLE_BLOCK")
        if context.current_timestamp - obs.updated_at > policy.max_age_seconds:
            raise PricingError("observation exceeds max age", "STALE_ORACLE_PRICE")
        if obs.confidence_bps < policy.minimum_confidence_bps:
            raise PricingError("observation confidence too low", "LOW_CONFIDENCE")

    def _aggregate_prices(self, prices: list[int], policy: TokenOraclePolicy) -> tuple[int, int]:
        if not prices:
            raise PricingError("no valid prices to aggregate", "NO_VALID_PRICES")
        if len(prices) < policy.minimum_valid_sources:
            raise PricingError("insufficient valid sources", "INSUFFICIENT_SOURCES")

        prices.sort()
        min_price, max_price = prices[0], prices[-1]
        if min_price <= 0:
            raise PricingError("aggregated price is zero or negative", "INVALID_AGGREGATION_PRICE")
        deviation_bps = mul_div(max_price - min_price, 10000, min_price)
        if deviation_bps > policy.maximum_deviation_bps:
            raise PricingError("oracle deviation exceeded", "ORACLE_DEVIATION_EXCEEDED")

        if policy.aggregation == "MEDIAN":
            aggregated = int(statistics.median(prices))
        elif policy.aggregation == "CONSERVATIVE_LOW":
            aggregated = min_price
        elif policy.aggregation == "CONSERVATIVE_HIGH":
            aggregated = max_price
        else:
            aggregated = int(statistics.median(prices))

        return aggregated, deviation_bps

    def get_usd_price(self, token_address: str, context: PricingContext) -> PriceResult:
        token_addr_lower = token_address.lower()
        token = self.tokens.get(token_addr_lower)
        if not token:
            raise PricingError(f"token not in registry: {token_address}", "UNKNOWN_TOKEN")

        policy = self.policies.get(token_addr_lower)
        if not policy:
            raise PricingError(f"no pricing policy for token: {token_address}", "NO_POLICY")

        valid_prices: list[int] = []
        valid_source_ids: list[str] = []

        for source_id in policy.source_ids:
            source = self.sources.get(source_id)
            if not source:
                continue
            try:
                obs = source.read_usd_price(token, context)
                self._validate_observation(obs, policy, context)
                scaled_price = scale_decimals(obs.answer, obs.answer_decimals, 18)
                valid_prices.append(scaled_price)
                valid_source_ids.append(source_id)
            except Exception:
                continue

        aggregated_price, deviation = self._aggregate_prices(valid_prices, policy)

        return PriceResult(
            price_usd_x18=aggregated_price,
            source_ids=valid_source_ids,
            aggregation=policy.aggregation,
            deviation_bps=deviation,
            max_deviation_bps=policy.maximum_deviation_bps,
            min_confidence_bps=policy.minimum_confidence_bps,
        )

    def derive_pair_price(
        self, base_token_address: str, quote_token_address: str, context: PricingContext
    ) -> PricePair:
        base_price = self.get_usd_price(base_token_address, context)
        quote_price = self.get_usd_price(quote_token_address, context)
        quote_per_base = mul_div(base_price.price_usd_x18, PRICE_SCALE, quote_price.price_usd_x18)
        return PricePair(
            base_price=base_price,
            quote_price=quote_price,
            quote_per_base_x18=quote_per_base,
        )

    def token_atomic_to_usd_x18(
        self, amount_atomic: int, token: TokenMetadata, price_usd_x18: int
    ) -> int:
        return mul_div(amount_atomic, price_usd_x18, pow10(token.decimals))

    def usd_x18_to_token_atomic(
        self, usd_x18: int, token: TokenMetadata, price_usd_x18: int
    ) -> int:
        return mul_div(usd_x18, pow10(token.decimals), price_usd_x18, Rounding.UP)

    def convert_token_atomic(
        self,
        amount_in_atomic: int,
        token_in: TokenMetadata,
        token_out: TokenMetadata,
        context: PricingContext,
    ) -> int:
        price_in = self.get_usd_price(token_in.address, context)
        price_out = self.get_usd_price(token_out.address, context)
        usd_value = self.token_atomic_to_usd_x18(
            amount_in_atomic, token_in, price_in.price_usd_x18
        )
        return self.usd_x18_to_token_atomic(
            usd_value, token_out, price_out.price_usd_x18
        )


def get_price_usd_x18(symbol: str, engine: PrecisionPricingEngine | None = None) -> int:
    """
    Convenience bridge to get a price scaled to 1e18 using the precision engine.
    Falls back to the legacy oracle_layer if no engine is provided.
    """
    from .. import rpc_layer
    from ..oracle_layer import LegacyOracleSource, build_default_policy

    if engine:
        # In real usage, the caller would pass a fully wired engine + context.
        # This path is for when the engine is already available.
        token_address = rpc_layer.TOKEN_ADDRESSES.get(symbol, "")
        if not token_address:
            return 0
        ctx = PricingContext(
            chain_id=rpc_layer.CHAIN_ID,
            current_block=rpc_layer.BLOCK,
            current_timestamp=int(time.time()),
        )
        try:
            return engine.get_usd_price(token_address, ctx).price_usd_x18
        except PricingError:
            return 0

    # Legacy fallback path (Decimal -> scaled int)
    from ..oracle_layer import token_price_usd

    try:
        price_dec = token_price_usd(symbol)
        if price_dec <= 0:
            return 0
        # Convert Decimal price to 1e18 integer
        return int(price_dec * PRICE_SCALE)
    except Exception:
        return 0