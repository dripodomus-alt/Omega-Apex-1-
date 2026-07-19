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
# ==============================================================================

import time
from decimal import Decimal
from typing import Dict, Optional

import requests

from .config import ONEINCH_API_KEY, COINGECKO_KEY
from . import rpc_layer, redis_cache
from .rpc_layer import TOKEN_ADDRESSES

# ── Chainlink AggregatorV3 feed addresses (Polygon mainnet) ───────────────────
CHAINLINK_FEEDS: Dict[str, str] = {
    "WPOL":  "0xAB594600376Ec9fD91F8e885dADF0CE036862dE0",   # MATIC/USD
    "POL":   "0xAB594600376Ec9fD91F8e885dADF0CE036862dE0",
    "WETH":  "0xF9680D99D6C9589e2a93a78A04A279e509205945",   # ETH/USD
    "WBTC":  "0xc907E116054Ad103354f2D350FD2514433D57F6f",   # BTC/USD
    "LINK":  "0xd9FFdb71EbE7496cC440152d43986Aae0AB76665",   # LINK/USD
    "AAVE":  "0x72484B12719E23115761D5DA1646945632979bB6",   # AAVE/USD
    "USDC":  "0xfE4A8cc5b5B2366C1B58Bea3858e81843581b2F7",   # USDC/USD
    "USDT":  "0x0A6513e40db6EB1b165753AD52E80663aeA50545",   # USDT/USD
    "DAI":   "0x4746DeC9e833A82EC7C2C1356372CcF2cfcD2F3D",   # DAI/USD
    "CRV":   "0x336584C8E6Dc19637A5b36206B1c79923111b405",   # CRV/USD
    "UNI":   "0xdf0Fb4e4F928d2dCB76f438575fDD8682386e13C",   # UNI/USD
    "BAL":   "0xD106B538F2A868c28Ca1Ec7E298C3325c0226b1b",   # BAL/USD
    "FRAX":  "0x00DBeB1e45485d53DF7C2F0dF1Aa0b6Dc30311d3",   # FRAX/USD
    "EURS":  "0x73366Fe0AA0Ded304479862808e02506FE556a98",   # EUR/USD
    "EURT":  "0x73366Fe0AA0Ded304479862808e02506FE556a98",
    "jEUR":  "0x73366Fe0AA0Ded304479862808e02506FE556a98",
    "PAR":   "0x73366Fe0AA0Ded304479862808e02506FE556a98",
}

_CL_ABI = [
    {"inputs": [], "name": "latestRoundData",
     "outputs": [{"name": "roundId",        "type": "uint80"},
                 {"name": "answer",          "type": "int256"},
                 {"name": "startedAt",       "type": "uint256"},
                 {"name": "updatedAt",       "type": "uint256"},
                 {"name": "answeredInRound", "type": "uint80"}],
     "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "decimals",
     "outputs": [{"name": "", "type": "uint8"}],
     "stateMutability": "view", "type": "function"},
]

# ── CoinGecko ID map ──────────────────────────────────────────────────────────
_CG_BASE = "https://api.coingecko.com/api/v3"
_CG_IDS: Dict[str, str] = {
    "WPOL":   "matic-network",              "POL":    "matic-network",
    "WETH":   "weth",                       "WBTC":   "wrapped-bitcoin",
    "USDC":   "usd-coin",                   "USDC.e": "usd-coin",
    "USDT":   "tether",                     "DAI":    "dai",
    "LINK":   "chainlink",                  "AAVE":   "aave",
    "CRV":    "curve-dao-token",            "UNI":    "uniswap",
    "BAL":    "balancer",                   "FRAX":   "frax",
    "crvUSD": "crvusd",                     "miMATIC": "mimatic",
    "EURS":   "stasis-eurs",                "jEUR":   "jarvis-synthetic-euro",
    "EURT":   "tether-eurt",               "SNX":    "havven",
    "SUSHI":  "sushi",                      "COMP":   "compound-governance-token",
    "YFI":    "yearn-finance",              "GRT":    "the-graph",
    "LDO":    "lido-dao",                   "SAND":   "the-sandbox",
    "MANA":   "decentraland",              "APE":    "apecoin",
    "QUICK":  "quick",                      "RETH":   "rocket-pool-eth",
    "CBETH":  "coinbase-wrapped-staked-eth",
}

# ── 1inch ─────────────────────────────────────────────────────────────────────
_1INCH_PRICE_URL = "https://api.1inch.dev/price/v1.1/137"

# ── DexScreener ───────────────────────────────────────────────────────────────
_DS_BASE = "https://api.dexscreener.com/latest/dex"
_DS_TVL_CACHE: Dict[str, tuple[float, Decimal, Decimal]] = {}
_DS_TVL_TTL_SECONDS = 300

class PriceUnavailable(RuntimeError):
    """Raised when a live USD price is unavailable for a token."""


TOKEN_USD_PRICE: Dict[str, Decimal] = {}
TOKEN_USD_SOURCE: Dict[str, str] = {}
_PRICE_LAST_REFRESH                 = 0.0
PRICE_TTL_SECONDS                   = 60


# ── Internal helpers ──────────────────────────────────────────────────────────

def _chainlink_price(symbol: str) -> Optional[Decimal]:
    """Reads latest USD price from a Chainlink AggregatorV3 feed."""
    from web3 import Web3 as _Web3
    feed_addr = CHAINLINK_FEEDS.get(symbol)
    if not feed_addr or not rpc_layer.RPC_LIVE or rpc_layer.w3 is None:
        return None
    try:
        contract     = rpc_layer.w3.eth.contract(
            address=_Web3.to_checksum_address(feed_addr), abi=_CL_ABI)
        _, answer, _, updated_at, _ = contract.functions.latestRoundData().call()
        decimals = contract.functions.decimals().call()
        if time.time() - updated_at > 3600:
            return None
        return Decimal(answer) / Decimal(10 ** decimals)
    except Exception:
        return None


def _chainlink_prices_multicall(symbols: list[str]) -> dict[str, Decimal]:
    """
    Bulk-fetches USD prices from multiple Chainlink feeds using a single multicall.
    This is significantly more efficient than individual calls.
    """
    from web3 import Web3 as _Web3
    if not rpc_layer.RPC_LIVE or rpc_layer.w3 is None:
        return {}

    calls = []
    valid_symbols = []
    for symbol in symbols:
        feed_addr = CHAINLINK_FEEDS.get(symbol)
        if not feed_addr:
            continue
        valid_symbols.append(symbol)
        contract = rpc_layer.w3.eth.contract(address=_Web3.to_checksum_address(feed_addr), abi=_CL_ABI)
        calls.append((feed_addr, True, rpc_layer._encode_fn(contract, "latestRoundData")))
        calls.append((feed_addr, True, rpc_layer._encode_fn(contract, "decimals")))

    if not calls:
        return {}

    try:
        results = rpc_layer.multicall3_aggregate(calls)
    except Exception as exc:
        print(f"  ⚠️  Chainlink multicall failed: {exc}")
        return {}

    prices: dict[str, Decimal] = {}
    for i, symbol in enumerate(valid_symbols):
        round_data_ok, round_data_bytes = results[i * 2]
        decimals_ok, decimals_bytes = results[i * 2 + 1]
        if not round_data_ok or not decimals_ok:
            continue
        if len(round_data_bytes or b"") < 32 * 5 or len(decimals_bytes or b"") < 32:
            continue
        try:
            _, answer, _, updated_at, _ = rpc_layer.w3.codec.decode(["uint80", "int256", "uint256", "uint256", "uint80"], round_data_bytes)
            decimals = rpc_layer.w3.codec.decode(["uint8"], decimals_bytes)[0]
        except Exception as exc:
            print(f"  ⚠️  Chainlink feed decode skipped for {symbol}: {type(exc).__name__}: {exc}")
            continue
        if time.time() - updated_at < 3600: # 1 hour freshness
            prices[symbol] = Decimal(answer) / (Decimal(10) ** decimals)
    return prices

def _coingecko_prices(symbols: list) -> Dict[str, Decimal]:
    """Bulk-fetches USD prices via CoinGecko /simple/price."""
    ids_map = {sym: _CG_IDS[sym] for sym in symbols if sym in _CG_IDS}
    if not ids_map:
        return {}
    headers = {"accept": "application/json"}
    if COINGECKO_KEY:
        headers["x-cg-demo-api-key"] = COINGECKO_KEY
    try:
        resp = requests.get(
            f"{_CG_BASE}/simple/price",
            params={"ids": ",".join(set(ids_map.values())), "vs_currencies": "usd"},
            headers=headers, timeout=8,
        )
        resp.raise_for_status()
        data       = resp.json()
        id_to_syms: Dict[str, list] = {}
        for sym, cg_id in ids_map.items():
            id_to_syms.setdefault(cg_id, []).append(sym)
        result: Dict[str, Decimal] = {}
        for cg_id, price_dict in data.items():
            price = Decimal(str(price_dict.get("usd", 0)))
            if price > 0:
                for sym in id_to_syms.get(cg_id, []):
                    result[sym] = price
        return result
    except Exception as exc:
        print(f"  ⚠️  CoinGecko unavailable: {exc}")
        return {}


def _1inch_prices(symbols: list) -> Dict[str, Decimal]:
    """Fetches USD prices from the 1inch Token Price API (requires free API key)."""
    if not ONEINCH_API_KEY:
        return {}
    addrs = [TOKEN_ADDRESSES[s] for s in symbols if s in TOKEN_ADDRESSES]
    if not addrs:
        return {}
    try:
        resp = requests.post(
            _1INCH_PRICE_URL,
            json={"tokens": addrs, "currency": "USD"},
            headers={"Authorization": "Bearer " + ONEINCH_API_KEY, "accept": "application/json"},
            timeout=8,
        )
        resp.raise_for_status()
        addr_to_price = {k.lower(): Decimal(str(v)) for k, v in resp.json().items()}
        result: Dict[str, Decimal] = {}
        for sym in symbols:
            addr = TOKEN_ADDRESSES.get(sym, "").lower()
            if addr in addr_to_price and addr_to_price[addr] > 0:
                result[sym] = addr_to_price[addr]
        return result
    except Exception as exc:
        print(f"  ⚠️  1inch price API unavailable: {exc}")
        return {}


def _fetch_live_price_for_symbol(symbol: str) -> tuple[Decimal | None, str]:
    """Fetches a live price for a single symbol from the oracle stack."""
    # 1. Chainlink (highest authority)
    cl_price = _chainlink_price(symbol)
    if cl_price is not None and cl_price > 0:
        return cl_price, "chainlink"

    # 2. 1inch
    inch_prices = _1inch_prices([symbol])
    if symbol in inch_prices:
        return inch_prices[symbol], "1inch"

    # 3. CoinGecko
    cg_prices = _coingecko_prices([symbol])
    if symbol in cg_prices:
        return cg_prices[symbol], "coingecko"

    # 4. DexScreener (final fallback for address-based tokens)
    address = TOKEN_ADDRESSES.get(symbol)
    if address:
        try:
            ds_price = dexscreener_token_price(address)
            if ds_price is not None and ds_price > 0:
                return ds_price, "dexscreener"
        except Exception:
            pass

    return None, ""


# ── Public API ────────────────────────────────────────────────────────────────

def dexscreener_token_price(token_address: str) -> Optional[Decimal]:
    """Returns USD spot price for a Polygon token address via DexScreener."""
    try:
        resp  = requests.get(f"{_DS_BASE}/tokens/{token_address}", timeout=8)
        resp.raise_for_status()
        pairs = [p for p in resp.json().get("pairs", []) if p.get("chainId") == "polygon"]
        if not pairs:
            return None
        best = max(pairs, key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0))
        ps   = best.get("priceUsd")
        return Decimal(ps) if ps else None
    except Exception:
        return None


def dexscreener_pool_tvl(pair_address: str) -> Decimal:
    """Returns live TVL (USD) for a Polygon pool address via DexScreener."""
    address_l = pair_address.lower()
    cache_key = redis_cache.key("oracle", "dexscreener_tvl", address_l)

    # 1. Check Redis cache
    cached = redis_cache.get_json(cache_key)
    if isinstance(cached, dict) and cached.get("tvl_usd"):
        try:
            return Decimal(str(cached["tvl_usd"]))
        except Exception:
            pass

    # 2. Check in-memory cache as a fallback
    cached_mem = _DS_TVL_CACHE.get(address_l)
    if cached_mem and time.time() - cached_mem[0] < _DS_TVL_TTL_SECONDS:
        return cached_mem[1]

    # 3. Fetch live from API
    try:
        resp  = requests.get(f"{_DS_BASE}/pairs/polygon/{pair_address}", timeout=8)
        resp.raise_for_status()
        pairs = resp.json().get("pairs", [])
        if not pairs:
            return Decimal("0")
        pair_data = pairs[0]
        tvl = Decimal(str(pair_data.get("liquidity", {}).get("usd") or 0))
        volume = Decimal(str(pair_data.get("volume", {}).get("h24") or 0))

        # 4. Store in both caches
        cache_payload = {"tvl_usd": str(tvl), "volume_24h_usd": str(volume)}
        redis_cache.set_json(cache_key, cache_payload, ttl=_DS_TVL_TTL_SECONDS)
        _DS_TVL_CACHE[address_l] = (time.time(), tvl, volume)

        return tvl
    except Exception:
        return Decimal("0")


def dexscreener_pool_tvls(pair_addresses: list[str]) -> Dict[str, dict[str, Decimal]]:
    """
    Returns live TVL and 24h volume for Polygon pair addresses.

    DexScreener supports one or multiple pair addresses in this endpoint. Values
    are cached in-process for the current validation/scanner cycle.
    """
    now = time.time()
    result: Dict[str, dict[str, Decimal]] = {}
    missing: list[str] = []
    for address in dict.fromkeys(a.lower() for a in pair_addresses if a):
        cached = _DS_TVL_CACHE.get(address)
        if cached and now - cached[0] < _DS_TVL_TTL_SECONDS:
            result[address] = {"tvl_usd": cached[1], "volume_24h_usd": cached[2]}
        else:
            missing.append(address)

    for idx in range(0, len(missing), 30):
        chunk = missing[idx: idx + 30]
        if not chunk:
            continue
        try:
            resp = requests.get(
                f"{_DS_BASE}/pairs/polygon/{','.join(chunk)}",
                timeout=10,
            )
            resp.raise_for_status()
            for pair in resp.json().get("pairs", []) or []:
                address = str(pair.get("pairAddress", "")).lower()
                if not address:
                    continue
                tvl = Decimal(str(pair.get("liquidity", {}).get("usd") or 0))
                volume = Decimal(str(pair.get("volume", {}).get("h24") or 0))
                _DS_TVL_CACHE[address] = (now, tvl, volume)
                result[address] = {"tvl_usd": tvl, "volume_24h_usd": volume}
        except Exception:
            continue
    return result


def refresh_token_prices(force: bool = False) -> Dict[str, Decimal]:
    """
    Refreshes TOKEN_USD_PRICE from live sources in priority order:
      1. CoinGecko (no key required, broad coverage)
      2. 1inch (DeFi-native, requires free API key)
      3. Chainlink on-chain (most authoritative)

    Results are cached for PRICE_TTL_SECONDS to respect rate limits.
    """
    global TOKEN_USD_PRICE, TOKEN_USD_SOURCE, _PRICE_LAST_REFRESH
    if not force and (time.time() - _PRICE_LAST_REFRESH) < PRICE_TTL_SECONDS:
        return TOKEN_USD_PRICE

    updated: Dict[str, Decimal] = {}
    sources: Dict[str, str] = {}

    cg = _coingecko_prices(list(_CG_IDS.keys()))
    updated.update(cg)
    for sym in cg:
        sources[sym] = "coingecko"
    if cg:
        print(f"  📡 CoinGecko:  {len(cg)} prices fetched")

    inch = _1inch_prices(list(TOKEN_ADDRESSES.keys()))
    updated.update(inch)
    for sym in inch:
        sources[sym] = "1inch"
    if inch:
        print(f"  🔄 1inch:       {len(inch)} prices fetched")

    cl_prices = _chainlink_prices_multicall(list(CHAINLINK_FEEDS.keys()))
    updated.update(cl_prices)
    for sym in cl_prices:
        sources[sym] = "chainlink_multicall"
    if cl_prices:
        print(f"  🔗 Chainlink:  {len(cl_prices)} on-chain prices confirmed via multicall")

    TOKEN_USD_PRICE.clear()
    TOKEN_USD_PRICE.update(updated)
    TOKEN_USD_SOURCE.clear()
    TOKEN_USD_SOURCE.update(sources)
    _PRICE_LAST_REFRESH = time.time()
    return TOKEN_USD_PRICE


def token_price_usd(symbol: str) -> Decimal:
    """Returns a live-sourced cached USD price for a token symbol."""
    # 1. Check in-memory cache (fastest)
    price = TOKEN_USD_PRICE.get(symbol)
    if price is not None and price > 0:
        return price

    # 2. Check Redis cache (persistent)
    cache_key = redis_cache.key("oracle", "token_price_usd", symbol)
    cached = redis_cache.get_json(cache_key)
    if isinstance(cached, dict) and cached.get("price"):
        try:
            cached_price = Decimal(str(cached["price"]))
            if cached_price > 0:
                return cached_price
        except Exception:
            pass

    # 3. Fetch live price as a last resort
    live_price, source = _fetch_live_price_for_symbol(symbol)
    if live_price is not None and live_price > 0:
        # Store in Redis for next time
        redis_cache.set_json(
            cache_key,
            {"symbol": symbol, "price": str(live_price), "source": source},
            ttl=PRICE_TTL_SECONDS * 2,
        )
        return live_price

    # 4. Fail if no price can be found
    if price is None or price <= 0:
        raise PriceUnavailable(f"no live USD price available for {symbol}")
    return price
