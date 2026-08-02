"""
Execution Payload Builder
Builds complete, ready-to-broadcast transaction payloads for every
spread opportunity found across all 10 chains.

Each payload contains:
  - flash_loan  : provider address + ABI-encoded calldata
  - swap_leg_1  : buy leg (buy_pool → token out)
  - swap_leg_2  : sell leg (sell_pool → profit in)
  - net_profit  : fee-adjusted profit estimate in USD
  - gas_budget  : gas limit + priority fee suggestion

Strict rule: payloads are ALWAYS single-chain. No cross-chain paths.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple

from web3 import Web3

try:
    from .protocol_adapters import POLYGON_EXECUTOR_ADDRESS, SwapEncodingContext, encode_swap
except ImportError:  # Support direct script execution from backend/.
    from protocol_adapters import POLYGON_EXECUTOR_ADDRESS, SwapEncodingContext, encode_swap

logger = logging.getLogger(__name__)
EXECUTOR_CONTRACT_ADDRESS = POLYGON_EXECUTOR_ADDRESS

# ─────────────────────────────────────────────────────────────
#  Per-chain contract addresses
# ─────────────────────────────────────────────────────────────

# Aave V3 Pool (flashLoan) — per chain
AAVE_V3_POOL: Dict[int, str] = {
    1:      "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",  # Ethereum
    56:     "0x6807dc923806fE8Fd134338EABCA509979a7e0cB",  # BNB (Aave BNB market)
    137:    "0x794a61358D6845594F94dc1DB02A252b5b4814aD",  # Polygon
    42161:  "0x794a61358D6845594F94dc1DB02A252b5b4814aD",  # Arbitrum
    10:     "0x794a61358D6845594F94dc1DB02A252b5b4814aD",  # Optimism
    8453:   "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5",  # Base
    43114:  "0x794a61358D6845594F94dc1DB02A252b5b4814aD",  # Avalanche
    250:    None,                                          # Fantom — Aave not deployed
    324:    None,                                          # zkSync — Aave not deployed
    59144:  None,                                          # Linea — Aave not deployed
}

# Balancer Vault (flashLoan — 0% fee) — per chain
BALANCER_VAULT: Dict[int, str] = {
    1:      "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
    56:     "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
    137:    "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
    42161:  "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
    10:     "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
    8453:   "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
    43114:  "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
    250:    "0x20dd72Ed959b6147912C2e529F0a0C651c33c9ce",  # Fantom non-standard
    324:    "0xBA1333333333a1BA1108E8412f11850A5C319bA9",  # zkSync
    59144:  "0xBA12222222228d8Ba445958a75a0704d566BF2C8",  # Linea
}

# Uniswap-compatible V2 routers — per chain (first entry = preferred)
V2_ROUTERS: Dict[int, List[str]] = {
    1:      ["0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"],  # Uniswap V2
    56:     ["0x10ED43C718714eb63d5aA57B78B54704E256024E"],  # PancakeSwap V2
    137:    ["0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff"],  # QuickSwap V2
    42161:  ["0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506"],  # SushiSwap Arbitrum
    10:     ["0x4A7b5Da61326A6379179b40d00F57E5bbDC962c2"],  # Velodrome-compat
    8453:   ["0x327Df1E6de05895d2ab08513aaDD9313Fe505d86"],  # BaseSwap V2
    43114:  ["0x60aE616a2155Ee3d9A68541Ba4544862310933d4"],  # TraderJoe V2
    250:    ["0xF491e7B69E4244ad4002BC14e878a34207E38c29"],  # SpookySwap
    324:    ["0x9B5def958d0f3b6955cBEa4D5B7809b2fb26b059"],  # SyncSwap zkSync (custom)
    59144:  ["0x610D2f07b7EdC67565160F587F37636194C34E74"],  # HorizonDEX Linea
}

# Uniswap V3 SwapRouter02 — per chain
V3_ROUTERS: Dict[int, Optional[str]] = {
    1:      "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
    56:     "0xB971eF87ede563556b2ED4b1C0b0019111Dd85d2",  # PancakeSwap V3 router
    137:    "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
    42161:  "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
    10:     "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
    8453:   "0x2626664c2603336E57B271c5C0b26F421741e481",
    43114:  "0xbb00FF08d01D300023C629E8fFfFcb65A5a578cE",  # TraderJoe V3
    250:    None,                                          # Fantom — no Uni V3
    324:    "0x99c56385daBCE3E81d8499d0b8d0257aBC07E8A3",  # SyncSwap zkSync
    59144:  "0x3d4e44Eb1374240CE5F1B136B58aEA539c39be70",  # HorizonDEX Linea V3
}

# Gas limits per operation type
GAS_LIMITS = {
    "flash_loan_v2_v2": 350_000,
    "flash_loan_v2_v3": 420_000,
    "flash_loan_v3_v3": 500_000,
    "flash_loan_curve":  600_000,
    "flash_loan_balancer": 700_000,
}

# Flash loan fee bps
FLASH_FEE_BPS = {
    "balancer": 0,    # FREE
    "aave":     5,    # 0.05%
}

EXECUTION_FLOOR_USD = 1_000.0
FLASH_SIZE_FACTOR = 0.10

# ─────────────────────────────────────────────────────────────
#  ABIs (minimal, selector-only approach)
# ─────────────────────────────────────────────────────────────

BALANCER_FLASHLOAN_ABI = [{
    "name": "flashLoan",
    "type": "function",
    "stateMutability": "nonpayable",
    "inputs": [
        {"name": "recipient",  "type": "address"},
        {"name": "tokens",     "type": "address[]"},
        {"name": "amounts",    "type": "uint256[]"},
        {"name": "userData",   "type": "bytes"},
    ],
    "outputs": [],
}]

AAVE_FLASHLOAN_ABI = [{
    "name": "flashLoan",
    "type": "function",
    "stateMutability": "nonpayable",
    "inputs": [
        {"name": "receiverAddress", "type": "address"},
        {"name": "assets",          "type": "address[]"},
        {"name": "amounts",         "type": "uint256[]"},
        {"name": "modes",           "type": "uint256[]"},
        {"name": "onBehalfOf",      "type": "address"},
        {"name": "params",          "type": "bytes"},
        {"name": "referralCode",    "type": "uint16"},
    ],
    "outputs": [],
}]

V2_ROUTER_ABI = [{
    "name": "swapExactTokensForTokens",
    "type": "function",
    "stateMutability": "nonpayable",
    "inputs": [
        {"name": "amountIn",     "type": "uint256"},
        {"name": "amountOutMin", "type": "uint256"},
        {"name": "path",         "type": "address[]"},
        {"name": "to",           "type": "address"},
        {"name": "deadline",     "type": "uint256"},
    ],
    "outputs": [{"name": "amounts", "type": "uint256[]"}],
}]

V3_ROUTER_ABI = [{
    "name": "exactInputSingle",
    "type": "function",
    "stateMutability": "payable",
    "inputs": [{
        "name": "params",
        "type": "tuple",
        "components": [
            {"name": "tokenIn",           "type": "address"},
            {"name": "tokenOut",          "type": "address"},
            {"name": "fee",               "type": "uint24"},
            {"name": "recipient",         "type": "address"},
            {"name": "amountIn",          "type": "uint256"},
            {"name": "amountOutMinimum",  "type": "uint256"},
            {"name": "sqrtPriceLimitX96", "type": "uint160"},
        ],
    }],
    "outputs": [{"name": "amountOut", "type": "uint256"}],
}]

CURVE_POOL_ABI = [{
    "name": "exchange",
    "type": "function",
    "stateMutability": "nonpayable",
    "inputs": [
        {"name": "i", "type": "int128"},
        {"name": "j", "type": "int128"},
        {"name": "dx", "type": "uint256"},
        {"name": "min_dy", "type": "uint256"},
    ],
    "outputs": [{"name": "dy", "type": "uint256"}],
}]

BALANCER_VAULT_SWAP_ABI = [{
    "name": "swap",
    "type": "function",
    "stateMutability": "payable",
    "inputs": [
        {
            "name": "singleSwap",
            "type": "tuple",
            "components": [
                {"name": "poolId", "type": "bytes32"},
                {"name": "kind", "type": "uint8"},
                {"name": "assetIn", "type": "address"},
                {"name": "assetOut", "type": "address"},
                {"name": "amount", "type": "uint256"},
                {"name": "userData", "type": "bytes"},
            ],
        },
        {
            "name": "funds",
            "type": "tuple",
            "components": [
                {"name": "sender", "type": "address"},
                {"name": "fromInternalBalance", "type": "bool"},
                {"name": "recipient", "type": "address"},
                {"name": "toInternalBalance", "type": "bool"},
            ],
        },
        {"name": "limit", "type": "uint256"},
        {"name": "deadline", "type": "uint256"},
    ],
    "outputs": [{"name": "amountCalculated", "type": "uint256"}],
}]


# ─────────────────────────────────────────────────────────────
#  Data model
# ─────────────────────────────────────────────────────────────

@dataclass
class ExecutionPayload:
    """
    Complete, immediately broadcastable execution payload for one
    cross-DEX arbitrage opportunity on a single chain.
    """
    chain_id:          int
    chain_name:        str
    token_in:          str          # address (borrow token)
    token_mid:         str          # address (intermediate)
    token_in_symbol:   str
    token_mid_symbol:  str
    loan_amount_wei:   int          # flash loan size in wei
    loan_amount_usd:   float
    flash_size_usd:    float
    min_pool_tvl_usd:  float

    # Flash loan leg
    flash_provider:    str          # "balancer" | "aave"
    flash_contract:    str          # vault / pool address
    flash_calldata:    str          # hex-encoded ABI calldata
    flash_fee_bps:     int

    # Swap leg 1 — buy (borrow → intermediate)
    buy_router:        str
    buy_pool:          str
    buy_calldata:      str
    buy_protocol:      str          # "v2" | "v3" | "curve" | "balancer"

    # Swap leg 2 — sell (intermediate → repay + profit)
    sell_router:       str
    sell_pool:         str
    sell_calldata:     str
    sell_protocol:     str

    # Economics
    gross_profit_usd:  float
    flash_fee_usd:     float
    gas_limit:         int
    gas_priority_gwei: float        # suggested EIP-1559 tip
    net_profit_usd:    float        # gross − flash_fee − gas_est

    # Meta
    spread_bps:        float
    executable:        bool         # True if net_profit > 0
    note:              str = "Single-chain cross-DEX only. No cross-chain arbitrage."

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


# ─────────────────────────────────────────────────────────────
#  Builder
# ─────────────────────────────────────────────────────────────

class ExecutionPayloadBuilder:
    """
    Builds a broadcast-ready ExecutionPayload for every
    ChainSpreadOpportunity emitted by the multi-chain engine.

    Uses a dummy Web3 instance for ABI encoding — no RPC required.
    """

    def __init__(self):
        self._w3 = Web3()   # ABI encoder only, no provider needed

    # ── Public entry point ────────────────────────────────────

    def build(
        self,
        opp: Dict[str, Any],
        loan_amount_usd: Optional[float] = 50_000.0,
        gas_price_gwei: float = 30.0,
        slippage_bps: int = 50,
    ) -> Optional[ExecutionPayload]:
        """
        Build an ExecutionPayload from a spread opportunity dict.

        Args:
            opp            : ChainSpreadOpportunity.to_dict()
            loan_amount_usd: Flash loan size in USD (default $50k)
            gas_price_gwei : Base fee + tip for gas estimation
            slippage_bps   : Max slippage tolerance

        Returns:
            ExecutionPayload or None if unprofitable / missing config
        """
        chain_id   = opp.get("chain_id", 0)
        chain_name = opp.get("chain_name", "unknown")

        try:
            # ── 0. Dynamic flash size + execution floor ───────
            loan_amount_usd, min_pool_tvl_usd = self._resolve_flash_size_usd(
                opp, loan_amount_usd
            )
            if loan_amount_usd is None or loan_amount_usd <= 0:
                logger.debug("[ExecBuilder] invalid flash size after TVL sizing")
                return None
            if min_pool_tvl_usd < EXECUTION_FLOOR_USD:
                logger.debug(
                    f"[ExecBuilder] min TVL ${min_pool_tvl_usd:,.2f} below floor ${EXECUTION_FLOOR_USD:,.2f}"
                )
                return None

            # ── 1. Select flash loan provider ─────────────────
            flash_provider, flash_addr = self._select_flash_provider(
                chain_id,
                opp.get("token0_address", ""),
                loan_amount_usd,
            )
            if not flash_addr:
                logger.debug(f"[ExecBuilder] no flash provider on chain {chain_id}")
                return None

            # ── 2. Token addresses & amounts ──────────────────
            token_in     = Web3.to_checksum_address(opp["token0_address"])
            token_mid    = Web3.to_checksum_address(opp["token1_address"])
            t0_dec       = opp.get("token0_decimals", 18)
            t1_dec       = opp.get("token1_decimals", 18)
            loan_wei     = int(loan_amount_usd * (10 ** t0_dec) / max(opp.get("buy_price", 1.0), 1e-12))

            # ── 3. Build swap calldatas ───────────────────────
            buy_proto    = opp.get("buy_protocol",  "v2")
            sell_proto   = opp.get("sell_protocol", "v2")
            buy_pool     = opp.get("buy_pool",  "")
            sell_pool    = opp.get("sell_pool", "")
            buy_pool_meta = opp.get("buy_pool_meta", {})
            sell_pool_meta = opp.get("sell_pool_meta", {})
            buy_price = float(opp.get("buy_price", 0.0) or 0.0)
            expected_buy_out = None
            if buy_price > 0 and loan_wei > 0:
                expected_buy_out = int(((loan_wei / (10 ** t0_dec)) * buy_price) * (10 ** t1_dec))

            buy_router, buy_cd   = self._swap_calldata(
                chain_id, opp.get("buy_dex", buy_proto), buy_proto, token_in, token_mid, buy_pool, loan_wei, slippage_bps, buy_pool_meta, expected_buy_out
            )
            sell_router, sell_cd = self._swap_calldata(
                chain_id, opp.get("sell_dex", sell_proto), sell_proto, token_mid, token_in, sell_pool, 0, slippage_bps, sell_pool_meta, None
            )

            # ── 4. Flash loan calldata (wraps both swaps) ─────
            inner_data = self._encode_inner(buy_cd, sell_cd, buy_router, sell_router)
            flash_cd   = self._flash_calldata(
                flash_provider, flash_addr, token_in, loan_wei, inner_data
            )

            # ── 5. Economics ──────────────────────────────────
            spread_bps      = opp.get("spread_bps", 0.0)
            gross_profit_usd = loan_amount_usd * (spread_bps / 10_000.0)
            flash_fee_usd   = loan_amount_usd * FLASH_FEE_BPS[flash_provider] / 10_000.0
            gas_limit       = self._gas_limit(buy_proto, sell_proto)
            gas_est_usd     = gas_limit * gas_price_gwei * 1e-9 * 2500.0  # assume $2500/ETH equiv
            net_profit_usd  = gross_profit_usd - flash_fee_usd - gas_est_usd

            return ExecutionPayload(
                chain_id         = chain_id,
                chain_name       = chain_name,
                token_in         = token_in,
                token_mid        = token_mid,
                token_in_symbol  = opp.get("token0_symbol", "T0"),
                token_mid_symbol = opp.get("token1_symbol", "T1"),
                loan_amount_wei  = loan_wei,
                loan_amount_usd  = loan_amount_usd,
                flash_size_usd   = loan_amount_usd,
                min_pool_tvl_usd = min_pool_tvl_usd,
                flash_provider   = flash_provider,
                flash_contract   = flash_addr,
                flash_calldata   = flash_cd,
                flash_fee_bps    = FLASH_FEE_BPS[flash_provider],
                buy_router       = buy_router,
                buy_pool         = buy_pool,
                buy_calldata     = buy_cd,
                buy_protocol     = buy_proto,
                sell_router      = sell_router,
                sell_pool        = sell_pool,
                sell_calldata    = sell_cd,
                sell_protocol    = sell_proto,
                gross_profit_usd = round(gross_profit_usd, 4),
                flash_fee_usd    = round(flash_fee_usd, 4),
                gas_limit        = gas_limit,
                gas_priority_gwei= gas_price_gwei,
                net_profit_usd   = round(net_profit_usd, 4),
                spread_bps       = spread_bps,
                executable       = net_profit_usd > 0,
            )

        except Exception as e:
            logger.warning(f"[ExecBuilder] build failed chain={chain_id}: {e}")
            return None

    # ── Internal helpers ──────────────────────────────────────

    def _select_flash_provider(
        self, chain_id: int, token: str, loan_usd: float
    ):
        """Prefer Balancer (0 fee); fall back to Aave."""
        bal = BALANCER_VAULT.get(chain_id)
        if bal:
            return "balancer", bal
        aave = AAVE_V3_POOL.get(chain_id)
        if aave:
            return "aave", aave
        return None, None

    @staticmethod
    def _resolve_flash_size_usd(
        opp: Dict[str, Any],
        fallback_loan_amount_usd: Optional[float],
    ) -> Tuple[Optional[float], float]:
        liquidity_candidates = []
        for key in ("buy_pool_liquidity_usd", "sell_pool_liquidity_usd", "liquidity_usd"):
            value = opp.get(key)
            if value is None:
                continue
            try:
                f = float(value)
                if f > 0:
                    liquidity_candidates.append(f)
            except (TypeError, ValueError):
                continue

        if liquidity_candidates:
            min_pool_tvl_usd = min(liquidity_candidates)
            return min_pool_tvl_usd * FLASH_SIZE_FACTOR, min_pool_tvl_usd

        fallback = float(fallback_loan_amount_usd or 0.0)
        if fallback <= 0:
            return None, 0.0
        synthetic_tvl = fallback / FLASH_SIZE_FACTOR
        return fallback, synthetic_tvl

    def _swap_calldata_v2(
        self,
        chain_id: int,
        token_in: str,
        token_out: str,
        amount_in: int,
        slippage_bps: int,
        deadline: int,
        expected_amount_out: Optional[int] = None,
    ):
        router = (V2_ROUTERS.get(chain_id) or ["0x" + "0" * 40])[0]
        c = self._w3.eth.contract(abi=V2_ROUTER_ABI)
        amount_out_min = self._amount_out_min(expected_amount_out, slippage_bps)
        cd = c.encode_abi(
            abi_element_identifier="swapExactTokensForTokens",
            args=[amount_in, amount_out_min, [token_in, token_out], EXECUTOR_CONTRACT_ADDRESS, deadline],
        )
        return router, cd

    def _swap_calldata_v3(
        self,
        chain_id: int,
        token_in: str,
        token_out: str,
        amount_in: int,
        slippage_bps: int,
        deadline: int,
        pool_meta: Optional[Dict[str, Any]] = None,
        expected_amount_out: Optional[int] = None,
    ):
        router = V3_ROUTERS.get(chain_id) or "0x" + "0" * 40
        c = self._w3.eth.contract(abi=V3_ROUTER_ABI)
        fee_tier = self._resolve_v3_fee_tier(pool_meta)
        cd = c.encode_abi(
            abi_element_identifier="exactInputSingle",
            args=[(
                token_in,
                token_out,
                fee_tier,
                EXECUTOR_CONTRACT_ADDRESS,
                amount_in,
                self._amount_out_min(expected_amount_out, slippage_bps),
                0,
            )],
        )
        return router, cd

    def _swap_calldata_curve(
        self,
        token_in: str,
        token_out: str,
        pool: str,
        amount_in: int,
        slippage_bps: int,
        pool_meta: Optional[Dict[str, Any]] = None,
        expected_amount_out: Optional[int] = None,
    ):
        if not pool:
            raise ValueError("Curve pool address is required")
        tokens = [t.lower() for t in (pool_meta or {}).get("tokens", []) if isinstance(t, str)]
        token_in_l = token_in.lower()
        token_out_l = token_out.lower()
        if token_in_l in tokens and token_out_l in tokens:
            i = tokens.index(token_in_l)
            j = tokens.index(token_out_l)
        else:
            i, j = 0, 1
        c = self._w3.eth.contract(abi=CURVE_POOL_ABI)
        amount_out_min = self._amount_out_min(expected_amount_out, slippage_bps)
        cd = c.encode_abi(
            abi_element_identifier="exchange",
            args=[i, j, amount_in, amount_out_min],
        )
        return pool, cd

    def _swap_calldata_balancer(
        self,
        chain_id: int,
        token_in: str,
        token_out: str,
        amount_in: int,
        slippage_bps: int,
        deadline: int,
        pool_meta: Optional[Dict[str, Any]] = None,
        expected_amount_out: Optional[int] = None,
    ):
        pool_id = (pool_meta or {}).get("pool_id")
        if not pool_id:
            raise ValueError("Balancer pool_id is required for swap encoding")
        if isinstance(pool_id, bytes):
            pool_id_bytes = pool_id
        else:
            pool_id_bytes = bytes.fromhex(str(pool_id).replace("0x", ""))
        vault = BALANCER_VAULT.get(chain_id)
        if not vault:
            raise ValueError(f"Balancer vault missing for chain {chain_id}")
        c = self._w3.eth.contract(abi=BALANCER_VAULT_SWAP_ABI)
        amount_out_min = self._amount_out_min(expected_amount_out, slippage_bps)
        single_swap = (
            pool_id_bytes,
            0,
            token_in,
            token_out,
            amount_in,
            b"",
        )
        funds = (
            EXECUTOR_CONTRACT_ADDRESS,
            False,
            EXECUTOR_CONTRACT_ADDRESS,
            False,
        )
        cd = c.encode_abi(
            abi_element_identifier="swap",
            args=[single_swap, funds, amount_out_min, deadline],
        )
        return vault, cd

    @staticmethod
    def _amount_out_min(expected_amount_out: Optional[int], slippage_bps: int) -> int:
        if not expected_amount_out or expected_amount_out <= 0:
            return 0
        return int(expected_amount_out * (1 - (slippage_bps / 10_000)))

    @staticmethod
    def _resolve_v3_fee_tier(pool_meta: Optional[Dict[str, Any]]) -> int:
        meta = pool_meta or {}
        for key in ("fee_tier", "fee", "feeTier"):
            value = meta.get(key)
            if value is not None:
                fee = int(value)
                if fee <= 0:
                    raise ValueError("V3 fee tier must be positive")
                return fee
        if meta.get("fee_bps") is not None:
            converted = int(meta["fee_bps"]) * 100
            if converted > 0:
                return converted
        raise ValueError("V3 fee tier is required in pool metadata")

    def _swap_calldata(
        self,
        chain_id: int,
        dex: str,
        protocol: str,
        token_in: str,
        token_out: str,
        pool: str,
        amount_in: int,
        slippage_bps: int,
        pool_meta: Optional[Dict[str, Any]] = None,
        expected_amount_out: Optional[int] = None,
    ):
        """Build swap calldata via fail-closed protocol adapters."""
        import time as _time
        deadline = int(_time.time()) + 300   # 5-minute window
        encoded = encode_swap(SwapEncodingContext(
            chain_id=chain_id,
            dex=dex,
            protocol=protocol,
            pool=pool,
            token_in=token_in,
            token_out=token_out,
            amount_in=amount_in,
            amount_out_min=self._amount_out_min(expected_amount_out, slippage_bps),
            recipient=EXECUTOR_CONTRACT_ADDRESS,
            deadline=deadline,
            pool_meta=pool_meta or {},
        ))
        return encoded.router, encoded.calldata_hex

    def _encode_inner(
        self, buy_cd: str, sell_cd: str, buy_router: str, sell_router: str
    ) -> bytes:
        """
        ABI-encode the inner swap sequence as userData bytes.
        This is the data passed into the flash loan callback.
        """
        encoded = self._w3.codec.encode(
            ["address", "bytes", "address", "bytes"],
            [
                Web3.to_checksum_address(buy_router),
                bytes.fromhex(buy_cd[2:]) if buy_cd.startswith("0x") else b"",
                Web3.to_checksum_address(sell_router),
                bytes.fromhex(sell_cd[2:]) if sell_cd.startswith("0x") else b"",
            ],
        )
        return encoded

    def _flash_calldata(
        self,
        provider: str,
        vault_addr: str,
        token: str,
        amount: int,
        inner: bytes,
    ) -> str:
        """Build flash loan calldata wrapping the inner swap payload."""
        if provider == "balancer":
            c = self._w3.eth.contract(
                address=Web3.to_checksum_address(vault_addr),
                abi=BALANCER_FLASHLOAN_ABI,
            )
            return c.encode_abi(
                abi_element_identifier="flashLoan",
                args=[EXECUTOR_CONTRACT_ADDRESS, [token], [amount], inner],
            )
        else:  # aave
            c = self._w3.eth.contract(
                address=Web3.to_checksum_address(vault_addr),
                abi=AAVE_FLASHLOAN_ABI,
            )
            return c.encode_abi(
                abi_element_identifier="flashLoan",
                args=[EXECUTOR_CONTRACT_ADDRESS, [token], [amount], [0], EXECUTOR_CONTRACT_ADDRESS, inner, 0],
            )

    def _gas_limit(self, buy_proto: str, sell_proto: str) -> int:
        combined = f"{buy_proto}_{sell_proto}"
        if "curve" in combined or "balancer" in combined:
            return GAS_LIMITS["flash_loan_balancer"]
        if "v3" in combined:
            return GAS_LIMITS["flash_loan_v3_v3"]
        return GAS_LIMITS["flash_loan_v2_v2"]


# ── Singleton ─────────────────────────────────────────────────

_builder: Optional[ExecutionPayloadBuilder] = None


def get_payload_builder() -> ExecutionPayloadBuilder:
    global _builder
    if _builder is None:
        _builder = ExecutionPayloadBuilder()
    return _builder


def build_payload(opp: Dict, **kwargs) -> Optional[Dict]:
    """Convenience wrapper — returns dict or None."""
    result = get_payload_builder().build(opp, **kwargs)
    return result.to_dict() if result else None
