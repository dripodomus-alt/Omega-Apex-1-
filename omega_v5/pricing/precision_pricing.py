#!/usr/bin/env python3
# ==============================================================================
# precision_pricing.py — Python port of APEX Ω Precision Pricing Engine
#
# Makes the canonical TS logic (BigInt-only, 18-decimal scale, strict oracle
# validation, mulDiv, aggregation) fully compatible with the Omega V5 pipeline.
#
# All monetary math uses native Python int (arbitrary precision, no float/Decimal
# for core price paths). Matches the TS contract exactly for cross-language
# consistency in the execution pipeline.
#
# Responsibilities (from TS):
# 1. Resolve token decimals.
# 2. Resolve oracle decimals.
# 3. Normalize every oracle price into PRICE_SCALE (1e18).
# 4. Convert token atomic units into USD fixed-point units.
# 5. Convert USD values back into token atomic units.
# 6. Derive TOKEN_A / TOKEN_B cross prices.
# 7. Reject stale, invalid, incomplete, or divergent prices.
# 8. Preserve integer precision throughout the execution pipeline.
# ==============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Protocol, Tuple

# ── Constants (exact match to TS) ─────────────────────────────────────────────
PRICE_DECIMALS: int = 18
PRICE_SCALE: int = 10 ** PRICE_DECIMALS

BPS_DENOMINATOR: int = 10_000


class OracleKind(str, Enum):
    CHAINLINK = "CHAINLINK"
    DEX_TWAP = "DEX_TWAP"
    PROTOCOL_RATE = "PROTOCOL_RATE"
    MANUAL_DISABLED = "MANUAL_DISABLED"


@dataclass
class TokenMetadata:
    chain_id: int
    address: str  # 0x...
    symbol: str
    decimals: int


@dataclass
class OracleObservation:
    source_id: str
    source_kind: OracleKind

    # Oracle answer before normalization (e.g. 8-decimal feed -> 100000000 for $1)
    answer: int
    answer_decimals: int

    updated_at: int  # unix seconds
    observed_at_block: int

    round_id: Optional[int] = None
    answered_in_round: Optional[int] = None
    confidence_bps: Optional[int] = None


class OracleSource(Protocol):
    """Returns the USD price for exactly one whole token."""
    id: str
    kind: OracleKind

    def read_usd_price(
        self, token: TokenMetadata, context: PricingContext
    ) -> OracleObservation:
        ...


@dataclass
class PricingContext:
    chain_id: int
    current_block: int
    current_timestamp: int


@dataclass
class TokenOraclePolicy:
    token: str  # address lower
    max_age_seconds: int
    max_block_lag: int
    minimum_valid_sources: int
    maximum_deviation_bps: int
    minimum_confidence_bps: int
    source_ids: List[str]
    aggregation: str  # "MEDIAN" | "CONSERVATIVE_LOW" | "CONSERVATIVE_HIGH"


@dataclass
class PriceResult:
    token: TokenMetadata
    price_usd_x18: int  # USD price of 1 whole token @ 18 decimals
    observed_at_block: int
    updated_at: int
    sources_used: List[str]
    source_deviation_bps: int
    confidence_bps: int


@dataclass
class PricePair:
    base: TokenMetadata
    quote: TokenMetadata
    quote_per_base_x18: int  # quote units per 1 base, scaled 1e18
    base_usd_x18: int
    quote_usd_x18: int


class PricingError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.name = "PricingError"


class Rounding(str, Enum):
    DOWN = "DOWN"
    UP = "UP"
    NEAREST = "NEAREST"


class PrecisionPricingEngine:
    """Python port of the TS PrecisionPricingEngine.

    Registers tokens, policies, and sources. Provides exact integer pricing
    for the arbitrage/execution pipeline.
    """

    def __init__(
        self,
        tokens: List[TokenMetadata],
        policies: List[TokenOraclePolicy],
        sources: List[OracleSource],
    ):
        self.tokens: Dict[str, TokenMetadata] = {}
        self.policies: Dict[str, TokenOraclePolicy] = {}
        self.sources: Dict[str, OracleSource] = {}

        for token in tokens:
            self._validate_decimals(token.decimals, "token")
            key = self._key(token.chain_id, token.address)
            self.tokens[key] = token

        for policy in policies:
            self.policies[policy.token.lower()] = policy

        for source in sources:
            self.sources[source.id] = source

    def get_token(self, chain_id: int, address: str) -> TokenMetadata:
        key = self._key(chain_id, address)
        token = self.tokens.get(key)
        if not token:
            raise PricingError(
                "TOKEN_NOT_REGISTERED",
                f"No metadata exists for {chain_id}:{address}",
            )
        return token

    def get_usd_price(
        self, token_address: str, context: PricingContext
    ) -> PriceResult:
        token = self.get_token(context.chain_id, token_address)
        policy = self.policies.get(token_address.lower())

        if not policy:
            raise PricingError(
                "POLICY_NOT_REGISTERED",
                f"No oracle policy exists for {token.symbol}",
            )

        observations: List[OracleObservation] = []
        failures: List[str] = []

        for source_id in policy.source_ids:
            source = self.sources.get(source_id)
            if not source:
                failures.append(f"{source_id}:SOURCE_NOT_REGISTERED")
                continue

            try:
                observation = source.read_usd_price(token, context)
                self._validate_observation(observation, policy, context)
                observations.append(observation)
            except Exception as exc:  # broad to capture PricingError + source errors
                msg = str(exc)
                failures.append(f"{source_id}:{msg}")

        if len(observations) < policy.minimum_valid_sources:
            raise PricingError(
                "INSUFFICIENT_VALID_SOURCES",
                f"{token.symbol} requires {policy.minimum_valid_sources} "
                f"valid sources but received {len(observations)}. "
                f"Failures: {' | '.join(failures)}",
            )

        normalized = [
            {
                "observation": obs,
                "price_usd_x18": scale_decimals(
                    obs.answer, obs.answer_decimals, PRICE_DECIMALS
                ),
            }
            for obs in observations
        ]

        prices = [n["price_usd_x18"] for n in normalized]
        minimum = min_bigint(prices)
        maximum = max_bigint(prices)

        deviation_bps = calculate_deviation_bps(minimum, maximum)

        if deviation_bps > policy.maximum_deviation_bps:
            raise PricingError(
                "ORACLE_DEVIATION_EXCEEDED",
                f"{token.symbol} source deviation {deviation_bps} bps exceeds "
                f"{policy.maximum_deviation_bps} bps",
            )

        selected_price = aggregate_prices(
            prices, policy.aggregation  # type: ignore[arg-type]
        )

        return PriceResult(
            token=token,
            price_usd_x18=selected_price,
            observed_at_block=min_bigint([o.observed_at_block for o in observations]),
            updated_at=min_bigint([o.updated_at for o in observations]),
            sources_used=[o.source_id for o in observations],
            source_deviation_bps=deviation_bps,
            confidence_bps=min_bigint(
                [o.confidence_bps or BPS_DENOMINATOR for o in observations]
            ),
        )

    def token_atomic_to_usd_x18(
        self,
        amount_atomic: int,
        token: TokenMetadata,
        price_usd_x18: int,
        rounding: Rounding = Rounding.DOWN,
    ) -> int:
        assert_non_negative(amount_atomic)
        assert_positive(price_usd_x18)

        token_scale = pow10(token.decimals)
        return mul_div(amount_atomic, price_usd_x18, token_scale, rounding)

    def usd_x18_to_token_atomic(
        self,
        usd_value_x18: int,
        token: TokenMetadata,
        price_usd_x18: int,
        rounding: Rounding = Rounding.UP,
    ) -> int:
        assert_non_negative(usd_value_x18)
        assert_positive(price_usd_x18)

        return mul_div(
            usd_value_x18, pow10(token.decimals), price_usd_x18, rounding
        )

    def derive_pair_price(
        self,
        base: PriceResult,
        quote: PriceResult,
        rounding: Rounding = Rounding.DOWN,
    ) -> PricePair:
        assert_positive(quote.price_usd_x18)

        quote_per_base_x18 = mul_div(
            base.price_usd_x18, PRICE_SCALE, quote.price_usd_x18, rounding
        )

        return PricePair(
            base=base.token,
            quote=quote.token,
            quote_per_base_x18=quote_per_base_x18,
            base_usd_x18=base.price_usd_x18,
            quote_usd_x18=quote.price_usd_x18,
        )

    def convert_token_atomic(
        self,
        amount_in_atomic: int,
        token_in: TokenMetadata,
        token_in_usd_x18: int,
        token_out: TokenMetadata,
        token_out_usd_x18: int,
        rounding: Rounding = Rounding.UP,
    ) -> int:
        usd_value = self.token_atomic_to_usd_x18(
            amount_in_atomic, token_in, token_in_usd_x18, rounding
        )
        return self.usd_x18_to_token_atomic(
            usd_value, token_out, token_out_usd_x18, rounding
        )

    def executable_price_x18(
        self,
        amount_in_atomic: int,
        token_in: TokenMetadata,
        amount_out_atomic: int,
        token_out: TokenMetadata,
        rounding: Rounding = Rounding.UP,
    ) -> int:
        assert_positive(amount_in_atomic)
        assert_positive(amount_out_atomic)

        numerator = amount_in_atomic * pow10(token_out.decimals) * PRICE_SCALE
        denominator = amount_out_atomic * pow10(token_in.decimals)
        return divide(numerator, denominator, rounding)

    # ── Private validation (exact TS logic) ───────────────────────────────────
    def _validate_observation(
        self,
        observation: OracleObservation,
        policy: TokenOraclePolicy,
        context: PricingContext,
    ) -> None:
        self._validate_decimals(observation.answer_decimals, "oracle")

        if observation.answer <= 0:
            raise PricingError(
                "NON_POSITIVE_ORACLE_PRICE",
                f"{observation.source_id} returned {observation.answer}",
            )

        if (
            observation.updated_at <= 0
            or context.current_timestamp < observation.updated_at
            or context.current_timestamp - observation.updated_at
            > policy.max_age_seconds
        ):
            raise PricingError(
                "STALE_ORACLE_PRICE",
                f"{observation.source_id} failed timestamp validation",
            )

        if (
            context.current_block < observation.observed_at_block
            or context.current_block - observation.observed_at_block
            > policy.max_block_lag
        ):
            raise PricingError(
                "ORACLE_BLOCK_LAG",
                f"{observation.source_id} exceeded block-lag policy",
            )

        if (
            observation.round_id is not None
            and observation.answered_in_round is not None
            and observation.answered_in_round < observation.round_id
        ):
            raise PricingError(
                "INCOMPLETE_ORACLE_ROUND",
                f"{observation.source_id} returned an incomplete round",
            )

        confidence = observation.confidence_bps or BPS_DENOMINATOR
        if confidence < policy.minimum_confidence_bps:
            raise PricingError(
                "LOW_ORACLE_CONFIDENCE",
                f"{observation.source_id} confidence {confidence} bps is below "
                f"{policy.minimum_confidence_bps} bps",
            )

    def _validate_decimals(self, decimals: int, type_: str) -> None:
        if not isinstance(decimals, int) or decimals < 0 or decimals > 36:
            code = (
                "INVALID_TOKEN_DECIMALS"
                if type_ == "token"
                else "INVALID_ORACLE_DECIMALS"
            )
            raise PricingError(
                code, f"{type_} decimals {decimals} are unsupported"
            )

    def _key(self, chain_id: int, address: str) -> str:
        return f"{chain_id}:{address.lower()}"


# ── Pure integer math helpers (exact port of TS) ──────────────────────────────
def scale_decimals(
    value: int,
    from_decimals: int,
    to_decimals: int,
    rounding: Rounding = Rounding.DOWN,
) -> int:
    assert_non_negative(value)

    if from_decimals == to_decimals:
        return value

    if from_decimals < to_decimals:
        return value * pow10(to_decimals - from_decimals)

    return divide(value, pow10(from_decimals - to_decimals), rounding)


def mul_div(
    x: int, y: int, denominator: int, rounding: Rounding = Rounding.DOWN
) -> int:
    if denominator == 0:
        raise PricingError("DIVISION_BY_ZERO", "mulDiv denominator is zero")
    return divide(x * y, denominator, rounding)


def divide(numerator: int, denominator: int, rounding: Rounding) -> int:
    if denominator == 0:
        raise PricingError("DIVISION_BY_ZERO", "Division denominator is zero")

    quotient = numerator // denominator
    remainder = numerator % denominator

    if remainder == 0 or rounding == Rounding.DOWN:
        return quotient

    if rounding == Rounding.UP:
        return quotient + 1

    # NEAREST
    return quotient + 1 if remainder * 2 >= denominator else quotient


def calculate_deviation_bps(minimum: int, maximum: int) -> int:
    assert_positive(minimum)
    return mul_div(maximum - minimum, BPS_DENOMINATOR, minimum, Rounding.UP)


def aggregate_prices(
    prices: List[int], mode: str
) -> int:
    if not prices:
        raise PricingError(
            "INSUFFICIENT_VALID_SOURCES", "No prices were supplied for aggregation"
        )

    sorted_prices = sorted(prices)

    if mode == "CONSERVATIVE_LOW":
        return sorted_prices[0]
    if mode == "CONSERVATIVE_HIGH":
        return sorted_prices[-1]

    # MEDIAN
    middle = len(sorted_prices) // 2
    if len(sorted_prices) % 2 == 1:
        return sorted_prices[middle]
    return (sorted_prices[middle - 1] + sorted_prices[middle]) // 2


def pow10(decimals: int) -> int:
    if not isinstance(decimals, int) or decimals < 0 or decimals > 36:
        raise PricingError(
            "UNSAFE_DECIMAL_EXPONENT", f"Unsupported decimal exponent {decimals}"
        )
    return 10 ** decimals


def assert_positive(value: int) -> None:
    if value <= 0:
        raise PricingError(
            "NON_POSITIVE_ORACLE_PRICE", f"Expected positive value; received {value}"
        )


def assert_non_negative(value: int) -> None:
    if value < 0:
        raise PricingError(
            "NEGATIVE_VALUE", f"Expected non-negative value; received {value}"
        )


def min_bigint(values: List[int]) -> int:
    if not values:
        raise PricingError(
            "INSUFFICIENT_VALID_SOURCES",
            "Cannot determine minimum of an empty collection",
        )
    return min(values)


def max_bigint(values: List[int]) -> int:
    if not values:
        raise PricingError(
            "INSUFFICIENT_VALID_SOURCES",
            "Cannot determine maximum of an empty collection",
        )
    return max(values)


# ── Convenience factory for pipeline integration ──────────────────────────────
def create_default_engine(
    tokens: List[TokenMetadata],
    policies: List[TokenOraclePolicy],
    sources: List[OracleSource],
) -> PrecisionPricingEngine:
    """Factory used by the pipeline to wire the precision engine."""
    return PrecisionPricingEngine(tokens, policies, sources)
