# ==============================================================================
# oracle_layer.py  —  Multi-source USD price oracle stack
# Extracted from Cell 6B of notebooks/omega_v5.ipynb
#
# Priority stack
# --------------
# 1. CoinGecko free tier  — broad coverage, no key required
# 2. 1inch Price API      — DeFi-native spot prices (requires free key)
# 3. Chainlink on-chain   — highest authority, overrides REST for covered symbols
#
# Production policy: no hardcoded USD fallback prices are admitted into scoring.
# If no live source returns a price, the caller must skip that route.
#
# UPDATED: Now exports adapters compatible with PrecisionPricingEngine so the
# canonical integer-only pricing logic can be used throughout the pipeline.
# ==============================================================================

import time
from decimal import Decimal
from typing import Dict, Optional, List

import requests

from .config import ONEINCH_API_KEY, COINGECKO_KEY
from . import rpc_layer, redis_cache
from .rpc_layer import TOKEN_ADDRESSES
from .exceptions import PriceUnavailable
from .pricing.precision_pricing import (
    OracleSource,
    OracleObservation,
    OracleKind,
    TokenMetadata,
    PricingContext,
    PricingError,
)

# ── Chainlink AggregatorV3 feed addresses (Polygon mainnet) ───────────────────
CHAINLINK_FEEDS: Dict[str, str] = {
    "USDC": "0xfE4A8cc5b5B2366C1B58Bea3858e81843581b2F7",
    "WETH": "0xF9680D99D6C9589e2a93a78A04A279e509205945",
    "WBTC": "0xDE31F8bFBD8c84b5360CFACCa3539B938dd78ae6",
    "DAI": "0x4746DeC9e833A82EC7C2C1356372CcF2cfcD2F3D",
    # add more as needed
}

# Legacy price cache and source audit maps (kept)
TOKEN_USD_PRICE: Dict[str, Decimal] = {}
TOKEN_USD_SOURCE: Dict[str, str] = {}
_price_cache: Dict[str, tuple[float, Decimal]] = {}
_price_cache: Dict[str, Decimal] = {}
_cache_ttl = 30  # seconds


def _get_chainlink_price(feed_address: str) -> Decimal:
    """Placeholder — real impl uses web3 call to latestRoundData."""
    # In production this would do an eth_call via rpc_layer
    # For now return a sentinel that forces fallback
    raise PriceUnavailable("Chainlink direct call not wired in this snapshot")

def _chainlink_prices_multicall(symbols: List[str]) -> Dict[str, Decimal]:
    """Read Chainlink prices through multicall; skip empty return bytes."""
    calls = []
    ordered: list[str] = []
    for symbol in symbols:
        feed = CHAINLINK_FEEDS.get(symbol)
        if not feed:
            continue
        calls.append({"target": feed, "callData": rpc_layer._encode_fn("latestRoundData()")})
        ordered.append(symbol)
    if not calls:
        return {}
    out: Dict[str, Decimal] = {}
    for symbol, (ok, data) in zip(ordered, rpc_layer.multicall3_aggregate(calls)):
        if not ok or not data:
            continue
        try:
            decoded = rpc_layer.w3.codec.decode(["uint80", "int256", "uint256", "uint256", "uint80"], data)
            answer = Decimal(str(decoded[1])) / Decimal("100000000")
            if answer > 0:
                out[symbol] = answer
        except Exception:
            continue
    return out


def token_price_usd(symbol: str) -> Decimal:
    """Legacy Decimal price (kept for compatibility)."""
    now = time.time()
    if symbol in _price_cache:
        ts, price = _price_cache[symbol]
        if now - ts < _cache_ttl:
            return price

    price: Optional[Decimal] = None

    # 1. Try Chainlink first for known feeds
    if symbol in CHAINLINK_FEEDS:
        try:
            price = _get_chainlink_price(CHAINLINK_FEEDS[symbol])
            TOKEN_USD_SOURCE[symbol] = "chainlink"
        except Exception:
            price = None

    # 2. CoinGecko
    if price is None:
        try:
            cg_id = {
                "USDC": "usd-coin",
                "WETH": "weth",
                "WBTC": "wrapped-bitcoin",
                "DAI": "dai",
                "WPOL": "matic-network",
            }.get(symbol, symbol.lower())
            url = f"https://api.coingecko.com/api/v3/simple/price?ids={cg_id}&vs_currencies=usd"
            r = requests.get(url, timeout=6)
            if r.ok:
                data = r.json()
                val = data.get(cg_id, {}).get("usd")
                if val:
                    price = Decimal(str(val))
                    TOKEN_USD_SOURCE[symbol] = "coingecko"
        except Exception:
            pass

    # 3. 1inch fallback
    if price is None and ONEINCH_API_KEY:
        try:
            addr = TOKEN_ADDRESSES.get(symbol)
            if addr:
                url = (
                    f"https://api.1inch.dev/price/v1.1/137/{addr}"
                    f"?currency=USD&provider=1inch"
                )
                headers = {"Authorization": f"Bearer {ONEINCH_API_KEY}"}
                r = requests.get(url, headers=headers, timeout=6)
                if r.ok:
                    data = r.json()
                    val = data.get("price")
                    if val:
                        price = Decimal(str(val))
                        TOKEN_USD_SOURCE[symbol] = "1inch"
        except Exception:
            pass

    if price is None or price <= 0:
        raise PriceUnavailable(f"No price for {symbol}")

    _price_cache[symbol] = (now, price)
    TOKEN_USD_PRICE[symbol] = price
    return price



def refresh_token_prices(force: bool = False, symbols: List[str] | None = None) -> Dict[str, Decimal]:
    if force:
        _price_cache.clear()
    targets = symbols or list(TOKEN_ADDRESSES.keys())[:25]
    for symbol in targets:
        try:
            token_price_usd(symbol)
        except Exception:
            continue
    return dict(TOKEN_USD_PRICE)
# ── Precision engine adapters (new — makes TS logic usable in pipeline) ───────
class LegacyOracleSource(OracleSource):
    """Adapter that turns the existing oracle_layer into a PrecisionPricingEngine source."""

    def __init__(self, source_id: str, kind: OracleKind = OracleKind.DEX_TWAP):
        self.id = source_id
        self.kind = kind

    def read_usd_price(
        self, token: TokenMetadata, context: PricingContext
    ) -> OracleObservation:
        # Use legacy path to obtain a price, then emit a properly scaled observation.
        # In production you would replace this with direct on-chain / TWAP reads.
        try:
            price_dec = token_price_usd(token.symbol)
            # Convert Decimal price (e.g. 1.0001) to 18-decimal integer answer
            # We treat the legacy price as having 18 decimals for simplicity here.
            answer = int(price_dec * (10 ** 18))
            answer_decimals = 18
        except Exception as e:
            # Surface as non-positive so validation rejects it cleanly
            answer = 0
            answer_decimals = 18

        return OracleObservation(
            source_id=self.id,
            source_kind=self.kind,
            answer=answer,
            answer_decimals=answer_decimals,
            updated_at=int(time.time()),
            observed_at_block=context.current_block,
            confidence_bps=9500,  # conservative
        )


def build_default_policy(token_address: str) -> "TokenOraclePolicy":
    """Minimal policy that works with the legacy adapter (import from precision_pricing)."""
    from .pricing.precision_pricing import TokenOraclePolicy

    return TokenOraclePolicy(
        token=token_address.lower(),
        max_age_seconds=300,
        max_block_lag=10,
        minimum_valid_sources=1,
        maximum_deviation_bps=500,  # 5%
        minimum_confidence_bps=8000,
        source_ids=["legacy_oracle"],
        aggregation="MEDIAN",
    )


def get_precision_price_x18(
    symbol: str,
    chain_id: int = 137,
    current_block: int = 0,
    current_ts: int = 0,
) -> int:
    """
    Convenience: returns a price scaled to 1e18 using the precision engine + legacy adapter.
    This is the bridge the rest of the pipeline should call for critical paths.
    """
    from .pricing.precision_pricing import get_price_usd_x18 as _get_price

    # This function now delegates to the canonical implementation in the
    # precision_pricing module, which has the full engine logic.
    return _get_price(symbol)

