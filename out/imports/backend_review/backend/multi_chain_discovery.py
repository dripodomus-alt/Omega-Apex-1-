"""
Multi-Chain Pool Discovery
Orchestrates V2/V3 factory scanning + Curve + Balancer discovery
for every configured chain in isolation.

Rules enforced:
  • Each chain runs its own isolated discovery pass
  • No cross-chain pool merging
  • Results keyed by chain_id
"""

import logging
import time
from typing import Dict, List, Optional
from itertools import combinations

from web3 import Web3
from web3.providers import HTTPProvider

from chain_config import CHAINS, get_chain, get_chain_token_info, get_rpc_url, ENABLED_CHAINS
from curve_balancer_discovery import get_curve_balancer_discovery

logger = logging.getLogger(__name__)

NULL_ADDRESS = "0x0000000000000000000000000000000000000000"

# ─── ABI fragments ──────────────────────────────────────────

V2_FACTORY_ABI = [
    {"name": "getPair",        "outputs": [{"type": "address"}], "inputs": [{"name": "", "type": "address"}, {"name": "", "type": "address"}], "stateMutability": "view", "type": "function"},
    {"name": "allPairs",       "outputs": [{"type": "address"}], "inputs": [{"name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"name": "allPairsLength", "outputs": [{"type": "uint256"}], "inputs": [], "stateMutability": "view", "type": "function"},
]

V3_FACTORY_ABI = [
    {"name": "getPool", "outputs": [{"type": "address"}], "inputs": [{"name": "", "type": "address"}, {"name": "", "type": "address"}, {"name": "", "type": "uint24"}], "stateMutability": "view", "type": "function"},
]


# ─── Per-chain scanner ──────────────────────────────────────

class ChainPoolScanner:
    """
    Discovers all DEX pools on a single EVM chain:
      - UniswapV2-style factories  (getPair)
      - UniswapV3-style factories  (getPool × fee tiers)
      - Curve Finance pools        (via CurveDiscovery)
      - Balancer V2 pools          (via BalancerDiscovery)

    No cross-chain logic exists here.
    """

    def __init__(self, chain_id: int, rpc_url: Optional[str] = None):
        self.chain_cfg = get_chain(chain_id)
        self.chain_id  = chain_id
        self.name      = self.chain_cfg["display"]

        url = rpc_url or get_rpc_url(chain_id)
        self.w3 = Web3(HTTPProvider(url, request_kwargs={"timeout": 15}))

        # Build token list from chain config
        tokens = self.chain_cfg["tokens"]
        self.token_list = [
            {"symbol": sym, "address": Web3.to_checksum_address(info["address"]), "decimals": info["decimals"]}
            for sym, info in tokens.items()
        ]
        self.token_addresses = [t["address"] for t in self.token_list]
        self.token_map       = {t["address"].lower(): t for t in self.token_list}

        logger.info(
            f"[Scanner/{self.name}] init | {len(self.token_list)} tokens | "
            f"rpc={url[:40]}…"
        )

    # ── helpers ──────────────────────────────────────────────

    def _token_info(self, address: str) -> Optional[Dict]:
        return self.token_map.get(address.lower())

    def _pool_base(self, pair_addr: str, dex_name: str, protocol: str, fee_bps: int,
                   t0_addr: str, t1_addr: str) -> Dict:
        t0 = self._token_info(t0_addr) or {"symbol": "?", "decimals": 18}
        t1 = self._token_info(t1_addr) or {"symbol": "?", "decimals": 18}
        return {
            "pair_address":    pair_addr,
            "chain_id":        self.chain_id,
            "dex_name":        dex_name,
            "protocol":        protocol,
            "token0_address":  t0_addr,
            "token1_address":  t1_addr,
            "token0_symbol":   t0["symbol"],
            "token1_symbol":   t1["symbol"],
            "token0_decimals": t0["decimals"],
            "token1_decimals": t1["decimals"],
            "fee_bps":         fee_bps,
        }

    # ── V2 factory scan ──────────────────────────────────────

    def _scan_v2(self, factory_addr: str, dex_key: str, dex_cfg: Dict) -> List[Dict]:
        dex_name = dex_key.replace("_", " ").title()
        fee_bps  = dex_cfg.get("fee_bps", 30)
        pools    = []
        pairs    = list(combinations(self.token_addresses, 2))

        try:
            factory = self.w3.eth.contract(
                address=Web3.to_checksum_address(factory_addr),
                abi=V2_FACTORY_ABI,
            )
        except Exception as e:
            logger.warning(f"[Scanner/{self.name}] {dex_name} V2 init failed: {e}")
            return pools

        logger.info(f"[Scanner/{self.name}] {dex_name} V2 — {len(pairs)} pairs")
        found = 0
        for t0, t1 in pairs:
            try:
                addr = factory.functions.getPair(t0, t1).call()
                if addr == NULL_ADDRESS:
                    continue
                pools.append(self._pool_base(
                    Web3.to_checksum_address(addr),
                    dex_name, "uniswap_v2", fee_bps, t0, t1,
                ))
                found += 1
            except Exception as e:
                logger.debug(f"[Scanner/{self.name}] getPair {t0[:8]}/{t1[:8]}: {e}")

        logger.info(f"[Scanner/{self.name}] {dex_name} V2 → {found} pools")
        return pools

    # ── V3 factory scan ──────────────────────────────────────

    def _scan_v3(self, factory_addr: str, dex_key: str, dex_cfg: Dict) -> List[Dict]:
        dex_name   = dex_key.replace("_", " ").title()
        fee_tiers  = dex_cfg.get("fee_tiers", [500, 3000, 10000])
        pools      = []
        pairs      = list(combinations(self.token_addresses, 2))

        try:
            factory = self.w3.eth.contract(
                address=Web3.to_checksum_address(factory_addr),
                abi=V3_FACTORY_ABI,
            )
        except Exception as e:
            logger.warning(f"[Scanner/{self.name}] {dex_name} V3 init failed: {e}")
            return pools

        logger.info(f"[Scanner/{self.name}] {dex_name} V3 — {len(pairs)} pairs × {len(fee_tiers)} fees")
        found = 0
        for t0, t1 in pairs:
            for fee in fee_tiers:
                try:
                    addr = factory.functions.getPool(t0, t1, fee).call()
                    if addr == NULL_ADDRESS:
                        continue
                    pools.append(self._pool_base(
                        Web3.to_checksum_address(addr),
                        dex_name, "uniswap_v3", fee // 100, t0, t1,
                    ))
                    found += 1
                except Exception as e:
                    logger.debug(f"[Scanner/{self.name}] getPool {t0[:8]}/{t1[:8]} fee={fee}: {e}")

        logger.info(f"[Scanner/{self.name}] {dex_name} V3 → {found} pools")
        return pools

    # ── public: full discovery ────────────────────────────────

    def discover_all_pools(self) -> List[Dict]:
        t0   = time.time()
        seen: Dict[str, Dict] = {}

        # 1) V2 + V3 factory scan
        for dex_key, dex_cfg in self.chain_cfg.get("dex_factories", {}).items():
            factory_addr = dex_cfg.get("address", "")
            if not factory_addr:
                continue
            ptype = dex_cfg.get("type", 2)
            try:
                if ptype == 2:
                    pools = self._scan_v2(factory_addr, dex_key, dex_cfg)
                elif ptype == 3:
                    pools = self._scan_v3(factory_addr, dex_key, dex_cfg)
                else:
                    logger.debug(f"[Scanner/{self.name}] {dex_key}: unknown type {ptype}")
                    pools = []
                for p in pools:
                    seen.setdefault(p["pair_address"].lower(), p)
            except Exception as e:
                logger.error(f"[Scanner/{self.name}] {dex_key} error: {e}")

        standard_count = len(seen)
        logger.info(f"[Scanner/{self.name}] Standard DEX pools: {standard_count}")

        # 2) Curve + Balancer
        try:
            cb_disc = get_curve_balancer_discovery(self.w3, self.chain_cfg)
            cb_pools = cb_disc.discover_all()
            for p in cb_pools:
                seen.setdefault(p["pair_address"].lower(), p)
            logger.info(
                f"[Scanner/{self.name}] Curve+Balancer added "
                f"{len(seen) - standard_count} pools"
            )
        except Exception as e:
            logger.error(f"[Scanner/{self.name}] Curve/Balancer error: {e}")

        result = list(seen.values())
        logger.info(
            f"[Scanner/{self.name}] ✅ TOTAL: {len(result)} unique pools "
            f"in {time.time()-t0:.1f}s"
        )
        return result


# ─── Multi-chain orchestrator ────────────────────────────────

class MultiChainDiscovery:
    """
    Runs ChainPoolScanner for all enabled chains sequentially (or
    returns cached results).  Results are never mixed across chains.
    """

    def __init__(self, chain_ids: Optional[List[int]] = None):
        self.chain_ids = chain_ids or ENABLED_CHAINS
        self._cache:   Dict[int, List[Dict]] = {}
        self._scanners: Dict[int, ChainPoolScanner] = {}

    def get_scanner(self, chain_id: int) -> ChainPoolScanner:
        if chain_id not in self._scanners:
            self._scanners[chain_id] = ChainPoolScanner(chain_id)
        return self._scanners[chain_id]

    def discover_chain(self, chain_id: int, force: bool = False) -> List[Dict]:
        """Full pool discovery for a single chain."""
        if not force and chain_id in self._cache:
            return self._cache[chain_id]
        scanner = self.get_scanner(chain_id)
        pools = scanner.discover_all_pools()
        self._cache[chain_id] = pools
        return pools

    def discover_all_chains(self, force: bool = False) -> Dict[int, List[Dict]]:
        """Run discovery on every enabled chain. Returns {chain_id: [pools]}."""
        results: Dict[int, List[Dict]] = {}
        for chain_id in self.chain_ids:
            try:
                results[chain_id] = self.discover_chain(chain_id, force=force)
            except Exception as e:
                logger.error(f"[MultiChain] chain {chain_id} failed: {e}")
                results[chain_id] = []
        return results

    def get_cached(self, chain_id: int) -> List[Dict]:
        return self._cache.get(chain_id, [])

    def summary(self) -> Dict[int, int]:
        return {cid: len(pools) for cid, pools in self._cache.items()}


# ── Singleton ────────────────────────────────────────────────

_mcd: Optional[MultiChainDiscovery] = None


def get_multi_chain_discovery(chain_ids: Optional[List[int]] = None) -> MultiChainDiscovery:
    global _mcd
    if _mcd is None:
        _mcd = MultiChainDiscovery(chain_ids)
    return _mcd
