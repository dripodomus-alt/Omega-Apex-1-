"""
Curve + Balancer Pool Discovery
Discovers AMM pools from Curve Finance registries and Balancer Vault
across all 10 supported chains.

Strict rule: single-chain only — no cross-chain routing.
"""

import logging
import time
from typing import Dict, List, Optional, Tuple
from web3 import Web3

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
#  ABI FRAGMENTS
# ─────────────────────────────────────────────────────────────

CURVE_ADDRESS_PROVIDER_ABI = [
    {"name": "get_registry", "outputs": [{"type": "address"}], "inputs": [], "stateMutability": "view", "type": "function"},
    {"name": "get_address",  "outputs": [{"type": "address"}], "inputs": [{"name": "id", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"name": "max_id",       "outputs": [{"type": "uint256"}], "inputs": [], "stateMutability": "view", "type": "function"},
]

CURVE_REGISTRY_ABI = [
    {"name": "pool_count",        "outputs": [{"type": "uint256"}], "inputs": [], "stateMutability": "view", "type": "function"},
    {"name": "pool_list",         "outputs": [{"type": "address"}], "inputs": [{"name": "i", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"name": "get_n_coins",       "outputs": [{"name": "", "type": "uint256[2]"}], "inputs": [{"name": "pool", "type": "address"}], "stateMutability": "view", "type": "function"},
    {"name": "get_coins",         "outputs": [{"type": "address[8]"}], "inputs": [{"name": "pool", "type": "address"}], "stateMutability": "view", "type": "function"},
    {"name": "get_decimals",      "outputs": [{"type": "uint256[8]"}], "inputs": [{"name": "pool", "type": "address"}], "stateMutability": "view", "type": "function"},
    {"name": "get_balances",      "outputs": [{"type": "uint256[8]"}], "inputs": [{"name": "pool", "type": "address"}], "stateMutability": "view", "type": "function"},
    {"name": "get_pool_name",     "outputs": [{"type": "string"}], "inputs": [{"name": "pool", "type": "address"}], "stateMutability": "view", "type": "function"},
    {"name": "get_virtual_price_from_lp_token", "outputs": [{"type": "uint256"}], "inputs": [{"name": "_token", "type": "address"}], "stateMutability": "view", "type": "function"},
]

CURVE_FACTORY_ABI = [
    {"name": "pool_count",   "outputs": [{"type": "uint256"}], "inputs": [], "stateMutability": "view", "type": "function"},
    {"name": "pool_list",    "outputs": [{"type": "address"}], "inputs": [{"name": "i", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"name": "get_n_coins",  "outputs": [{"type": "uint256"}], "inputs": [{"name": "pool", "type": "address"}], "stateMutability": "view", "type": "function"},
    {"name": "get_coins",    "outputs": [{"type": "address[4]"}], "inputs": [{"name": "pool", "type": "address"}], "stateMutability": "view", "type": "function"},
    {"name": "get_decimals", "outputs": [{"type": "uint256[4]"}], "inputs": [{"name": "pool", "type": "address"}], "stateMutability": "view", "type": "function"},
    {"name": "get_balances", "outputs": [{"type": "uint256[4]"}], "inputs": [{"name": "pool", "type": "address"}], "stateMutability": "view", "type": "function"},
]

BALANCER_VAULT_ABI = [
    {
        "name": "getPoolTokens",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "poolId", "type": "bytes32"}],
        "outputs": [
            {"name": "tokens",   "type": "address[]"},
            {"name": "balances", "type": "uint256[]"},
            {"name": "lastChangeBlock", "type": "uint256"},
        ],
    },
]

BALANCER_POOL_ABI = [
    {"name": "getPoolId",     "outputs": [{"type": "bytes32"}], "inputs": [], "stateMutability": "view", "type": "function"},
    {"name": "getSwapFeePercentage", "outputs": [{"type": "uint256"}], "inputs": [], "stateMutability": "view", "type": "function"},
    {"name": "name",          "outputs": [{"type": "string"}],  "inputs": [], "stateMutability": "view", "type": "function"},
]

# PoolRegistered(bytes32,address,uint8)
BALANCER_POOL_REGISTERED_TOPIC = "0x3c13bc30b8e878c53fd2a36b679409c073afd75950be43d8858768e956fbc20e"

NULL_ADDRESS = "0x0000000000000000000000000000000000000000"
BATCH_SIZE = 50          # pool_list calls per batch
MAX_CURVE_POOLS = 500    # upper safety cap per registry
MAX_BAL_POOLS   = 300    # upper cap for Balancer log scan


# ─────────────────────────────────────────────────────────────
#  CURVE DISCOVERY
# ─────────────────────────────────────────────────────────────

class CurveDiscovery:
    """
    Discovers Curve Finance pools on a single chain via:
      - The Curve AddressProvider (registry id=0 → main registry)
      - The Curve factory (plain pools, meta pools)
      - Direct meta-registry if available
    """

    def __init__(self, w3: Web3, chain_cfg: Dict):
        self.w3 = w3
        self.chain_cfg = chain_cfg
        self.chain_id = chain_cfg["chain_id"]
        self.chain_name = chain_cfg["display"]
        self.curve_cfg = chain_cfg.get("curve", {})

    # ── internal helpers ──────────────────────────────────────

    def _get_registry_from_provider(self, provider_addr: str) -> Optional[str]:
        try:
            provider = self.w3.eth.contract(
                address=Web3.to_checksum_address(provider_addr),
                abi=CURVE_ADDRESS_PROVIDER_ABI,
            )
            registry = provider.functions.get_registry().call()
            if registry and registry != NULL_ADDRESS:
                return registry
        except Exception as e:
            logger.debug(f"[Curve/{self.chain_name}] provider.get_registry: {e}")
        return None

    def _scan_registry(self, registry_addr: str, source_tag: str) -> List[Dict]:
        pools = []
        try:
            reg = self.w3.eth.contract(
                address=Web3.to_checksum_address(registry_addr),
                abi=CURVE_REGISTRY_ABI,
            )
            pool_count = reg.functions.pool_count().call()
            pool_count = min(pool_count, MAX_CURVE_POOLS)
            logger.info(f"[Curve/{self.chain_name}] {source_tag}: {pool_count} pools found")

            for i in range(pool_count):
                try:
                    pool_addr = reg.functions.pool_list(i).call()
                    if not pool_addr or pool_addr == NULL_ADDRESS:
                        continue

                    coins_raw  = reg.functions.get_coins(pool_addr).call()
                    decs_raw   = reg.functions.get_decimals(pool_addr).call()
                    bals_raw   = reg.functions.get_balances(pool_addr).call()

                    coins = [c for c in coins_raw if c and c != NULL_ADDRESS]
                    decs  = decs_raw[:len(coins)]
                    bals  = bals_raw[:len(coins)]

                    if len(coins) < 2:
                        continue

                    try:
                        name = reg.functions.get_pool_name(pool_addr).call()
                    except Exception:
                        name = f"curve-{pool_addr[:8]}"

                    pools.append(self._build_pool(pool_addr, coins, decs, bals, "curve_stable", name, source_tag))

                except Exception as e:
                    logger.debug(f"[Curve/{self.chain_name}] pool_list[{i}] error: {e}")

        except Exception as e:
            logger.warning(f"[Curve/{self.chain_name}] registry scan ({source_tag}) failed: {e}")
        return pools

    def _scan_factory(self, factory_addr: str, source_tag: str) -> List[Dict]:
        pools = []
        try:
            fac = self.w3.eth.contract(
                address=Web3.to_checksum_address(factory_addr),
                abi=CURVE_FACTORY_ABI,
            )
            pool_count = fac.functions.pool_count().call()
            pool_count = min(pool_count, MAX_CURVE_POOLS)
            logger.info(f"[Curve/{self.chain_name}] {source_tag}: {pool_count} factory pools")

            for i in range(pool_count):
                try:
                    pool_addr = fac.functions.pool_list(i).call()
                    if not pool_addr or pool_addr == NULL_ADDRESS:
                        continue

                    coins_raw = fac.functions.get_coins(pool_addr).call()
                    decs_raw  = fac.functions.get_decimals(pool_addr).call()
                    bals_raw  = fac.functions.get_balances(pool_addr).call()

                    coins = [c for c in coins_raw if c and c != NULL_ADDRESS]
                    decs  = decs_raw[:len(coins)]
                    bals  = bals_raw[:len(coins)]

                    if len(coins) < 2:
                        continue

                    pools.append(self._build_pool(pool_addr, coins, decs, bals, "curve_factory", f"factory-{i}", source_tag))

                except Exception as e:
                    logger.debug(f"[Curve/{self.chain_name}] factory_list[{i}] error: {e}")

        except Exception as e:
            logger.warning(f"[Curve/{self.chain_name}] factory scan ({source_tag}) failed: {e}")
        return pools

    def _build_pool(
        self,
        pool_addr: str,
        coins: List[str],
        decimals: List,
        balances: List,
        dex_name: str,
        name: str,
        source: str,
    ) -> Dict:
        return {
            "pair_address":   Web3.to_checksum_address(pool_addr),
            "dex_name":       dex_name,
            "protocol":       "curve_stable",
            "pool_name":      name,
            "source":         source,
            "chain_id":       self.chain_id,
            "n_coins":        len(coins),
            "tokens":         [Web3.to_checksum_address(c) for c in coins],
            "decimals":       [int(d) for d in decimals],
            "balances":       [int(b) for b in balances],
            # Curve pools always have 2+ tokens — expose first pair for compatibility
            "token0_address": Web3.to_checksum_address(coins[0]),
            "token1_address": Web3.to_checksum_address(coins[1]),
            "token0_decimals": int(decimals[0]),
            "token1_decimals": int(decimals[1]),
            "fee_bps":        4,   # typical Curve 0.04 %
        }

    # ── public API ────────────────────────────────────────────

    def discover_pools(self) -> List[Dict]:
        if not self.curve_cfg.get("enabled", False):
            logger.info(f"[Curve/{self.chain_name}] disabled — skipping")
            return []

        t0 = time.time()
        all_pools: Dict[str, Dict] = {}

        # 1) main registry via address provider
        provider_addr = self.curve_cfg.get("address_provider")
        if provider_addr:
            registry_addr = self._get_registry_from_provider(provider_addr)
            if registry_addr:
                for pool in self._scan_registry(registry_addr, "main_registry"):
                    all_pools[pool["pair_address"].lower()] = pool
            # also try id=3 (meta-pool registry) and id=6 (crypto factory)
            try:
                provider = self.w3.eth.contract(
                    address=Web3.to_checksum_address(provider_addr),
                    abi=CURVE_ADDRESS_PROVIDER_ABI,
                )
                for reg_id in [3, 5, 6, 7]:
                    try:
                        extra_reg = provider.functions.get_address(reg_id).call()
                        if extra_reg and extra_reg != NULL_ADDRESS and extra_reg.lower() not in [p.lower() for p in [registry_addr or ""]]:
                            for pool in self._scan_registry(extra_reg, f"registry_id_{reg_id}"):
                                all_pools.setdefault(pool["pair_address"].lower(), pool)
                    except Exception:
                        pass
            except Exception:
                pass

        # 2) meta-registry (Ethereum / Polygon)
        meta_reg = self.curve_cfg.get("meta_registry")
        if meta_reg:
            for pool in self._scan_registry(meta_reg, "meta_registry"):
                all_pools.setdefault(pool["pair_address"].lower(), pool)

        # 3) plain factory
        factory = self.curve_cfg.get("factory_v2")
        if factory:
            for pool in self._scan_factory(factory, "factory_v2"):
                all_pools.setdefault(pool["pair_address"].lower(), pool)

        result = list(all_pools.values())
        logger.info(
            f"[Curve/{self.chain_name}] ✅ {len(result)} unique pools in {time.time()-t0:.1f}s"
        )
        return result


# ─────────────────────────────────────────────────────────────
#  BALANCER DISCOVERY
# ─────────────────────────────────────────────────────────────

class BalancerDiscovery:
    """
    Discovers Balancer V2 pools on a single chain.

    Strategy:
      1. Scan PoolRegistered events from the Vault (last N blocks or
         from genesis if fast enough)
      2. For each pool address → call getPoolId → call Vault.getPoolTokens
    """

    GENESIS_BLOCKS: Dict[int, int] = {
        1:     12272146,   # Ethereum Balancer V2 deploy block
        56:    22527457,   # BNB
        137:   15832991,   # Polygon
        42161: 118959,     # Arbitrum
        10:    29_000_000, # Optimism
        8453:  6_000_000,  # Base
        43114: 20_000_000, # Avalanche
        250:   16_896_080, # Fantom (BeethovenX)
        324:   0,          # zkSync (custom vault)
        59144: 0,          # Linea
    }

    # How many blocks to look back for events (0 = from genesis)
    LOOKBACK_BLOCKS: Dict[int, int] = {
        1:     2_000_000,
        56:    5_000_000,
        137:   5_000_000,
        42161: 10_000_000,
        10:    5_000_000,
        8453:  3_000_000,
        43114: 5_000_000,
        250:   5_000_000,
        324:   2_000_000,
        59144: 1_000_000,
    }

    def __init__(self, w3: Web3, chain_cfg: Dict):
        self.w3 = w3
        self.chain_cfg = chain_cfg
        self.chain_id = chain_cfg["chain_id"]
        self.chain_name = chain_cfg["display"]
        self.bal_cfg = chain_cfg.get("balancer", {})
        self._vault = None

    def _get_vault(self):
        if self._vault is None:
            vault_addr = self.bal_cfg.get("vault")
            if not vault_addr:
                return None
            self._vault = self.w3.eth.contract(
                address=Web3.to_checksum_address(vault_addr),
                abi=BALANCER_VAULT_ABI,
            )
        return self._vault

    def _fetch_pool_tokens(self, pool_id: str) -> Optional[Tuple[List[str], List[int]]]:
        vault = self._get_vault()
        if not vault:
            return None
        try:
            pool_id_bytes = bytes.fromhex(pool_id.replace("0x", ""))
            tokens, balances, _ = vault.functions.getPoolTokens(pool_id_bytes).call()
            return list(tokens), [int(b) for b in balances]
        except Exception as e:
            logger.debug(f"[Balancer/{self.chain_name}] getPoolTokens({pool_id[:10]}…): {e}")
            return None

    def _get_pool_id(self, pool_addr: str) -> Optional[str]:
        try:
            pool_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(pool_addr),
                abi=BALANCER_POOL_ABI,
            )
            pool_id_bytes = pool_contract.functions.getPoolId().call()
            return "0x" + pool_id_bytes.hex()
        except Exception as e:
            logger.debug(f"[Balancer/{self.chain_name}] getPoolId({pool_addr[:10]}…): {e}")
            return None

    def _get_fee(self, pool_addr: str) -> int:
        try:
            pool_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(pool_addr),
                abi=BALANCER_POOL_ABI,
            )
            fee_pct = pool_contract.functions.getSwapFeePercentage().call()
            # fee_pct is in 1e18 units (e.g. 1e15 = 0.1%)
            return max(1, int(fee_pct // 1e14))  # → bps
        except Exception:
            return 30  # default 0.3%

    def _scan_logs(self) -> List[str]:
        """Return list of unique pool addresses from PoolRegistered events."""
        try:
            latest = self.w3.eth.block_number
            lookback = self.LOOKBACK_BLOCKS.get(self.chain_id, 2_000_000)
            genesis  = self.GENESIS_BLOCKS.get(self.chain_id, 0)
            from_block = max(genesis, latest - lookback)

            vault_addr = self.bal_cfg.get("vault", "")
            if not vault_addr:
                return []

            CHUNK = 10_000
            pool_addresses: List[str] = []
            seen: set = set()

            logger.info(
                f"[Balancer/{self.chain_name}] scanning logs "
                f"from {from_block} to {latest} ({latest-from_block:,} blocks)"
            )

            current = from_block
            while current <= latest:
                end = min(current + CHUNK - 1, latest)
                try:
                    logs = self.w3.eth.get_logs({
                        "fromBlock": current,
                        "toBlock":   end,
                        "address":   Web3.to_checksum_address(vault_addr),
                        "topics":    [BALANCER_POOL_REGISTERED_TOPIC],
                    })
                    for log in logs:
                        if len(log["topics"]) >= 2:
                            # topic[1] = poolId (bytes32), first 20 bytes = pool address
                            pool_id_bytes = log["topics"][1]
                            pool_addr = "0x" + pool_id_bytes.hex()[24:64]
                            if pool_addr.lower() not in seen:
                                seen.add(pool_addr.lower())
                                pool_addresses.append(Web3.to_checksum_address(pool_addr))
                                if len(pool_addresses) >= MAX_BAL_POOLS:
                                    return pool_addresses
                except Exception as e:
                    logger.debug(f"[Balancer/{self.chain_name}] log chunk {current}-{end}: {e}")
                current = end + 1

            logger.info(f"[Balancer/{self.chain_name}] log scan: {len(pool_addresses)} pools")
            return pool_addresses

        except Exception as e:
            logger.warning(f"[Balancer/{self.chain_name}] log scan failed: {e}")
            return []

    def _build_pool(self, pool_addr: str, pool_id: str, tokens: List[str], balances: List[int], fee_bps: int) -> Dict:
        return {
            "pair_address":   Web3.to_checksum_address(pool_addr),
            "pool_id":        pool_id,
            "dex_name":       "balancer_weighted",
            "protocol":       "balancer_v2",
            "source":         "balancer_vault",
            "chain_id":       self.chain_id,
            "n_coins":        len(tokens),
            "tokens":         [Web3.to_checksum_address(t) for t in tokens],
            "balances":       balances,
            "token0_address": Web3.to_checksum_address(tokens[0]) if tokens else NULL_ADDRESS,
            "token1_address": Web3.to_checksum_address(tokens[1]) if len(tokens) > 1 else NULL_ADDRESS,
            "token0_decimals": 18,
            "token1_decimals": 18,
            "fee_bps":        fee_bps,
        }

    def discover_pools(self) -> List[Dict]:
        if not self.bal_cfg.get("enabled", False):
            logger.info(f"[Balancer/{self.chain_name}] disabled — skipping")
            return []

        t0 = time.time()
        pool_addresses = self._scan_logs()

        if not pool_addresses:
            logger.warning(f"[Balancer/{self.chain_name}] no pools found via logs")
            return []

        result = []
        for pool_addr in pool_addresses:
            try:
                pool_id = self._get_pool_id(pool_addr)
                if not pool_id:
                    continue
                token_data = self._fetch_pool_tokens(pool_id)
                if not token_data or len(token_data[0]) < 2:
                    continue
                tokens, balances = token_data
                fee_bps = self._get_fee(pool_addr)
                result.append(self._build_pool(pool_addr, pool_id, tokens, balances, fee_bps))
            except Exception as e:
                logger.debug(f"[Balancer/{self.chain_name}] pool {pool_addr[:10]}: {e}")

        logger.info(
            f"[Balancer/{self.chain_name}] ✅ {len(result)} pools resolved in {time.time()-t0:.1f}s"
        )
        return result


# ─────────────────────────────────────────────────────────────
#  UNIFIED ENTRY POINT
# ─────────────────────────────────────────────────────────────

class CurveBalancerDiscovery:
    """
    Runs Curve + Balancer discovery for a single chain.
    Returns combined pool list, deduped by pool address.
    """

    def __init__(self, w3: Web3, chain_cfg: Dict):
        self.curve   = CurveDiscovery(w3, chain_cfg)
        self.balancer = BalancerDiscovery(w3, chain_cfg)
        self.chain_name = chain_cfg["display"]

    def discover_all(self) -> List[Dict]:
        t0 = time.time()
        seen: Dict[str, Dict] = {}

        curve_pools   = self.curve.discover_pools()
        balancer_pools = self.balancer.discover_pools()

        for pool in curve_pools + balancer_pools:
            key = pool["pair_address"].lower()
            seen.setdefault(key, pool)

        result = list(seen.values())
        logger.info(
            f"[CurveBalancer/{self.chain_name}] "
            f"✅ Total: {len(result)} pools "
            f"(Curve: {len(curve_pools)}, Balancer: {len(balancer_pools)}) "
            f"in {time.time()-t0:.1f}s"
        )
        return result


# ─────────────────────────────────────────────────────────────
#  Per-chain singleton cache
# ─────────────────────────────────────────────────────────────

_instances: Dict[int, CurveBalancerDiscovery] = {}


def get_curve_balancer_discovery(w3: Web3, chain_cfg: Dict) -> CurveBalancerDiscovery:
    chain_id = chain_cfg["chain_id"]
    if chain_id not in _instances:
        _instances[chain_id] = CurveBalancerDiscovery(w3, chain_cfg)
    return _instances[chain_id]
