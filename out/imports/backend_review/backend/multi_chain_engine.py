"""
Multi-Chain Arbitrage Engine
Each chain runs a fully isolated scan: pool discovery, price matrix,
spread detection, profit filtering.

Strict rule: cross-DEX only within the same chain. No cross-chain arb.

Performance:
  - V2/V3 prices fetched via Multicall3 batch (1 RPC call per 300-pool chunk)
  - All 10 chains run concurrently via asyncio.gather
  - Execution payloads built inline on every spread ≥ min_spread_bps
  - Results broadcast immediately to ws_hub "mc_spreads" channel
"""

import os
import time
import logging
import asyncio
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

from web3 import Web3

from chain_config import CHAINS, get_all_chain_ids, ENABLED_CHAINS, get_chain
from multi_chain_rpc import get_multi_chain_rpc
from multi_chain_discovery import get_multi_chain_discovery

# Multicall3 — deployed at the same address on every major EVM chain
MULTICALL3_ADDRESS = "0xcA11bde05977b3631167028862bE2a173976CA11"
MULTICALL3_ABI = [{
    "inputs": [{"components": [
        {"name": "target",      "type": "address"},
        {"name": "allowFailure","type": "bool"},
        {"name": "callData",    "type": "bytes"},
    ], "name": "calls", "type": "tuple[]"}],
    "name": "aggregate3",
    "outputs": [{"components": [
        {"name": "success",    "type": "bool"},
        {"name": "returnData", "type": "bytes"},
    ], "name": "returnData", "type": "tuple[]"}],
    "stateMutability": "view",
    "type": "function",
}]

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
#  Data models
# ─────────────────────────────────────────────────────────────

@dataclass
class ChainPoolPrice:
    chain_id:        int
    pool_address:    str
    dex_name:        str
    protocol:        str
    token0_address:  str
    token1_address:  str
    token0_symbol:   str
    token1_symbol:   str
    token0_decimals: int
    token1_decimals: int
    reserve0:        float = 0.0
    reserve1:        float = 0.0
    price_t0_in_t1:  float = 0.0   # how many t1 per t0
    price_t1_in_t0:  float = 0.0   # how many t0 per t1
    liquidity_usd:   float = -1.0
    fee_bps:         int   = 30
    pool_id:         Optional[str] = None
    tokens:          List[str] = field(default_factory=list)
    last_updated:    float = field(default_factory=time.time)

    def mid_price(self) -> float:
        if self.price_t0_in_t1 <= 0:
            return 0.0
        return self.price_t0_in_t1

    def spread_bps(self, other: "ChainPoolPrice") -> float:
        """Spread (in bps) between this pool and another for the same pair."""
        if self.mid_price() <= 0 or other.mid_price() <= 0:
            return 0.0
        hi = max(self.mid_price(), other.mid_price())
        lo = min(self.mid_price(), other.mid_price())
        return ((hi - lo) / lo) * 10000


@dataclass
class ChainSpreadOpportunity:
    chain_id:         int
    chain_name:       str
    token0_symbol:    str
    token1_symbol:    str
    token0_address:   str
    token1_address:   str
    buy_pool:         str    # pool to buy from (lower ask)
    sell_pool:        str    # pool to sell to  (higher bid)
    buy_dex:          str
    sell_dex:         str
    buy_protocol:     str    = "v2"
    sell_protocol:    str    = "v2"
    buy_pool_meta:    Dict   = field(default_factory=dict)
    sell_pool_meta:   Dict   = field(default_factory=dict)
    token0_decimals:  int    = 18
    token1_decimals:  int    = 18
    spread_bps:       float  = 0.0
    buy_price:        float  = 0.0
    sell_price:       float  = 0.0
    buy_pool_tokenA_price_usd: float = 0.0
    sell_pool_tokenA_price_usd: float = 0.0
    buy_pool_token_prices: Dict = field(default_factory=dict)
    sell_pool_token_prices: Dict = field(default_factory=dict)
    estimated_profit_pct: float = 0.0
    liquidity_usd:    float  = 0.0
    buy_pool_liquidity_usd: float = 0.0
    sell_pool_liquidity_usd: float = 0.0
    execution_payload: Optional[Dict] = field(default=None)
    timestamp:        float  = field(default_factory=time.time)
    note:             str    = "Single-chain cross-DEX only. No cross-chain arbitrage."

    def to_dict(self) -> Dict:
        d = asdict(self)
        return d


# ─────────────────────────────────────────────────────────────
#  Per-chain price engine
# ─────────────────────────────────────────────────────────────

# Minimal pair ABI to read V2 reserves
V2_PAIR_ABI = [
    {"name": "getReserves", "outputs": [
        {"name": "_reserve0", "type": "uint112"},
        {"name": "_reserve1", "type": "uint112"},
        {"name": "_blockTimestampLast", "type": "uint32"},
    ], "inputs": [], "stateMutability": "view", "type": "function"},
    {"name": "token0", "outputs": [{"type": "address"}], "inputs": [], "stateMutability": "view", "type": "function"},
    {"name": "token1", "outputs": [{"type": "address"}], "inputs": [], "stateMutability": "view", "type": "function"},
]

# Minimal V3 pool slot0 ABI
V3_SLOT0_ABI = [
    {"name": "slot0", "outputs": [
        {"name": "sqrtPriceX96",   "type": "uint160"},
        {"name": "tick",           "type": "int24"},
        {"name": "observationIndex", "type": "uint16"},
        {"name": "observationCardinality", "type": "uint16"},
        {"name": "observationCardinalityNext", "type": "uint16"},
        {"name": "feeProtocol",    "type": "uint8"},
        {"name": "unlocked",       "type": "bool"},
    ], "inputs": [], "stateMutability": "view", "type": "function"},
    {"name": "liquidity", "outputs": [{"type": "uint128"}], "inputs": [], "stateMutability": "view", "type": "function"},
]


class ChainPriceEngine:
    """
    Fetches on-chain prices for all discovered pools on a single chain.
    Runs entirely isolated from other chains.
    """

    def __init__(self, chain_id: int):
        self.chain_id   = chain_id
        self.chain_cfg  = get_chain(chain_id)
        self.chain_name = self.chain_cfg["display"]
        self.rpc_mon    = get_multi_chain_rpc()
        self.discovery  = get_multi_chain_discovery()
        self._pools:    List[ChainPoolPrice] = []
        self._spreads:  List[ChainSpreadOpportunity] = []
        self._last_scan: float = 0.0

    def _get_w3(self) -> Optional[Web3]:
        return self.rpc_mon.get_web3(self.chain_id)

    @staticmethod
    def _estimate_liquidity_quote(reserve0: float, reserve1: float, price_t0_in_t1: float) -> float:
        if reserve0 <= 0 or reserve1 <= 0 or price_t0_in_t1 <= 0:
            return -1.0
        return max((reserve0 * price_t0_in_t1) + reserve1, 0.0)

    def _fetch_v2_price(self, w3: Web3, pool: Dict) -> Optional[ChainPoolPrice]:
        try:
            contract = w3.eth.contract(
                address=Web3.to_checksum_address(pool["pair_address"]),
                abi=V2_PAIR_ABI,
            )
            r0, r1, _ = contract.functions.getReserves().call()
            if r0 == 0 or r1 == 0:
                return None

            dec0 = pool.get("token0_decimals", 18)
            dec1 = pool.get("token1_decimals", 18)
            reserve0 = r0 / (10 ** dec0)
            reserve1 = r1 / (10 ** dec1)
            price_01 = reserve1 / reserve0  # price of token0 in terms of token1

            return ChainPoolPrice(
                chain_id        = self.chain_id,
                pool_address    = pool["pair_address"],
                dex_name        = pool.get("dex_name", "unknown"),
                protocol        = pool.get("protocol", "v2"),
                token0_address  = pool["token0_address"],
                token1_address  = pool["token1_address"],
                token0_symbol   = pool.get("token0_symbol", "T0"),
                token1_symbol   = pool.get("token1_symbol", "T1"),
                token0_decimals = dec0,
                token1_decimals = dec1,
                reserve0        = reserve0,
                reserve1        = reserve1,
                price_t0_in_t1  = price_01,
                price_t1_in_t0  = reserve0 / reserve1 if reserve1 > 0 else 0,
                fee_bps         = pool.get("fee_bps", 30),
            )
        except Exception as e:
            logger.debug(f"[Engine/{self.chain_name}] V2 price {pool['pair_address'][:10]}: {e}")
            return None

    def _fetch_v3_price(self, w3: Web3, pool: Dict) -> Optional[ChainPoolPrice]:
        try:
            contract = w3.eth.contract(
                address=Web3.to_checksum_address(pool["pair_address"]),
                abi=V3_SLOT0_ABI,
            )
            slot0 = contract.functions.slot0().call()
            sqrt_price_x96 = slot0[0]
            if sqrt_price_x96 == 0:
                return None

            liquidity = contract.functions.liquidity().call()
            dec0 = pool.get("token0_decimals", 18)
            dec1 = pool.get("token1_decimals", 18)

            # price = (sqrtPriceX96 / 2^96)^2 * 10^(dec0-dec1)
            sqrt_price = sqrt_price_x96 / (2 ** 96)
            price_raw  = sqrt_price ** 2
            price_adj  = price_raw * (10 ** dec0) / (10 ** dec1)

            return ChainPoolPrice(
                chain_id        = self.chain_id,
                pool_address    = pool["pair_address"],
                dex_name        = pool.get("dex_name", "unknown"),
                protocol        = pool.get("protocol", "v3"),
                token0_address  = pool["token0_address"],
                token1_address  = pool["token1_address"],
                token0_symbol   = pool.get("token0_symbol", "T0"),
                token1_symbol   = pool.get("token1_symbol", "T1"),
                token0_decimals = dec0,
                token1_decimals = dec1,
                price_t0_in_t1  = price_adj,
                price_t1_in_t0  = 1 / price_adj if price_adj > 0 else 0,
                liquidity_usd   = float(liquidity),
                fee_bps         = pool.get("fee_bps", 30),
            )
        except Exception as e:
            logger.debug(f"[Engine/{self.chain_name}] V3 price {pool['pair_address'][:10]}: {e}")
            return None

    def _fetch_curve_balancer_price(self, w3: Web3, pool: Dict) -> Optional[ChainPoolPrice]:
        """Price for Curve/Balancer pools via stored balances."""
        try:
            balances = pool.get("balances", [])
            tokens   = pool.get("tokens", [pool.get("token0_address"), pool.get("token1_address")])
            decimals = pool.get("decimals", [18, 18])

            if len(balances) < 2 or balances[0] == 0 or balances[1] == 0:
                return None

            dec0 = decimals[0] if decimals else 18
            dec1 = decimals[1] if len(decimals) > 1 else 18
            r0   = balances[0] / (10 ** dec0)
            r1   = balances[1] / (10 ** dec1)
            if r0 == 0 or r1 == 0:
                return None

            return ChainPoolPrice(
                chain_id        = self.chain_id,
                pool_address    = pool["pair_address"],
                dex_name        = pool.get("dex_name", "curve_stable"),
                protocol        = pool.get("protocol", "curve"),
                token0_address  = tokens[0] if tokens else "",
                token1_address  = tokens[1] if len(tokens) > 1 else "",
                token0_symbol   = pool.get("token0_symbol", "T0"),
                token1_symbol   = pool.get("token1_symbol", "T1"),
                token0_decimals = int(dec0),
                token1_decimals = int(dec1),
                reserve0        = r0,
                reserve1        = r1,
                price_t0_in_t1  = r1 / r0,
                price_t1_in_t0  = r0 / r1,
                liquidity_usd   = self._estimate_liquidity_quote(r0, r1, r1 / r0),
                fee_bps         = pool.get("fee_bps", 4),
                pool_id         = pool.get("pool_id"),
                tokens          = [str(t) for t in pool.get("tokens", []) if t],
            )
        except Exception as e:
            logger.debug(f"[Engine/{self.chain_name}] curve/bal price {pool.get('pair_address','')[:10]}: {e}")
            return None

    # ── Multicall3 batch price fetching ──────────────────────────

    def _multicall_contract(self, w3: Web3):
        return w3.eth.contract(
            address=Web3.to_checksum_address(MULTICALL3_ADDRESS),
            abi=MULTICALL3_ABI,
        )

    def _batch_fetch_v2(self, w3: Web3, pools: List[Dict], chunk_size: int = 300) -> Dict[str, Tuple]:
        """
        Fetch getReserves() for all V2 pools in chunked Multicall3 batches.
        Returns { pool_address_lower: (reserve0, reserve1) }
        """
        mc = self._multicall_contract(w3)
        # encode getReserves selector = 0x0902f1ac
        GET_RESERVES_SIG = bytes.fromhex("0902f1ac")
        results: Dict[str, Tuple] = {}

        chunks = [pools[i:i+chunk_size] for i in range(0, len(pools), chunk_size)]
        for chunk in chunks:
            calls = []
            addrs = []
            for p in chunk:
                addr = p["pair_address"]
                calls.append({
                    "target":       Web3.to_checksum_address(addr),
                    "allowFailure": True,
                    "callData":     GET_RESERVES_SIG,
                })
                addrs.append(addr.lower())
            try:
                raw = mc.functions.aggregate3(calls).call()
                for i, (ok, data) in enumerate(raw):
                    if ok and len(data) >= 64:
                        r0 = int.from_bytes(data[0:32],  "big") & ((1 << 112) - 1)
                        r1 = int.from_bytes(data[32:64], "big") & ((1 << 112) - 1)
                        results[addrs[i]] = (r0, r1)
            except Exception as e:
                logger.debug(f"[Engine/{self.chain_name}] V2 multicall chunk: {e}")
        return results

    def _batch_fetch_v3(self, w3: Web3, pools: List[Dict], chunk_size: int = 200) -> Dict[str, Tuple]:
        """
        Fetch slot0() + liquidity() for all V3 pools in Multicall3 batches.
        Returns { pool_address_lower: (sqrtPriceX96, liquidity) }
        """
        mc = self._multicall_contract(w3)
        SLOT0_SIG     = bytes.fromhex("3850c7bd")
        LIQUIDITY_SIG = bytes.fromhex("1a686502")
        results: Dict[str, Tuple] = {}

        chunks = [pools[i:i+chunk_size] for i in range(0, len(pools), chunk_size)]
        for chunk in chunks:
            calls, addrs = [], []
            for p in chunk:
                addr = p["pair_address"]
                cs   = Web3.to_checksum_address(addr)
                calls.append({"target": cs, "allowFailure": True, "callData": SLOT0_SIG})
                calls.append({"target": cs, "allowFailure": True, "callData": LIQUIDITY_SIG})
                addrs.append(addr.lower())
            try:
                raw = mc.functions.aggregate3(calls).call()
                for i, addr in enumerate(addrs):
                    slot0_ok, slot0_data = raw[i * 2]
                    liq_ok,   liq_data   = raw[i * 2 + 1]
                    if slot0_ok and liq_ok and len(slot0_data) >= 32 and len(liq_data) >= 32:
                        sqrt_price = int.from_bytes(slot0_data[0:32], "big")
                        liquidity  = int.from_bytes(liq_data[0:32],   "big")
                        results[addr] = (sqrt_price, liquidity)
            except Exception as e:
                logger.debug(f"[Engine/{self.chain_name}] V3 multicall chunk: {e}")
        return results

    def fetch_all_prices(self, max_pools: int = 500) -> List[ChainPoolPrice]:
        """
        Fetch prices for up to max_pools on this chain.
        V2 and V3 pools are priced via Multicall3 batch (1 RPC call per 300-pool chunk).
        Curve / Balancer pools use stored discovery balances — no extra RPC needed.
        """
        w3 = self._get_w3()
        if not w3:
            logger.error(f"[Engine/{self.chain_name}] no web3 connection")
            return []

        pools = self.discovery.get_cached(self.chain_id)
        if not pools:
            logger.info(f"[Engine/{self.chain_name}] no cached pools; running discovery first…")
            pools = self.discovery.discover_chain(self.chain_id)

        pools = pools[:max_pools]

        # Bucket pools by protocol
        v2_pools     = [p for p in pools if p.get("protocol", "").lower() in ("v2", "uniswap_v2", "pancake_v2", "quickswap", "sushiswap", "spookyswap", "traderjoe", "baseswap", "horizondex", "syncswap_v2") or (p.get("protocol","") not in ("v3","uniswap_v3","algebra") and "curve" not in p.get("protocol","") and "balancer" not in p.get("protocol",""))]
        v3_pools     = [p for p in pools if p.get("protocol", "").lower() in ("v3", "uniswap_v3", "algebra", "pancake_v3", "traderjoe_v3")]
        cb_pools     = [p for p in pools if "curve" in p.get("protocol","").lower() or "balancer" in p.get("protocol","").lower()]

        prices: List[ChainPoolPrice] = []

        # ── V2: batch Multicall3 ──────────────────────────────
        if v2_pools:
            t0 = time.time()
            batch_v2 = self._batch_fetch_v2(w3, v2_pools)
            logger.info(f"[Engine/{self.chain_name}] V2 multicall: {len(batch_v2)}/{len(v2_pools)} pools in {time.time()-t0:.2f}s")
            for p in v2_pools:
                addr = p["pair_address"].lower()
                if addr not in batch_v2:
                    continue
                r0_raw, r1_raw = batch_v2[addr]
                if r0_raw == 0 or r1_raw == 0:
                    continue
                dec0 = p.get("token0_decimals", 18)
                dec1 = p.get("token1_decimals", 18)
                r0   = r0_raw / (10 ** dec0)
                r1   = r1_raw / (10 ** dec1)
                prices.append(ChainPoolPrice(
                    chain_id        = self.chain_id,
                    pool_address    = p["pair_address"],
                    dex_name        = p.get("dex_name", "unknown_v2"),
                    protocol        = p.get("protocol", "v2"),
                    token0_address  = p.get("token0_address", ""),
                    token1_address  = p.get("token1_address", ""),
                    token0_symbol   = p.get("token0_symbol", "T0"),
                    token1_symbol   = p.get("token1_symbol", "T1"),
                    token0_decimals = dec0,
                    token1_decimals = dec1,
                    reserve0        = r0,
                    reserve1        = r1,
                    price_t0_in_t1  = r1 / r0 if r0 > 0 else 0,
                    price_t1_in_t0  = r0 / r1 if r1 > 0 else 0,
                    liquidity_usd   = self._estimate_liquidity_quote(r0, r1, (r1 / r0) if r0 > 0 else 0),
                    fee_bps         = p.get("fee_bps", 30),
                ))

        # ── V3: batch Multicall3 ──────────────────────────────
        if v3_pools:
            t0 = time.time()
            batch_v3 = self._batch_fetch_v3(w3, v3_pools)
            logger.info(f"[Engine/{self.chain_name}] V3 multicall: {len(batch_v3)}/{len(v3_pools)} pools in {time.time()-t0:.2f}s")
            for p in v3_pools:
                addr = p["pair_address"].lower()
                if addr not in batch_v3:
                    continue
                sqrt_price_x96, liquidity = batch_v3[addr]
                if sqrt_price_x96 == 0:
                    continue
                dec0     = p.get("token0_decimals", 18)
                dec1     = p.get("token1_decimals", 18)
                sqrt_p   = sqrt_price_x96 / (2 ** 96)
                price_adj = (sqrt_p ** 2) * (10 ** dec0) / (10 ** dec1)
                prices.append(ChainPoolPrice(
                    chain_id        = self.chain_id,
                    pool_address    = p["pair_address"],
                    dex_name        = p.get("dex_name", "unknown_v3"),
                    protocol        = p.get("protocol", "v3"),
                    token0_address  = p.get("token0_address", ""),
                    token1_address  = p.get("token1_address", ""),
                    token0_symbol   = p.get("token0_symbol", "T0"),
                    token1_symbol   = p.get("token1_symbol", "T1"),
                    token0_decimals = dec0,
                    token1_decimals = dec1,
                    price_t0_in_t1  = price_adj,
                    price_t1_in_t0  = 1 / price_adj if price_adj > 0 else 0,
                    liquidity_usd   = float(liquidity) if liquidity else -1.0,
                    fee_bps         = p.get("fee_bps", 30),
                ))

        # ── Curve / Balancer: use stored discovery balances ───
        for p in cb_pools:
            cp = self._fetch_curve_balancer_price(w3, p)
            if cp:
                prices.append(cp)

        self._pools = prices
        self._last_scan = time.time()
        logger.info(f"[Engine/{self.chain_name}] priced {len(prices)}/{len(pools)} pools "
                    f"(v2={len(v2_pools)}, v3={len(v3_pools)}, cb={len(cb_pools)})")
        return prices

    def detect_spreads(
        self,
        min_spread_bps: float = 20.0,
        min_liquidity_usd: float = 1_000.0,
        loan_amount_usd: float = 50_000.0,
    ) -> List[ChainSpreadOpportunity]:
        """
        Cross-DEX spread detection — same chain, same token pair, different DEX.
        Attaches a complete execution payload to every profitable opportunity.
        """
        if not self._pools:
            return []

        # Lazy import to avoid circular dependency at module load time
        try:
            from execution_payload_builder import get_payload_builder
            payload_builder = get_payload_builder()
        except Exception:
            payload_builder = None

        # Group by canonical token pair (sorted addresses)
        pair_groups: Dict[str, List[ChainPoolPrice]] = {}
        for pool in self._pools:
            t0, t1 = sorted([pool.token0_address.lower(), pool.token1_address.lower()])
            key = f"{t0}:{t1}"
            pair_groups.setdefault(key, []).append(pool)

        opps: List[ChainSpreadOpportunity] = []
        chain_name = self.chain_cfg["display"]

        MAX_SPREAD_BPS = 2000.0   # 20% hard cap — anything above is bad price data

        for pair_key, group in pair_groups.items():
            if len(group) < 2:
                continue

            # Filter: positive price AND meets minimum liquidity
            valid = [
                p for p in group
                if p.mid_price() > 0 and (
                    p.liquidity_usd >= min_liquidity_usd or p.liquidity_usd < 0
                )
            ]
            if len(valid) < 2:
                continue

            valid.sort(key=lambda x: x.mid_price())
            buy_pool  = valid[0]   # cheapest → buy here
            sell_pool = valid[-1]  # most expensive → sell here
            buy_price = buy_pool.mid_price()
            sell_price = sell_pool.mid_price()

            # Sanity: price ratio >50x is almost certainly bad oracle data
            if buy_price > 0 and sell_price / buy_price > 50:
                continue
            if buy_pool.liquidity_usd < 0 and sell_pool.liquidity_usd < 0:
                continue
            # Hard execution rule: must buy cheaper than we sell.
            if buy_price >= sell_price:
                continue

            spread = buy_pool.spread_bps(sell_pool)
            if spread < min_spread_bps or spread > MAX_SPREAD_BPS:
                continue

            fee_cost = buy_pool.fee_bps + sell_pool.fee_bps
            net_bps  = spread - fee_cost
            if net_bps <= 0:
                continue

            opp = ChainSpreadOpportunity(
                chain_id         = self.chain_id,
                chain_name       = chain_name,
                token0_symbol    = buy_pool.token0_symbol,
                token1_symbol    = buy_pool.token1_symbol,
                token0_address   = buy_pool.token0_address,
                token1_address   = buy_pool.token1_address,
                token0_decimals  = buy_pool.token0_decimals,
                token1_decimals  = buy_pool.token1_decimals,
                buy_pool         = buy_pool.pool_address,
                sell_pool        = sell_pool.pool_address,
                buy_dex          = buy_pool.dex_name,
                sell_dex         = sell_pool.dex_name,
                buy_protocol     = buy_pool.protocol,
                sell_protocol    = sell_pool.protocol,
                buy_pool_meta    = {
                    "pool_id": buy_pool.pool_id,
                    "tokens": buy_pool.tokens,
                    "fee_bps": buy_pool.fee_bps,
                },
                sell_pool_meta   = {
                    "pool_id": sell_pool.pool_id,
                    "tokens": sell_pool.tokens,
                    "fee_bps": sell_pool.fee_bps,
                },
                spread_bps       = spread,
                buy_price        = buy_price,
                sell_price       = sell_price,
                buy_pool_tokenA_price_usd = buy_price,
                sell_pool_tokenA_price_usd = sell_price,
                buy_pool_token_prices = {
                    buy_pool.token0_symbol: buy_price,
                    buy_pool.token1_symbol: buy_pool.price_t1_in_t0,
                },
                sell_pool_token_prices = {
                    sell_pool.token0_symbol: sell_price,
                    sell_pool.token1_symbol: sell_pool.price_t1_in_t0,
                },
                estimated_profit_pct = net_bps / 100,
                liquidity_usd    = min(
                    [v for v in [buy_pool.liquidity_usd, sell_pool.liquidity_usd] if v > 0] or [0.0]
                ),
                buy_pool_liquidity_usd = buy_pool.liquidity_usd if buy_pool.liquidity_usd > 0 else 0.0,
                sell_pool_liquidity_usd = sell_pool.liquidity_usd if sell_pool.liquidity_usd > 0 else 0.0,
            )

            # ── Build execution payload inline ────────────────
            if payload_builder:
                try:
                    opp.execution_payload = payload_builder.build(
                        opp.to_dict(), loan_amount_usd=loan_amount_usd
                    )
                    if opp.execution_payload:
                        opp.execution_payload = opp.execution_payload.to_dict() \
                            if hasattr(opp.execution_payload, "to_dict") \
                            else opp.execution_payload
                except Exception as pe:
                    logger.debug(f"[Engine/{self.chain_name}] payload build skip: {pe}")

            opps.append(opp)

        opps.sort(key=lambda x: -x.spread_bps)
        self._spreads = opps
        executable = sum(1 for o in opps if (o.execution_payload or {}).get("executable", False))
        logger.info(
            f"[Engine/{self.chain_name}] {len(opps)} spread opportunities "
            f"({executable} executable, min {min_spread_bps} bps, cross-DEX only)"
        )
        return opps

    def scan(
        self,
        max_pools: int = 500,
        min_spread_bps: float = 20.0,
        min_liquidity_usd: float = 1_000.0,
    ) -> Tuple[List[ChainPoolPrice], List[ChainSpreadOpportunity]]:
        prices = self.fetch_all_prices(max_pools)
        spreads = self.detect_spreads(min_spread_bps, min_liquidity_usd)
        return prices, spreads

    def get_status(self) -> Dict:
        executable = sum(
            1 for s in self._spreads
            if (s.execution_payload or {}).get("executable", False)
               or s.spread_bps >= 20.0
        )
        # Real pool-type breakdown from priced pool objects
        v3_protocols = {"v3", "uniswap_v3", "algebra", "pancake_v3", "traderjoe_v3"}
        v2_count = v3_count = curve_count = balancer_count = 0
        for p in self._pools:
            proto = p.protocol.lower()
            if "curve" in proto:
                curve_count += 1
            elif "balancer" in proto:
                balancer_count += 1
            elif proto in v3_protocols:
                v3_count += 1
            else:
                v2_count += 1
        return {
            "chain_id":         self.chain_id,
            "chain_name":       self.chain_name,
            "pool_count":       len(self._pools),
            "spread_count":     len(self._spreads),
            "executable_count": executable,
            "v2_count":         v2_count,
            "v3_count":         v3_count,
            "curve_count":      curve_count,
            "balancer_count":   balancer_count,
            "last_scan":        datetime.fromtimestamp(self._last_scan, tz=timezone.utc).isoformat()
                                if self._last_scan else None,
        }


# ─────────────────────────────────────────────────────────────
#  Multi-chain orchestrator
# ─────────────────────────────────────────────────────────────

class MultiChainArbitrageEngine:
    """
    Manages one ChainPriceEngine per chain.
    Each chain is fully isolated — no cross-chain arbitrage.
    """

    def __init__(self, chain_ids: Optional[List[int]] = None):
        self.chain_ids = chain_ids or ENABLED_CHAINS
        self.engines: Dict[int, ChainPriceEngine] = {
            cid: ChainPriceEngine(cid) for cid in self.chain_ids
        }

    def scan_chain(
        self,
        chain_id: int,
        max_pools: int = 500,
        min_spread_bps: float = 20.0,
    ) -> Tuple[List[ChainPoolPrice], List[ChainSpreadOpportunity]]:
        return self.engines[chain_id].scan(max_pools=max_pools, min_spread_bps=min_spread_bps)

    async def scan_all_chains_async(
        self,
        max_pools: int = 500,
        min_spread_bps: float = 20.0,
    ) -> Dict[int, Dict]:
        """Run all chain scans concurrently."""
        loop = asyncio.get_event_loop()
        results: Dict[int, Dict] = {}

        async def _run(cid: int):
            try:
                engine = self.engines[cid]
                prices, spreads = await loop.run_in_executor(
                    None, lambda: engine.scan(max_pools, min_spread_bps)
                )
                results[cid] = {
                    "chain_id":    cid,
                    "chain_name":  CHAINS[cid]["display"],
                    "pool_count":  len(prices),
                    "spreads":     [s.to_dict() for s in spreads],
                    "spread_count": len(spreads),
                }
            except Exception as e:
                logger.error(f"[MultiChainEngine] chain {cid} error: {e}")
                results[cid] = {"chain_id": cid, "error": str(e)}

        await asyncio.gather(*[_run(cid) for cid in self.chain_ids])
        return results

    def all_spreads(self) -> List[Dict]:
        """Aggregate spreads from all chains, tagged by chain."""
        all_: List[Dict] = []
        for cid, engine in self.engines.items():
            for s in engine._spreads:
                all_.append(s.to_dict())
        all_.sort(key=lambda x: -x.get("spread_bps", 0))
        return all_

    def status(self) -> Dict[int, Dict]:
        return {cid: eng.get_status() for cid, eng in self.engines.items()}

    def get_engine(self, chain_id: int) -> ChainPriceEngine:
        return self.engines[chain_id]


# ── Singleton ────────────────────────────────────────────────

_engine: Optional[MultiChainArbitrageEngine] = None


def get_multi_chain_engine(chain_ids: Optional[List[int]] = None) -> MultiChainArbitrageEngine:
    global _engine
    if _engine is None:
        _engine = MultiChainArbitrageEngine(chain_ids)
    return _engine


async def periodic_multi_chain_scan(
    interval_seconds: int = 60,
    max_pools: int = 300,
    min_spread_bps: float = 20.0,
):
    """
    Background task: scan all 10 chains concurrently on a fixed interval.
    After each scan, broadcast results to the ws_hub "mc_spreads" channel
    so connected clients receive updates in real time without polling.
    """
    from ws_hub import hub  # local import to avoid circular at module load

    engine = get_multi_chain_engine()
    scan_num = 0
    while True:
        try:
            scan_num += 1
            logger.info(f"[MultiChainEngine] ⚡ scan #{scan_num} starting…")
            t0 = time.time()

            results = await engine.scan_all_chains_async(
                max_pools=max_pools, min_spread_bps=min_spread_bps
            )
            elapsed = time.time() - t0

            # ── Aggregate all executable spreads ──────────────
            all_spreads = engine.all_spreads()
            executable  = [s for s in all_spreads if (s.get("execution_payload") or {}).get("executable", False)]
            top_spreads = sorted(all_spreads, key=lambda x: -x.get("spread_bps", 0))[:50]

            # ── Broadcast to WebSocket clients (fire-and-forget)
            if hub.channel_size("mc_spreads") > 0:
                await hub.broadcast("mc_spreads", {
                    "type":            "mc_spreads",
                    "scan_num":        scan_num,
                    "scan_elapsed_s":  round(elapsed, 2),
                    "total_spreads":   len(all_spreads),
                    "executable":      len(executable),
                    "chains_scanned":  list(results.keys()),
                    "spreads":         top_spreads,
                    "timestamp":       int(time.time() * 1000),
                    "note":            "Single-chain cross-DEX only. No cross-chain arbitrage.",
                })

            # ── Broadcast per-chain summaries ─────────────────
            for cid, res in results.items():
                ch = f"mc_chain_{cid}"
                if hub.channel_size(ch) > 0:
                    await hub.broadcast(ch, {
                        "type":       "chain_scan",
                        "chain_id":   cid,
                        "chain_name": res.get("chain_name", ""),
                        "pool_count": res.get("pool_count", 0),
                        "spreads":    res.get("spreads", []),
                        "timestamp":  int(time.time() * 1000),
                    })

            logger.info(
                f"[MultiChainEngine] ✅ scan #{scan_num} done in {elapsed:.1f}s | "
                f"spreads={len(all_spreads)} executable={len(executable)}"
            )
        except Exception as e:
            logger.error(f"[MultiChainEngine] periodic scan error: {e}", exc_info=True)
        await asyncio.sleep(interval_seconds)
