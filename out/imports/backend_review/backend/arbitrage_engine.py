"""
APEX_OMEGA Arbitrage Engine
Integrates with existing system logic for spreads, flash loans, and pool prices
Uses EXACT AMM formulas for accurate arbitrage profit calculations
Supports Aave V3 AND Balancer Vault flash loans (dual execution)
"""

import os
import time
import asyncio
import logging
import json
from decimal import Decimal, InvalidOperation
import uuid
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from enum import IntEnum
from pathlib import Path
from executor_registry import get_rpc_url
try:
    from web3 import Web3
    _WEB3_AVAILABLE = True
except ModuleNotFoundError as exc:
    if exc.name != "web3":
        raise
    _WEB3_AVAILABLE = False

    class _Web3Stub:
        """Minimal stub used when web3 is not installed (e.g. unit-test environments)."""

        class HTTPProvider:
            def __init__(self, *a, **kw):
                pass

        @staticmethod
        def to_checksum_address(address: str) -> str:
            from eth_utils.address import to_checksum_address as eth_utils_to_checksum_address

            return eth_utils_to_checksum_address(address)
        def __init__(self, *a, **kw):
            pass

        def is_connected(self) -> bool:
            raise NotImplementedError("web3 is not installed; connectivity checks require web3")

        class Eth:
            block_number = 0

        eth = Eth()

        class _AccountAPI:
            @staticmethod
            def from_key(_key):
                raise NotImplementedError("web3 is not installed; signing requires web3")

            @staticmethod
            def sign_transaction(_tx, _key):
                raise NotImplementedError("web3 is not installed; signing requires web3")

        account = _AccountAPI()

    Web3 = _Web3Stub  # type: ignore[assignment]

from dotenv import load_dotenv
from execution_governance import get_governance_service, get_minimum_net_profit_usd
from transaction_builder import TransactionBuilder, TransactionBuilderError

load_dotenv(Path(__file__).parent / '.env')
logger = logging.getLogger(__name__)

# Import EXACT swap simulator for accurate profit calculations
try:
    from swap_simulator import swap_simulator, ProtocolType as SwapProtocolType
    EXACT_SWAP_ENABLED = True
except ImportError:
    EXACT_SWAP_ENABLED = False
    logger.warning("Exact swap simulator not available")

# Import TITAN engine for gas calculations
try:
    from titan_slippage import titan_engine, ProtocolType
    TITAN_ENABLED = True
except ImportError:
    TITAN_ENABLED = False

# Import Web3 pool fetcher for real blockchain data
try:
    from web3_pool_fetcher import Web3PoolFetcher
    WEB3_FETCHER_ENABLED = True
except ImportError:
    WEB3_FETCHER_ENABLED = False
    logger.warning("Web3 pool fetcher not available")

# Import flash loan provider selector
try:
    from flash_loan_providers import flash_loan_selector, FlashLoanProvider, FLASH_LOAN_PROVIDERS
    FLASH_LOAN_SELECTOR_ENABLED = True
except ImportError:
    FLASH_LOAN_SELECTOR_ENABLED = False
    logger.warning("Flash loan selector not available")

# Import Slippage Sentinel for DYNAMIC slippage prediction
try:
    from slippage_sentinel import get_slippage_sentinel
    SLIPPAGE_SENTINEL_ENABLED = True
except ImportError:
    SLIPPAGE_SENTINEL_ENABLED = False
    logger.warning("Slippage Sentinel not available - using static slippage")


class DexId(IntEnum):
    """DEX Identifiers"""
    UNISWAP_V2 = 1
    UNISWAP_V3 = 2
    QUICKSWAP_V2 = 3
    QUICKSWAP_V3 = 4
    SUSHISWAP = 5
    BALANCER = 6
    CURVE = 7
    ALGEBRA = 8


class Protocol(IntEnum):
    """Protocol types"""
    V2 = 2
    V3 = 3
    STABLE = 4
    WEIGHTED = 5


# Token configurations for Polygon
TOKENS = {
    "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174": {"symbol": "USDC", "decimals": 6},
    "0xc2132D05D31c914a87C6611C10748AEb04B58e8F": {"symbol": "USDT", "decimals": 6},
    "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270": {"symbol": "WMATIC", "decimals": 18},
    "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619": {"symbol": "WETH", "decimals": 18},
    "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6": {"symbol": "WBTC", "decimals": 8},
    "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063": {"symbol": "DAI", "decimals": 18},
    "0x53E0bca35eC356BD5ddDFebbD1Fc0fD03FaBad39": {"symbol": "LINK", "decimals": 18},
    "0xD6DF932A45C0f255f85145f286eA0b292B21C90B": {"symbol": "AAVE", "decimals": 18},
    "0x0000000000000000000000000000000000001010": {"symbol": "POL", "decimals": 18}, # Native gas token
}

# Simple token price oracle (hardcoded common prices - Jan 2025)
# In production, replace with Chainlink oracle or CoinGecko API
TOKEN_PRICES_USD = {
    "USDC": 1.0,
    "USDT": 1.0,
    "DAI": 1.0,
    "WMATIC": 0.85,
    "MATIC": 0.85,
    "POL": 0.85,
    "WETH": 3300.0,
    "ETH": 3300.0,
    "WBTC": 95000.0,
    "BTC": 95000.0,
    "LINK": 22.0,
    "AAVE": 280.0,
    # Lowercase mapping
    "wmatic": 0.85,
    "weth": 3300.0,
    "wbtc": 95000.0,
    "pol": 0.85,
    "usdc": 1.0,
    "usdt": 1.0,
    "dai": 1.0,
    "link": 22.0,
    "aave": 280.0,
}

def _protocol_int_to_str(protocol: int) -> str:
    """Map internal Protocol int to universal_arbitrage protocol string."""
    if protocol == Protocol.V2:
        return "v2"
    if protocol == Protocol.V3:
        return "v3"
    if protocol == Protocol.WEIGHTED:
        return "balancer"
    if protocol == Protocol.STABLE:
        return "curve"
    return "v3"  # safe default


@dataclass
class SwapLeg:
    """Single leg of an arbitrage swap"""
    pool: str
    dex: str
    dex_id: int
    protocol: int
    token_in: str
    token_out: str
    amount_in_usd: float
    amount_out_usd: float
    fee_paid_usd: float
    slippage_usd: float
    spot_price: float
    effective_price: float
    # Token decimals for accurate execution
    token_in_decimals: int = 18
    token_out_decimals: int = 18
    # Token USD prices — required for correct USD→wei conversion in the payload builder
    token_in_price_usd: Optional[float] = None
    token_out_price_usd: Optional[float] = None
    # Pool fee tier in basis points (e.g. 500, 3000, 10000) — required for V3 exactInputSingle
    fee: int = 3000

    @staticmethod
    def _usd_to_native_units(amount_usd: float, price_usd: float, decimals: int) -> int:
        """Convert USD notional to token-native integer units using explicit price metadata."""
        try:
            usd = Decimal(str(amount_usd))
            price = Decimal(str(price_usd))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError("Invalid USD amount or token price for native amount conversion") from exc

        if usd < 0:
            raise ValueError("USD amount must be non-negative")
        if price <= 0:
            raise ValueError("Token USD price must be positive")
        if decimals < 0:
            raise ValueError("Token decimals must be non-negative")

        return int((usd / price) * (Decimal(10) ** int(decimals)))

    @property
    def amount_in(self) -> int:
        if self.token_in_price_usd is None:
            raise ValueError("Missing token_in_price_usd for native amount conversion")
        return self._usd_to_native_units(
            self.amount_in_usd,
            self.token_in_price_usd,
            self.token_in_decimals,
        )

    @property
    def amount_out(self) -> int:
        if self.token_out_price_usd is None:
            raise ValueError("Missing token_out_price_usd for native amount conversion")
        return self._usd_to_native_units(
            self.amount_out_usd,
            self.token_out_price_usd,
            self.token_out_decimals,
        )

    def to_dict(self) -> Dict:
        return {
            "pool": self.pool,
            "dex": self.dex,
            "protocol": self.protocol,
            "tokenIn": self.token_in,
            "tokenOut": self.token_out,
            "amountIn": str(self.amount_in) if self.token_in_price_usd is not None else None,
            "amountOut": str(self.amount_out) if self.token_out_price_usd is not None else None,
            "amountInUsd": self.amount_in_usd,
            "amountOutUsd": self.amount_out_usd,
            "feePaidUsd": self.fee_paid_usd,
            "slippageUsd": self.slippage_usd,
            "spotPrice": self.spot_price,
            "effectivePrice": self.effective_price,
            "tokenInDecimals": self.token_in_decimals,
            "tokenOutDecimals": self.token_out_decimals,
            "tokenInPriceUsd": self.token_in_price_usd,
            "tokenOutPriceUsd": self.token_out_price_usd,
            "fee": self.fee,
        }


@dataclass
class FlashLoanData:
    """Flash loan arbitrage opportunity data with multi-provider support"""
    loan_amount_usd: float = 0
    flash_loan_fee_bps: int = 0
    flash_loan_fee_usd: float = 0
    leg1: Optional[SwapLeg] = None
    leg2: Optional[SwapLeg] = None
    total_fees_usd: float = 0
    total_slippage_usd: float = 0
    gas_cost_usd: float = 0
    gas_units: int = 0
    repay_amount_usd: float = 0
    net_profit_usd: float = 0
    net_profit_after_gas_usd: float = 0
    roi_percent: float = 0
    is_executable: bool = False
    hops: int = 2
    # Flash loan provider details
    flash_loan_provider: str = "Aave V3"  # Primary provider
    balancer_profit_usd: float = 0  # Profit using Balancer (FREE)
    aave_profit_usd: float = 0  # Profit using Aave (0.09% fee)
    dual_execution: bool = False  # Fire both if profitable
    total_extraction_usd: float = 0  # Total profit from all providers
    
    def to_dict(self) -> Dict:
        loan_amount = None
        net_profit_amount = None
        if self.leg1 and self.leg1.token_in_price_usd is not None:
            loan_amount = str(self.leg1.amount_in)
        if self.leg2 and self.leg2.token_out_price_usd is not None:
            net_profit_amount = str(
                SwapLeg._usd_to_native_units(
                    self.net_profit_usd,
                    self.leg2.token_out_price_usd,
                    self.leg2.token_out_decimals,
                )
            )
        return {
            "loanAmount": loan_amount,
            "loanAmountUsd": self.loan_amount_usd,
            "loanToken": self.leg1.token_in if self.leg1 else None,
            "loanTokenDecimals": self.leg1.token_in_decimals if self.leg1 else None,
            "loanTokenPriceUsd": self.leg1.token_in_price_usd if self.leg1 else None,
            "profitToken": self.leg2.token_out if self.leg2 else None,
            "profitTokenDecimals": self.leg2.token_out_decimals if self.leg2 else None,
            "profitTokenPriceUsd": self.leg2.token_out_price_usd if self.leg2 else None,
            "netProfitAmount": net_profit_amount,
            "flashLoanFeeBps": self.flash_loan_fee_bps,
            "flashLoanFeeUsd": self.flash_loan_fee_usd,
            "leg1": self.leg1.to_dict() if self.leg1 else None,
            "leg2": self.leg2.to_dict() if self.leg2 else None,
            "totalFeesUsd": self.total_fees_usd,
            "totalSlippageUsd": self.total_slippage_usd,
            "gasCostUsd": self.gas_cost_usd,
            "gasUnits": self.gas_units,
            "repayAmountUsd": self.repay_amount_usd,
            "netProfitUsd": self.net_profit_usd,
            "netProfitAfterGasUsd": self.net_profit_after_gas_usd,
            "roiPercent": self.roi_percent,
            "isExecutable": self.is_executable,
            "hops": self.hops,
            "flashLoanProvider": self.flash_loan_provider,
            "balancerProfitUsd": self.balancer_profit_usd,
            "aaveProfitUsd": self.aave_profit_usd,
            "dualExecution": self.dual_execution,
            "totalExtractionUsd": self.total_extraction_usd,
        }


@dataclass
class SpreadOpportunity:
    """Spread/arbitrage opportunity"""
    id: str
    timestamp: int
    token_pair: str
    min_reserve_usd: float
    flash_loan: FlashLoanData
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "tokenPair": self.token_pair,
            "minReserveUsd": self.min_reserve_usd,
            "flashLoan": self.flash_loan.to_dict(),
        }


@dataclass
class PoolPrice:
    """Pool price data with reserves for exact swap calculations"""
    pool_address: str
    dex_id: int
    dex_name: str
    token0: str
    token1: str
    token0_symbol: str
    token1_symbol: str
    spot_price: float
    reserve_usd: float
    protocol: int
    fee: int
    liquidity: int = 0
    tick: int = 0
    sqrt_price_x96: int = 0
    last_updated: int = 0
    # Actual token reserves for exact swap calculations
    reserve0: float = 0  # Token0 reserve in native units
    reserve1: float = 0  # Token1 reserve in native units
    weight0: float = 0.5  # Balancer weight for token0
    weight1: float = 0.5  # Balancer weight for token1
    amp_factor: int = 100  # Amplification factor for stableswap
    # Token decimals (CRITICAL for price calculations)
    token0_decimals: int = 18
    token1_decimals: int = 18
    
    def to_dict(self) -> Dict:
        return {
            "poolAddress": self.pool_address,
            "dexId": self.dex_id,
            "dexName": self.dex_name,
            "token0": self.token0,
            "token1": self.token1,
            "token0Symbol": self.token0_symbol,
            "token1Symbol": self.token1_symbol,
            "spotPrice": self.spot_price,
            "reserveUsd": self.reserve_usd,
            "protocol": self.protocol,
            "fee": self.fee,
        }


class ArbitrageEngine:
    """
    Main arbitrage engine that combines pool scanning with spread detection
    and flash loan opportunity calculation
    """
    
    def __init__(self, rpc_url: str = None):
        # Use provided RPC or environment variable
        if rpc_url is None:
            rpc_url = get_rpc_url('polygon') or "https://polygon-rpc.com"
        
        logger.info(f"🔗 Connecting to Polygon: {rpc_url[:60]}...")
        self.w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': 30}))
        self.pool_ready_min = int(os.getenv('OMEGA_MIN_READY_POOLS', '1'))
        self.pool_bootstrap_status: Dict[str, Any] = {
            "state": "initializing",
            "started_at": time.time(),
            "completed_at": None,
            "elapsed_s": 0.0,
            "providers_connected": [],
            "factories_scanned": 0,
            "pools_discovered": 0,
            "local_pools": 0,
            "unique_pools": 0,
            "pools_with_reserves": 0,
            "pools_normalized": 0,
            "pools_published": 0,
            "skipped_pools": 0,
            "unknown_token_pools": 0,
            "active_scanners": [],
            "failed_scanners": [],
            "cache_ready": False,
            "minimum_required_pools": self.pool_ready_min,
            "last_heartbeat": time.time(),
            "last_exception": None,
        }
        
        if self.w3.is_connected():
            logger.info(f"✅ Connected! Block: {self.w3.eth.block_number:,}")
            self.pool_bootstrap_status["providers_connected"].append("polygon_rpc")
        else:
            logger.error("❌ RPC connection failed!")
            self.pool_bootstrap_status["failed_scanners"].append("polygon_rpc")
        
        self.pools: Dict[str, PoolPrice] = {}
        self.spreads: List[SpreadOpportunity] = []
        self.last_update = 0
        self.pools_db_path = Path(__file__).parent / 'data' / 'pools.json'

        
        # Initialize Web3 pool fetcher for EXACT blockchain data (institutional-grade)
        if WEB3_FETCHER_ENABLED and self.w3.is_connected():
            self.pool_fetcher = Web3PoolFetcher(self.w3)
            logger.info("✅ Web3 pool fetcher initialized - EXACT on-chain data mode")
        else:
            self.pool_fetcher = None
            logger.error("❌ Web3 pool fetcher not available - CANNOT proceed without EXACT data")
        
        # Configuration from YOUR production .env
        self.min_reserve_usd = float(os.getenv('MIN_RESERVE_USD', '50000'))
        self.min_profit_usd = max(
            float(os.getenv('MIN_NET_PROFIT_USD', str(get_minimum_net_profit_usd()))),
            get_minimum_net_profit_usd()
        )
        self.flash_loan_fee_bps = int(os.getenv('FLASH_FEE_BPS', '9'))
        self.gas_price_gwei = float(os.getenv('SIM_DEFAULT_GAS_GWEI', '60'))
        self.gas_units = int(os.getenv('ESTIMATED_GAS_UNITS', '450000'))
        self.matic_price = 0.50

        # Execution context
        self.private_key = os.getenv("PRIVATE_KEY")
        self.wallet_address = os.getenv("EXECUTOR_WALLET")
        if self.private_key and not self.wallet_address:
            from eth_account import Account
            self.wallet_address = Account.from_key(self.private_key).address
            logger.info(f"🔑 Wallet address derived from private key: {self.wallet_address}")
        elif self.wallet_address:
            logger.info(f"🔑 Executor wallet configured: {self.wallet_address}")
        
        logger.info(f"⚙️  Min Profit: ${self.min_profit_usd} | Gas: {self.gas_price_gwei}Gwei")
        
        # SOLUTION: Load pools in background thread using MULTICALL3 batching
        # Pools will be available after ~2-5s (not 30-60s!)
        import threading
        self.pools_loading = True
        
        def load_pools_async():
            logger.info("🚀 Loading pools with MULTICALL3 batch + EXACT Web3 data...")
            start_time = time.time()
            self.pool_bootstrap_status.update(
                {
                    "state": "loading",
                    "started_at": start_time,
                    "active_scanners": ["unified_discovery", "local_database", "multicall3", "token_prices"],
                    "last_heartbeat": start_time,
                }
            )
            try:
                self._load_pools_from_db()
            except Exception as exc:
                self.pool_bootstrap_status["state"] = "failed"
                self.pool_bootstrap_status["last_exception"] = repr(exc)
                failed = self.pool_bootstrap_status.setdefault("failed_scanners", [])
                if "pool_loader" not in failed:
                    failed.append("pool_loader")
                logger.exception("Pool bootstrap failed before cache publication")
            finally:
                elapsed = time.time() - start_time
                published = len(self.pools)
                self.pools_loading = False
                if self.pool_bootstrap_status.get("state") != "failed":
                    self.pool_bootstrap_status["state"] = "ready" if published >= self.pool_ready_min else "empty"
                self.pool_bootstrap_status.update(
                    {
                        "completed_at": time.time(),
                        "elapsed_s": round(elapsed, 3),
                        "pools_published": published,
                        "cache_ready": published >= self.pool_ready_min,
                        "active_scanners": [],
                        "last_heartbeat": time.time(),
                    }
                )
                if published >= self.pool_ready_min:
                    logger.info(f"✅ Batch loading complete: {published} pools with EXACT data in {elapsed:.1f}s")
                else:
                    logger.error(
                        "Pool bootstrap completed without usable pool data: %s",
                        self.get_pool_bootstrap_status(),
                    )
        
        # Start background loading
        threading.Thread(target=load_pools_async, daemon=True).start()
        
        logger.info("🎯 ArbitrageEngine initialized (MULTICALL3 batch loading in background...)")
        
        # INSTITUTIONAL MATH INTEGRATION
        # Feature flag to enable/disable (for testing & rollback)
        self.enable_institutional_math = os.getenv('ENABLE_INSTITUTIONAL_MATH', 'true').lower() == 'true'
        
        if self.enable_institutional_math:
            try:
                from institutional_integration import get_institutional_coordinator
                self.institutional_coordinator = get_institutional_coordinator(self.w3)
                
                # Gas snapshot cache (10-second TTL for performance)
                self._gas_snapshot_cache = None
                self._gas_snapshot_cache_time = 0
                self._gas_snapshot_ttl = 10.0  # seconds
                
                # Execution trace storage (LRU cache, max 1000 opportunities)
                from collections import OrderedDict
                self._execution_traces = OrderedDict()  # {ssn: InstitutionalOpportunity}
                self._max_traces = 1000
                
                logger.info("✅ INSTITUTIONAL MATH ENABLED")
                logger.info("   - Angeris-Chitra optimal sizing")
                logger.info("   - Depth & health validation")
                logger.info("   - SSOT pipeline (4 invariants)")
                logger.info("   - EIP-1559 optimal tip")
                logger.info("   - Balancer 0% flash loans")
            except ImportError as e:
                logger.error(f"❌ Institutional math modules not available: {e}")
                logger.info("   Falling back to basic arbitrage math")
                self.enable_institutional_math = False
                self.institutional_coordinator = None
        else:
            logger.info("⚠️  INSTITUTIONAL MATH DISABLED (using basic math)")
            self.institutional_coordinator = None
    
    def get_pool_bootstrap_status(self) -> Dict[str, Any]:
        """Return a stable diagnostic snapshot for live-discovery readiness waits."""
        status = dict(getattr(self, "pool_bootstrap_status", {}))
        heartbeat = status.get("last_heartbeat")
        if heartbeat:
            status["last_heartbeat_age_s"] = round(max(time.time() - float(heartbeat), 0.0), 3)
        status["pools_published"] = len(getattr(self, "pools", {}) or {})
        status["cache_ready"] = status["pools_published"] >= int(status.get("minimum_required_pools", 1) or 1)
        status["pools_loading"] = bool(getattr(self, "pools_loading", False))
        return status
    
    def get_token_info(self, address: str) -> Dict:
        """Get token info with fallback"""
        # First, check the static TOKENS map for well-known assets.
        checksum_address = Web3.to_checksum_address(address)
        if checksum_address in TOKENS:
            return TOKENS[checksum_address]

        # If not found, dynamically create a placeholder. The symbol and decimals
        # will be updated with exact on-chain data during the pool loading process.
        # This ensures ALL discovered assets are supported, not just pre-configured ones.
        return {
            "symbol": f"DYN_{address[:6]}",  # Dynamic token placeholder
            "decimals": 18,  # Default, will be overwritten by exact data
        }
    
    def get_cached_gas_snapshot(self):
        """
        Get gas snapshot with 10-second cache
        Reduces RPC calls from 200ms to 0.1ms when cached
        """
        if not self.enable_institutional_math or not self.institutional_coordinator:
            return None
        
        current_time = time.time()
        
        # Check cache validity
        if (self._gas_snapshot_cache is not None and 
            (current_time - self._gas_snapshot_cache_time) < self._gas_snapshot_ttl):
            return self._gas_snapshot_cache
        
        # Cache miss or expired - fetch new snapshot
        try:
            from mev_gas_oracle import get_gas_oracle
            oracle = get_gas_oracle(self.w3)
            snapshot = oracle.get_gas_snapshot()
            
            # Update cache
            self._gas_snapshot_cache = snapshot
            self._gas_snapshot_cache_time = current_time
            
            return snapshot
        except Exception as e:
            logger.warning(f"Gas snapshot failed: {e}")
            return None
    
    def store_execution_trace(self, institutional_opp):
        """
        Store execution trace for dashboard retrieval
        Uses LRU eviction when max size reached
        """
        if not self.enable_institutional_math:
            return
        
        ssn = institutional_opp.ssn
        self._execution_traces[ssn] = institutional_opp
        
        # LRU eviction
        if len(self._execution_traces) > self._max_traces:
            # Remove oldest (first inserted)
            self._execution_traces.popitem(last=False)
    
    def get_execution_trace(self, ssn: str):
        """Retrieve execution trace by SSN for dashboard"""
        return self._execution_traces.get(ssn)
    
    def get_dex_name(self, dex_id: int) -> str:
        """Get DEX name by ID"""
        dex = get_dex_by_id(dex_id)
        return dex["name"] if dex else f"DEX_{dex_id}"
    
    def calculate_token_price_usd(self, pool: PoolPrice, token_address: str) -> float:
        """
        Calculate token price in USD from pool reserves
        CRITICAL: Reserves are ALREADY NORMALIZED (not raw wei)!
        Only works reliably for stablecoin pairs!
        """
        token_address = token_address.lower()
        token0_lower = pool.token0.lower()
        token1_lower = pool.token1.lower()
        
        # CRITICAL: Reserves are already normalized by web3_pool_fetcher!
        # Do NOT divide by decimals again!
        reserve0_normalized = pool.reserve0  # Already in human units
        reserve1_normalized = pool.reserve1  # Already in human units
        
        # Check if either token is a stablecoin
        stablecoins = [
            "0x2791bca1f2de4661ed88a30c99a7a9449aa84174",  # USDC
            "0xc2132d05d31c914a87c6611c10748aeb04b58e8f",  # USDT
            "0x8f3cf7ad23cd3cadbd9735aff958023239c6a063",  # DAI
        ]
        
        token0_is_stable = token0_lower in stablecoins
        token1_is_stable = token1_lower in stablecoins
        
        # CRITICAL FIX: Only calculate prices for stablecoin pairs
        # For non-stable pairs, we cannot reliably determine USD price from reserves alone
        
        if token_address == token0_lower:
            # Calculating price of token0
            if token1_is_stable and reserve0_normalized > 0:
                # token0 price = stable_reserve / token0_reserve (in USD)
                price = reserve1_normalized / reserve0_normalized
                # Sanity check: price should be reasonable (not trillion dollars)
                if price > 1e9 or price < 1e-9:
                    return 1.0  # Fallback for insane prices
                return price
            elif token0_is_stable:
                return 1.0  # Stablecoin = $1
            else:
                # No stablecoin in pair - cannot determine USD price reliably
                # Return 1.0 as fallback (will cause this spread to be skipped)
                return 1.0
        else:
            # Calculating price of token1
            if token0_is_stable and reserve1_normalized > 0:
                # token1 price = stable_reserve / token1_reserve (in USD)
                price = reserve0_normalized / reserve1_normalized
                # Sanity check
                if price > 1e9 or price < 1e-9:
                    return 1.0  # Fallback for insane prices
                return price
            elif token1_is_stable:
                return 1.0  # Stablecoin = $1
            else:
                # No stablecoin in pair
                return 1.0
    
    def _get_token_price_usd(self, token_symbol: str, token_address: str) -> float:
        """
        Get token price in USD using REAL price oracle
        
        Priority:
        1. Fetch from DEXScreener API (REAL prices for ALL tokens)
        2. Fallback to known tokens if API fails
        3. Return 0 only if truly unknown
        """
        # Import real oracle
        from real_token_oracle import get_real_price_oracle
        
        # Try fetching REAL price from DEXScreener
        oracle = get_real_price_oracle()
        real_price = oracle.get_token_price_usd(token_address, chain="polygon")
        
        if real_price > 0:
            return real_price
        
        # Fallback: Try symbol lookup (for cached known tokens)
        symbol_upper = token_symbol.upper()
        for known_addr, info in TOKENS.items():
            if known_addr.lower() == token_address.lower():
                known_symbol = info["symbol"]
                if known_symbol.upper() == symbol_upper:
                    # This is a known token, but oracle failed. Return 0 to be safe.
                    logger.warning(f"Oracle failed for known token {token_symbol}. Returning 0.")
                    return 0.0
        
        # Unknown token - API didn't find it either
        logger.debug(f"No price found for token: {token_symbol} ({token_address[:10]}...)")
        return 0.0
    
    def _load_pools_from_db(self):
        """
        Load pools from MULTIPLE SOURCES with MULTICALL3 batch fetching
        
        Sources:
        1. 1inch API → 100+ DEXs
        2. DefiLlama → TVL metadata
        3. Local database → Cached pools
        
        OPTIMIZATION: Uses Multicall3 to fetch ALL pool reserves in 1 RPC call
        Speed: ~2-5 seconds for 1000+ pools (vs 5+ minutes sequential)
        """
        import time
        from multicall_batch_loader import get_batch_loader
        from unified_pool_discovery import get_unified_discovery
        
        logger.info("🌐 INSTITUTIONAL POOL DISCOVERY: 1inch + DefiLlama + Database")
        
        start_total = time.time()
        
        # STEP 1: Discover pools from all sources. A venue outage must not block
        # cached/local pools from being normalized and published.
        self.pool_bootstrap_status["last_heartbeat"] = time.time()
        discovered_pools = {}
        discovery_timeout_s = float(os.getenv("OMEGA_UNIFIED_DISCOVERY_TIMEOUT_S", "3"))
        if discovery_timeout_s <= 0:
            failed = self.pool_bootstrap_status.setdefault("failed_scanners", [])
            if "unified_discovery_disabled" not in failed:
                failed.append("unified_discovery_disabled")
            logger.info("Unified pool discovery disabled; using local database pools only")
        else:
            import queue
            import threading

            result_queue: "queue.Queue[tuple[str, Any]]" = queue.Queue(maxsize=1)

            def run_unified_discovery():
                try:
                    discovery = get_unified_discovery()
                    result_queue.put(("ok", discovery.discover_all_pools()))
                except Exception as exc:
                    result_queue.put(("error", exc))

            worker = threading.Thread(target=run_unified_discovery, daemon=True)
            worker.start()
            worker.join(discovery_timeout_s)
            if worker.is_alive():
                failed = self.pool_bootstrap_status.setdefault("failed_scanners", [])
                if "unified_discovery_timeout" not in failed:
                    failed.append("unified_discovery_timeout")
                self.pool_bootstrap_status["last_exception"] = f"unified discovery exceeded {discovery_timeout_s:.1f}s"
                logger.warning(
                    "Unified pool discovery exceeded %.1fs; continuing with local database pools",
                    discovery_timeout_s,
                )
            else:
                status, payload = result_queue.get() if not result_queue.empty() else ("ok", {})
                if status == "ok":
                    discovered_pools = payload or {}
                else:
                    self.pool_bootstrap_status["last_exception"] = repr(payload)
                    failed = self.pool_bootstrap_status.setdefault("failed_scanners", [])
                    if "unified_discovery" not in failed:
                        failed.append("unified_discovery")
                    logger.warning("Unified pool discovery failed; continuing with local database pools: %s", payload)
        self.pool_bootstrap_status["pools_discovered"] = len(discovered_pools)
        
        # STEP 2: Load local database pools
        if not self.pools_db_path.exists():
            logger.warning(f"Local pool database not found: {self.pools_db_path}")
            local_pools = []
        else:
            try:
                with open(self.pools_db_path, 'r') as f:
                    data = json.load(f)
                    local_pools = data.get('pools', [])
                    logger.info(f"📊 Local database: {len(local_pools)} pools")
            except Exception as exc:
                local_pools = []
                self.pool_bootstrap_status["last_exception"] = repr(exc)
                failed = self.pool_bootstrap_status.setdefault("failed_scanners", [])
                if "local_database" not in failed:
                    failed.append("local_database")
                logger.warning("Local pool database load failed; continuing without cached pools: %s", exc)
        self.pool_bootstrap_status["local_pools"] = len(local_pools)
        self.pool_bootstrap_status["last_heartbeat"] = time.time()
        
        # STEP 3: Merge all sources (deduplicate by address)
        all_pool_addresses = set()
        pool_metadata = {}
        
        # Add discovered pools
        for pool_addr, metadata in discovered_pools.items():
            all_pool_addresses.add(pool_addr.lower())
            pool_metadata[pool_addr.lower()] = metadata
        
        # Add local database pools
        for pool_data in local_pools:
            addr = pool_data.get('pair_address', '').lower()
            if addr:
                all_pool_addresses.add(addr)
                if addr not in pool_metadata:
                    pool_metadata[addr] = pool_data
        
        def pool_priority(addr: str) -> tuple[int, str]:
            metadata = pool_metadata.get(addr, {})
            token0_known = str(metadata.get('token0_symbol', '')).upper() in TOKEN_PRICES_USD
            token1_known = str(metadata.get('token1_symbol', '')).upper() in TOKEN_PRICES_USD
            return (-(int(token0_known) + int(token1_known)), addr)

        pool_addresses = sorted(all_pool_addresses, key=pool_priority)
        discovered_unique_count = len(pool_addresses)
        default_max_pools = "100" if os.getenv("OMEGA_LIVE_TEST") else "0"
        max_bootstrap_pools = int(os.getenv("OMEGA_MAX_POOL_BOOTSTRAP_POOLS", default_max_pools))
        if max_bootstrap_pools > 0 and len(pool_addresses) > max_bootstrap_pools:
            logger.warning(
                "Pool bootstrap capped at %d/%d pools for bounded live-test startup",
                max_bootstrap_pools,
                len(pool_addresses),
            )
            pool_addresses = pool_addresses[:max_bootstrap_pools]
        self.pool_bootstrap_status["unique_pools"] = len(pool_addresses)
        self.pool_bootstrap_status["candidate_pools_total"] = discovered_unique_count
        logger.info(f"📍 TOTAL UNIQUE POOLS: {len(pool_addresses)} loaded ({discovered_unique_count} discovered/cached)")
        
        # STEP 4: MULTICALL3 BATCH LOADING - Fetch EXACT reserves for ALL
        batch_loader = get_batch_loader(self.w3)
        start_batch = time.time()
        try:
            exact_reserves = batch_loader.batch_load_pools(pool_addresses)
        except Exception as exc:
            exact_reserves = {}
            self.pool_bootstrap_status["last_exception"] = repr(exc)
            failed = self.pool_bootstrap_status.setdefault("failed_scanners", [])
            if "multicall3" not in failed:
                failed.append("multicall3")
            logger.warning("Multicall3 pool reserve load failed; no exact reserves available: %s", exc)
        batch_time = time.time() - start_batch
        self.pool_bootstrap_status["pools_with_reserves"] = len(exact_reserves)
        self.pool_bootstrap_status["last_heartbeat"] = time.time()
        
        logger.info(f"⚡ Multicall3 fetched {len(exact_reserves)} pools in {batch_time:.2f}s")
        
        # STEP 4.5: BATCH FETCH ALL TOKEN PRICES FROM DEXSCREENER
        # Collect all unique token addresses from pool metadata
        logger.info("🔍 Collecting unique token addresses for batch price fetching...")
        from real_token_oracle import get_real_price_oracle
        
        unique_tokens = set()
        for pool_addr in pool_addresses:
            metadata = pool_metadata.get(pool_addr, {})
            token0_addr = metadata.get('token0_address', '')
            token1_addr = metadata.get('token1_address', '')
            if token0_addr:
                unique_tokens.add(token0_addr.lower())
            if token1_addr:
                unique_tokens.add(token1_addr.lower())
        
        unique_token_list = list(unique_tokens)
        logger.info(f"📍 Found {len(unique_token_list)} unique tokens across all pools")
        
        # Batch fetch prices from DEXScreener (30 tokens per request)
        logger.info("🌐 Fetching real prices from DEXScreener API (batched)...")
        start_price_fetch = time.time()
        skip_external_prices = (
            os.getenv("OMEGA_SKIP_EXTERNAL_TOKEN_PRICES", "1" if os.getenv("OMEGA_LIVE_TEST") else "0").lower()
            in {"1", "true", "yes", "on"}
        )
        if skip_external_prices:
            batch_prices = {}
            failed = self.pool_bootstrap_status.setdefault("failed_scanners", [])
            if "external_token_prices_skipped" not in failed:
                failed.append("external_token_prices_skipped")
            logger.info("External token price fetch skipped; using static known-token prices")
        else:
            oracle = get_real_price_oracle()
            try:
                batch_prices = oracle.get_multiple_prices(unique_token_list, chain="polygon") if unique_token_list else {}
            except Exception as exc:
                batch_prices = {}
                self.pool_bootstrap_status["last_exception"] = repr(exc)
                failed = self.pool_bootstrap_status.setdefault("failed_scanners", [])
                if "token_prices" not in failed:
                    failed.append("token_prices")
                logger.warning("Batch token price fetch failed; falling back to static known-token prices: %s", exc)
        price_fetch_time = time.time() - start_price_fetch
        price_coverage_pct = (100 * len(batch_prices) / len(unique_token_list)) if unique_token_list else 0.0
        self.pool_bootstrap_status["last_heartbeat"] = time.time()
        
        logger.info(f"✅ Fetched {len(batch_prices)} token prices in {price_fetch_time:.2f}s")
        logger.info(f"📊 Price coverage: {len(batch_prices)}/{len(unique_token_list)} tokens ({price_coverage_pct:.1f}%)")
        
        # STEP 5: Build PoolPrice objects with EXACT data
        pool_prices = {}
        skipped = 0
        unknown_token_pools = 0  # Track pools with unknown tokens (kept in DB but TVL=0)
        
        for pool_address in pool_addresses:
            try:
                # Get exact reserves from multicall
                exact_data = exact_reserves.get(pool_address)
                if not exact_data or 'reserve0' not in exact_data:
                    skipped += 1
                    continue
                
                reserve0_raw = exact_data['reserve0']
                reserve1_raw = exact_data['reserve1']
                
                # Get metadata BEFORE normalization (need decimals)
                metadata = pool_metadata.get(pool_address, {})
                
                # Get token decimals
                token0_decimals = int(metadata.get('token0_decimals', 18))
                token1_decimals = int(metadata.get('token1_decimals', 18))
                
                # CRITICAL FIX: Normalize reserves from wei to human-readable units
                # Example: 1,000,000,000,000,000,000 wei WMATIC → 1.0 WMATIC
                reserve0 = reserve0_raw / (10 ** token0_decimals)
                reserve1 = reserve1_raw / (10 ** token1_decimals)
                
                # Skip pools with extreme imbalances or zero reserves
                if reserve0 == 0 or reserve1 == 0:
                    skipped += 1
                    continue
                
                ratio = max(reserve0, reserve1) / min(reserve0, reserve1)
                if ratio > 1e15:  # Extreme imbalance
                    skipped += 1
                    continue
                
                # Convert fee to tier notation (30 bps → 3000)
                # fee_bps is the actual basis points (30 = 0.30%)
                # fee in tier notation is bps * 100 (3000 for 0.30%)
                fee_bps = metadata.get('fee_bps', metadata.get('fee', 30))
                fee_tier = fee_bps * 100 if fee_bps < 1000 else fee_bps  # Convert if needed
                
                # P0 FIX: Get real token prices from BATCH-FETCHED results
                token0_addr = metadata.get('token0_address', '').lower()
                token1_addr = metadata.get('token1_address', '').lower()
                
                # P0 FIX: Get real token prices from BATCH-FETCHED results
                token0_price_usd = batch_prices.get(token0_addr, 0.0)
                token1_price_usd = batch_prices.get(token1_addr, 0.0)
                
                # Calculate TVL from both sides
                tvl_from_token0 = reserve0 * token0_price_usd
                tvl_from_token1 = reserve1 * token1_price_usd
                
                # CRITICAL CHANGE: Keep ALL pools, even if price = 0
                # If price is unknown, set TVL = 0 (pool won't show in spreads but data preserved)
                if token0_price_usd == 0 or token1_price_usd == 0:
                    reserve_usd = 0  # Pool has unknown token - set TVL to 0
                    unknown_token_pools += 1
                    logger.debug(f"Pool {metadata.get('pair_address', 'unknown')[:10]}... has unknown token (TVL=0, kept in database)")
                elif tvl_from_token0 > 0 and tvl_from_token1 > 0:
                    reserve_usd = (tvl_from_token0 + tvl_from_token1)
                elif tvl_from_token0 > 0:
                    reserve_usd = tvl_from_token0 * 2  # Assume balanced
                elif tvl_from_token1 > 0:
                    reserve_usd = tvl_from_token1 * 2
                else:
                    reserve_usd = 0
                
                # Build PoolPrice with EXACT data from Multicall3 (NOW NORMALIZED!)
                pool_prices[pool_address] = PoolPrice(
                    pool_address=pool_address,
                    dex_id=metadata.get('dex_id', ''),
                    dex_name=metadata.get('dex_name', metadata.get('project', 'Unknown')),
                    token0=exact_data.get('token0', metadata.get('token0_address', '')),
                    token1=exact_data.get('token1', metadata.get('token1_address', '')),
                    token0_symbol=metadata.get('token0_symbol', ''),
                    token1_symbol=metadata.get('token1_symbol', ''),
                    spot_price=reserve1 / reserve0 if reserve0 > 0 else 0,
                    reserve_usd=reserve_usd,  # ← P0 FIX: Real TVL or 0 (no more fake $50k)
                    protocol=metadata.get('protocol', 2),
                    fee=fee_tier,  # Now properly converted to tier notation
                    liquidity=0,
                    last_updated=0,
                    reserve0=reserve0,  # ← NOW NORMALIZED (human-readable units)
                    reserve1=reserve1,  # ← NOW NORMALIZED (human-readable units)
                    weight0=0,
                    weight1=0,
                    amp_factor=0,
                    sqrt_price_x96=0,
                    tick=0,
                    token0_decimals=token0_decimals,
                    token1_decimals=token1_decimals
                )
            
            except Exception as e:
                logger.debug(f"Failed to load pool {pool_address[:10]}: {e}")
                skipped += 1
                continue
        
        self.pools = pool_prices
        self.pool_bootstrap_status.update(
            {
                "pools_normalized": len(pool_prices),
                "pools_published": len(pool_prices),
                "skipped_pools": skipped,
                "unknown_token_pools": unknown_token_pools,
                "cache_ready": len(pool_prices) >= self.pool_ready_min,
                "last_heartbeat": time.time(),
            }
        )
        
        total_time = time.time() - start_total
        logger.info(f"✅ Successfully loaded {len(pool_prices)} pools with EXACT reserves")
        logger.info(f"📊 Pool breakdown: {unknown_token_pools} with unknown tokens (TVL=0), {skipped} skipped (no reserves)")
        logger.info(f"⚡ Total discovery + fetch time: {total_time:.2f}s")
        logger.info(f"🌐 DEXScreener batch pricing: {len(batch_prices)} tokens priced")
        logger.info("📊 Coverage: 1inch + DefiLlama + Database = INSTITUTIONAL GRADE")
    
    def calculate_slippage(
        self,
        amount_usd: float,
        pool_tvl_usd: float,
        fee_bps: int,
        protocol: int
    ) -> float:
        """
        Calculate slippage using TITAN engine with POOL TVL
        CRITICAL: Uses the TVL of the specific swap pool, NOT the flash loan pool
        """
        if TITAN_ENABLED:
            if protocol == Protocol.V3:
                return titan_engine.v3_slippage(amount_usd, pool_tvl_usd, fee_bps / 100)
            elif protocol == Protocol.V2:
                # For V2, we use TVL as both reserve approximations
                return titan_engine.v2_slippage(amount_usd, pool_tvl_usd / 2, pool_tvl_usd / 2, fee_bps / 100)
            elif protocol == Protocol.STABLE:
                return titan_engine.curve_slippage(amount_usd, pool_tvl_usd, 100)
            else:  # WEIGHTED (Balancer)
                return titan_engine.balancer_slippage(amount_usd, pool_tvl_usd / 2)
        
        # Fallback calculation
        if pool_tvl_usd == 0:
            return 10.0
        return (amount_usd / pool_tvl_usd) * 100
    
    
    def calculate_gas_cost_usd(self, gas_units: int = None) -> float:
        """
        Calculate gas cost in USD for Polygon network
        
        Args:
            gas_units: Number of gas units (uses default if not provided)
            
        Returns:
            Gas cost in USD (typically $0.01-0.03 on Polygon)
        """
        units = gas_units or self.gas_units
        # Gas cost in MATIC = (gas_price_gwei × gas_units) / 1e9
        gas_cost_matic = (self.gas_price_gwei * units) / 1e9
        # Convert to USD
        return gas_cost_matic * self.matic_price
    
    def get_dynamic_slippage_prediction(
        self,
        trade_amount_usd: float,
        pool: 'PoolPrice',
        dex_protocol: str = 'quickswap_v2'
    ) -> Dict[str, float]:
        """
        Get DYNAMIC slippage prediction from Slippage Sentinel ML model
        
        This replaces static 0.20% slippage with real-time ML predictions based on:
        - Trade amount / pool liquidity ratio
        - Recent volatility
        - Pool characteristics
        
        Returns dict with 'predicted_slippage', 'confidence_score', etc.
        """
        if not SLIPPAGE_SENTINEL_ENABLED:
            # Fallback to simple calculation if Sentinel not available
            utilization = trade_amount_usd / pool.reserve_usd if pool.reserve_usd > 0 else 0
            return {
                'predicted_slippage': utilization * 0.5,
                'confidence_score': 0.5,
                'impact_category': 'fallback'
            }
        
        sentinel = get_slippage_sentinel()
        
        # Prepare pool data for protocol-specific calculation
        pool_data = {
            'reserve_in': pool.reserve0,
            'reserve_out': pool.reserve1,
            'fee_bps': pool.fee // 100
        }
        
        return sentinel.predict_slippage(
            trade_amount_usd=trade_amount_usd,
            pool_liquidity_usd=pool.reserve_usd,
            volatility_1h=0.01,  # Could be enhanced with real volatility data
            volatility_24h=0.02,
            gas_price_gwei=self.gas_price_gwei,
            spread_bps=30,  # Default DEX fee
            dex_protocol=dex_protocol,
            pool_data=pool_data
        )
    
    def find_optimal_loan_amount(
        self,
        pool1: PoolPrice,
        pool2: PoolPrice,
        min_loan_usd: float = 1000,
        max_loan_usd: float = 1000000
    ) -> tuple[float, dict]:
        """
        Find the optimal flash loan amount that maximizes profit
        
        OPTIMIZED: Test only 2 loan sizes instead of 5 to prevent timeout
        """
        # Determine maximum safe loan based on pool TVLs
        pool1_tvl = pool1.reserve_usd
        pool2_tvl = pool2.reserve_usd
        min_pool_tvl = min(pool1_tvl, pool2_tvl)
        
        # Skip if pools have no TVL data
        if min_pool_tvl == 0:
            return 0, None
        
        # Maximum loan should be at most 5% of smallest pool
        max_tvl_fraction = float(os.getenv('MAX_TVL_FRACTION', '0.05'))
        max_safe_loan = min(min_pool_tvl * max_tvl_fraction, max_loan_usd)
        
        if max_safe_loan < min_loan_usd:
            return 0, None
        
        # OPTIMIZED: Evaluate a small candidate set:
        #  - baseline min loan (to avoid greedy extension regressions)
        #  - 1% and 3% TVL exploratory sizes
        # Then keep only the best executable candidate by net-after-gas.
        test_fractions = [0.01, 0.03]
        candidate_loans = []
        if min_loan_usd <= max_safe_loan:
            candidate_loans.append(min_loan_usd)
        for fraction in test_fractions:
            test_loan = min_pool_tvl * fraction
            if min_loan_usd <= test_loan <= max_safe_loan:
                candidate_loans.append(test_loan)

        # De-duplicate and keep deterministic order
        candidate_loans = sorted(set(candidate_loans))

        best_executable_loan = 0
        best_executable_profit_after_gas = float('-inf')
        best_executable_spread = None
        
        for test_loan in candidate_loans:
            spread = self.analyze_spread(pool1, pool2, test_loan)
            if not spread:
                continue

            profit_after_gas = getattr(
                spread.flash_loan,
                "net_profit_after_gas_usd",
                spread.flash_loan.net_profit_usd,
            )

            # Rollback-safe behavior: only allow an "extension" to replace the
            # current candidate if it remains executable and improves net profit.
            if spread.flash_loan.is_executable and profit_after_gas > best_executable_profit_after_gas:
                best_executable_profit_after_gas = profit_after_gas
                best_executable_loan = test_loan
                best_executable_spread = spread
        
        return best_executable_loan, best_executable_spread
    
    def _quick_profitability_filter(self, pool1: PoolPrice, pool2: PoolPrice) -> bool:
        """
        Phase B: Universal cross-protocol fast pre-filter.

        Uses `universal_arbitrage.verify_profitability()` to discard pool pairs
        whose spot-price differential cannot beat combined fees BEFORE running
        the expensive `_analyze_basic` / `_analyze_institutional` paths.

        Returns True if the pair *might* be profitable (proceed), False if
        definitively non-profitable (skip).
        Always returns True on errors — fail open, never miss a real opp.
        """
        try:
            from universal_arbitrage import get_universal_calculator

            # Build minimal pool dicts for the universal verifier
            p1_dict = {
                "protocol": _protocol_int_to_str(pool1.protocol),
                "reserve0": pool1.reserve0,
                "reserve1": pool1.reserve1,
                "fee_bps": pool1.fee // 100,
                "sqrt_price_x96": pool1.sqrt_price_x96,
                "liquidity": pool1.liquidity,
                "tick": pool1.tick,
                "weight0": pool1.weight0,
                "weight1": pool1.weight1,
                "amp_factor": pool1.amp_factor,
            }
            p2_dict = {
                "protocol": _protocol_int_to_str(pool2.protocol),
                "reserve0": pool2.reserve0,
                "reserve1": pool2.reserve1,
                "fee_bps": pool2.fee // 100,
                "sqrt_price_x96": pool2.sqrt_price_x96,
                "liquidity": pool2.liquidity,
                "tick": pool2.tick,
                "weight0": pool2.weight0,
                "weight1": pool2.weight1,
                "amp_factor": pool2.amp_factor,
            }

            calc = get_universal_calculator()
            is_profitable, _ratio = calc.verify_profitability(p1_dict, p2_dict)
            return is_profitable
        except Exception as e:
            # Fail open — don't miss real opportunities
            logger.debug(f"quick_profitability_filter failed open: {e}")
            return True

    def analyze_spread(
        self,
        pool1: PoolPrice,
        pool2: PoolPrice,
        loan_amount_usd: float = 10000
    ) -> Optional[SpreadOpportunity]:
        """
        Analyze spread between two pools

        ROUTING LOGIC:
        - Quick universal pre-filter (Phase B) — discards hopeless pairs cheaply
        - If INSTITUTIONAL_MATH enabled: Use full institutional analysis
        - If disabled or fails: Fall back to basic analysis

        Returns SpreadOpportunity if profitable
        """

        # Phase B: Universal cross-protocol pre-filter
        if not self._quick_profitability_filter(pool1, pool2):
            return None

        # INSTITUTIONAL MATH PATH (with graceful fallback)
        if self.enable_institutional_math and self.institutional_coordinator:
            try:
                institutional_result = self._analyze_institutional(pool1, pool2, loan_amount_usd)
                if institutional_result is not None:
                    # Store trace for dashboard
                    if hasattr(institutional_result, '_institutional_opp'):
                        self.store_execution_trace(institutional_result._institutional_opp)
                    return institutional_result
                else:
                    # Institutional analysis rejected opportunity (correct behavior)
                    return None
            except Exception as e:
                logger.error(f"❌ Institutional analysis failed: {e}")
                logger.info("   Falling back to basic analysis")
                # Fall through to basic analysis
        
        # BASIC ANALYSIS PATH (fallback or when institutional disabled)
        return self._analyze_basic(pool1, pool2, loan_amount_usd)
    
    def _analyze_institutional(
        self,
        pool1: PoolPrice,
        pool2: PoolPrice,
        loan_amount_usd: float = 10000
    ) -> Optional[SpreadOpportunity]:
        """
        INSTITUTIONAL MATH ANALYSIS
        Uses: Optimal sizing, depth validation, SSOT, gas optimization, Balancer 0%
        """
        
        # Verify same token pair
        pair1 = frozenset([pool1.token0, pool1.token1])
        pair2 = frozenset([pool2.token0, pool2.token1])
        if pair1 != pair2:
            return None
        
        # Determine buy/sell direction
        pool1_price = pool1.reserve1 / pool1.reserve0 if pool1.reserve0 > 0 else 0
        pool2_price = pool2.reserve1 / pool2.reserve0 if pool2.reserve0 > 0 else 0
        
        if pool1_price <= 0 or pool2_price <= 0:
            return None
        
        # Determine direction
        if pool1_price < pool2_price:
            buy_pool, sell_pool = pool1, pool2
        else:
            buy_pool, sell_pool = pool2, pool1
        
        # Check token ordering between pools
        tokens_reversed = (
            buy_pool.token0.lower() == sell_pool.token1.lower() and
            buy_pool.token1.lower() == sell_pool.token0.lower()
        )
        
        # Get token price USD (for sizing)
        token_price_usd = self.calculate_token_price_usd(buy_pool, buy_pool.token0)
        if token_price_usd <= 0 or token_price_usd > 1e6:
            return None  # Sanity check failed
        
        # Prepare pool reserves for institutional analysis
        if tokens_reversed:
            # Pool 2 has reversed token order
            pool2_reserve_in = sell_pool.reserve0  # Corresponds to buy_pool.token1
            pool2_reserve_out = sell_pool.reserve1  # Corresponds to buy_pool.token0
        else:
            # Same order
            pool2_reserve_in = sell_pool.reserve1
            pool2_reserve_out = sell_pool.reserve0
        
        # Call institutional coordinator
        institutional_opp = self.institutional_coordinator.analyze_opportunity(
            pool1_reserve_in=buy_pool.reserve0,
            pool1_reserve_out=buy_pool.reserve1,
            pool1_fee_bps=buy_pool.fee // 100,  # Convert tier to bps
            pool2_reserve_in=pool2_reserve_in,
            pool2_reserve_out=pool2_reserve_out,
            pool2_fee_bps=sell_pool.fee // 100,
            token_pair=f"{buy_pool.token0_symbol}/{buy_pool.token1_symbol}",
            buy_dex=buy_pool.dex_name,
            sell_dex=sell_pool.dex_name,
            buy_pool_address=buy_pool.pool_address,
            sell_pool_address=sell_pool.pool_address,
            token_price_usd=token_price_usd,
            max_loan_usd=loan_amount_usd,
            min_profit_usd=get_minimum_net_profit_usd()
        )
        
        if institutional_opp is None or not institutional_opp.is_executable:
            return None  # Opportunity rejected by institutional gates
        
        # Convert InstitutionalOpportunity → SpreadOpportunity
        spread_opp = self._convert_institutional_to_spread(institutional_opp, buy_pool, sell_pool)
        
        # Attach reference for trace storage
        spread_opp._institutional_opp = institutional_opp
        
        return spread_opp
    
    def _convert_institutional_to_spread(
        self,
        inst_opp,
        buy_pool: PoolPrice,
        sell_pool: PoolPrice
    ) -> SpreadOpportunity:
        """
        Convert InstitutionalOpportunity to SpreadOpportunity
        Preserves backward compatibility with existing code
        """
        
        # Build flash loan data
        flash_loan = FlashLoanData(
            loan_amount_usd=inst_opp.optimal_loan_amount,
            flash_loan_fee_bps=inst_opp.flash_fee_bps,
            flash_loan_fee_usd=inst_opp.flash_fee_usd,
            leg1=None,  # TODO: Build from institutional data
            leg2=None,
            total_fees_usd=inst_opp.flash_fee_usd,
            total_slippage_usd=0,  # Included in SSOT calculation
            gas_cost_usd=inst_opp.gas_cost_usd,
            gas_units=350_000,
            repay_amount_usd=inst_opp.optimal_loan_amount + inst_opp.flash_fee_usd,
            net_profit_usd=inst_opp.net_profit_usd,
            net_profit_after_gas_usd=inst_opp.net_profit_usd,
            roi_percent=inst_opp.roi_percent,
            is_executable=inst_opp.is_executable,
            hops=2,
            flash_loan_provider=inst_opp.flash_provider,
            balancer_profit_usd=inst_opp.net_profit_usd if "Balancer" in inst_opp.flash_provider else 0,
            aave_profit_usd=inst_opp.net_profit_usd if "Aave" in inst_opp.flash_provider else 0,
            dual_execution=False,
            total_extraction_usd=inst_opp.net_profit_usd
        )
        
        # Build spread opportunity
        spread_opp = SpreadOpportunity(
            id=inst_opp.ssn,  # Use SSN as ID
            timestamp=inst_opp.timestamp,
            token_pair=inst_opp.token_pair,
            min_reserve_usd=min(buy_pool.reserve_usd, sell_pool.reserve_usd),
            flash_loan=flash_loan
        )
        
        return spread_opp
    
    def _analyze_basic(
        self,
        pool1: PoolPrice,
        pool2: PoolPrice,
        loan_amount_usd: float = 10000
    ) -> Optional[SpreadOpportunity]:
        """
        BASIC ARBITRAGE ANALYSIS — refactored orchestrator (Phase A).

        Uses pure helpers from `arbitrage_helpers` for: pair validation,
        direction selection, two-leg swap simulation, and slippage capping.

        Math is preserved bit-for-bit vs. the prior monolithic implementation.
        """
        from arbitrage_helpers import (
            validate_pair,
            select_direction,
            has_stablecoin_anchor,
            simulate_two_legs,
            calculate_capped_slippage,
            MAX_SLIPPAGE_PCT_DEFAULT,
        )

        # ---------- 1. Validate pair (same tokens, reserves, TVL fraction) ----------
        v = validate_pair(pool1, pool2, loan_amount_usd, self.min_reserve_usd)
        if not v.ok:
            return None

        # ---------- 2. Pick buy/sell direction ----------
        direction = select_direction(pool1, pool2, v.pool1_price, v.pool2_price)
        buy_pool, sell_pool = direction.buy_pool, direction.sell_pool
        buy_price, sell_price = direction.buy_price, direction.sell_price
        tokens_reversed = direction.tokens_reversed

        pair_name = f"{pool1.token0_symbol}/{pool1.token1_symbol}"
        price_spread_pct = ((sell_price - buy_price) / buy_price) * 100
        logger.info(
            f"🎯 ARBITRAGE: BUY {buy_pool.dex_name}@{buy_price:.10f} → "
            f"SELL {sell_pool.dex_name}@{sell_price:.10f} | spread {price_spread_pct:.4f}% ({pair_name})"
        )

        # ---------- 3. USD pricing requires stablecoin anchor ----------
        if not has_stablecoin_anchor(buy_pool):
            return None

        token0_price_usd = self.calculate_token_price_usd(buy_pool, buy_pool.token0)
        token1_price_usd = self.calculate_token_price_usd(buy_pool, buy_pool.token1)

        if token0_price_usd > 1e6 or token1_price_usd > 1e6:
            logger.warning(
                f"⚠️  Skipping {pair_name}: insane prices (${token0_price_usd:.2f}, ${token1_price_usd:.2f})"
            )
            return None

        # ---------- 4. Simulate both swap legs (preserving exact behavior) ----------
        loan_amount_token0_normalized = loan_amount_usd / token0_price_usd

        leg1_result, leg2_result, leg1_out_decimals, leg2_out_decimals = simulate_two_legs(
            swap_simulator=swap_simulator,
            direction=direction,
            loan_amount_token0_normalized=loan_amount_token0_normalized,
        )

        amount_token1 = leg1_result.amount_out
        final_amount_token0 = leg2_result.amount_out

        logger.info(
            f"📊 LEG1 ${loan_amount_usd:,.2f} → {amount_token1:,.6f} {buy_pool.token1_symbol} "
            f"| fee {leg1_result.fee_paid:.6f} slip {leg1_result.slippage_pct:.4f}%"
        )
        logger.info(
            f"📊 LEG2 {amount_token1:,.6f} {buy_pool.token1_symbol} → {final_amount_token0:,.6f} "
            f"{buy_pool.token0_symbol} | fee {leg2_result.fee_paid:.6f} slip {leg2_result.slippage_pct:.4f}%"
        )

        leg1_amount_out_usd = amount_token1 * token1_price_usd
        leg2_amount_out_usd = final_amount_token0 * token0_price_usd

        # ---------- 5. Capped slippage (2% per leg) ----------
        (leg1_slippage_pct_capped, leg2_slippage_pct_capped,
         leg1_slippage_usd_ml, leg2_slippage_usd_ml) = calculate_capped_slippage(
            leg1_amm_pct=leg1_result.slippage_pct,
            leg2_amm_pct=leg2_result.slippage_pct,
            loan_amount_usd=loan_amount_usd,
            leg1_amount_out_usd=float(leg1_amount_out_usd),
            cap_pct=MAX_SLIPPAGE_PCT_DEFAULT,
        )

        # Sanity bug-trace
        # Use Decimal for comparison
        if leg2_amount_out_usd > Decimal('100000'):
            logger.error(
                f"🔴 MATH ANOMALY {buy_pool.token0_symbol}/{buy_pool.token1_symbol} "
                f"loan=${loan_amount_usd:,.2f} out=${leg2_amount_out_usd:,.2f} "
                f"buy={buy_pool.dex_name} sell={sell_pool.dex_name} reversed={tokens_reversed}"
            )

        # ---------- 6. Fees and gross profit ----------
        # Convert all financial values to Decimal for precision
        leg1_fee_usd = Decimal(str(leg1_result.fee_paid)) * Decimal(str(token0_price_usd))
        leg2_fee_usd = Decimal(str(leg2_result.fee_paid)) * Decimal(str(token1_price_usd))

        # Apply a 20% buffer to the gas cost to handle volatility
        GAS_BUFFER_MULTIPLIER = Decimal('1.2')
        gas_cost_usd = Decimal(str(self.calculate_gas_cost_usd()))
        buffered_gas_cost_usd = gas_cost_usd * GAS_BUFFER_MULTIPLIER

        # Gross profit is the raw USD difference after both swaps
        gross_profit_usd = leg2_amount_out_usd - loan_amount_usd
        
        # Calculate profits for BOTH flash loan providers
        if FLASH_LOAN_SELECTOR_ENABLED:
            # Get borrow token (assume token0 for flash loan)
            borrow_token = buy_pool.token0
            
            execution_plan = flash_loan_selector.get_execution_plan(
                borrow_token=borrow_token,
                loan_amount_usd=loan_amount_usd,
                expected_profit_usd=float(gross_profit_usd),
                gas_cost_usd=gas_cost_usd
            )
            
            # Extract provider details
            balancer_details = execution_plan['details'].get('balancer_vault', {})
            aave_details = execution_plan['details'].get('aave_v3', {})
            
            balancer_profit = Decimal(str(balancer_details.get('net_profit', 0)))
            aave_profit = Decimal(str(aave_details.get('net_profit', 0)))
            dual_execution = execution_plan['dual_execution']
            total_extraction = Decimal(str(execution_plan['total_profit']))
            
            # Use best provider for default values
            if balancer_profit > 0:
                primary_provider = "Balancer Vault (FREE)"
                flash_loan_fee_bps = 0
                flash_loan_fee_usd = Decimal('0')
                net_profit_usd = balancer_profit
            elif aave_profit > 0:
                primary_provider = "Aave V3"
                flash_loan_fee_bps = 9
                flash_loan_fee_usd = loan_amount_usd * Decimal('0.0009')
                net_profit_usd = aave_profit
            else:
                primary_provider = "None"
                flash_loan_fee_bps = self.flash_loan_fee_bps
                flash_loan_fee_usd = loan_amount_usd * (Decimal(str(self.flash_loan_fee_bps)) / Decimal('10000'))
                net_profit_usd = gross_profit_usd - flash_loan_fee_usd
            
            net_profit_after_gas_usd = net_profit_usd - buffered_gas_cost_usd
            effective_total_extraction_usd = total_extraction - buffered_gas_cost_usd
            effective_profit_after_gas_usd = max(effective_total_extraction_usd, net_profit_after_gas_usd)
            is_executable = effective_profit_after_gas_usd >= Decimal(str(get_minimum_net_profit_usd()))
            roi_percent = (net_profit_after_gas_usd / loan_amount_usd) * 100 if loan_amount_usd > 0 else Decimal('0')
            
        else:
            # Fallback to Aave only
            primary_provider = "Aave V3"
            flash_loan_fee_bps = self.flash_loan_fee_bps
            flash_loan_fee_usd = loan_amount_usd * (Decimal(str(self.flash_loan_fee_bps)) / Decimal('10000'))
            net_profit_usd = gross_profit_usd - flash_loan_fee_usd
            net_profit_after_gas_usd = net_profit_usd - buffered_gas_cost_usd
            roi_percent = (net_profit_after_gas_usd / loan_amount_usd) * 100 if loan_amount_usd > 0 else Decimal('0')
            is_executable = net_profit_after_gas_usd >= Decimal(str(get_minimum_net_profit_usd()))
            
            balancer_profit = 0
            aave_profit = net_profit_usd
            dual_execution = False
            total_extraction = net_profit_usd
            effective_total_extraction_usd = total_extraction - gas_cost_usd
        
        # ========================================================================
        # COMPREHENSIVE COST BREAKDOWN - USER REQUESTED TRANSPARENCY
        # ALL CALCULATIONS IN USD FIRST, THEN CONVERTED TO PERCENTAGES
        # ========================================================================
        
        # Calculate total costs in USD (absolute values)
        total_dex_fees_usd = float(leg1_fee_usd + leg2_fee_usd)
        total_slippage_usd = float(leg1_slippage_usd_ml + leg2_slippage_usd_ml)
        total_costs_usd = flash_loan_fee_usd + total_dex_fees_usd + total_slippage_usd
        
        # Convert to percentages (for display only - NOT used in calculations!)
        flash_loan_fee_pct = (flash_loan_fee_usd / loan_amount_usd) * 100 if loan_amount_usd > 0 else 0
        total_dex_fees_pct = (total_dex_fees_usd / loan_amount_usd) * 100 if loan_amount_usd > 0 else 0
        
        # CRITICAL: Slippage percentage must be calculated on ACTUAL amounts, not loan
        # Leg1 slippage is on loan_amount_usd base
        # Leg2 slippage is on leg1_amount_out_usd base (different base!)
        # (Note: per-leg pct values currently used only in display below.)
        
        # For display: convert total slippage to percentage of loan (approximation)
        total_slippage_pct_display = (Decimal(str(total_slippage_usd)) / loan_amount_usd) * 100 if loan_amount_usd > 0 else 0
        
        logger.info("=" * 80)
        logger.info("💰 PROFIT CALCULATION (USD-Based Math)")
        logger.info("=" * 80)
        logger.info(f"Flash Loan Amount:        ${loan_amount_usd:,.2f}")
        logger.info(f"Flash Loan Provider:      {primary_provider}")
        logger.info("")
        logger.info("USD FLOW (Actual Amounts):")
        logger.info(f"  1️⃣  Start:               ${loan_amount_usd:,.2f}")
        logger.info(f"  2️⃣  After Leg1:           ${float(leg1_amount_out_usd):,.2f}")
        logger.info(f"      ├─ Fee paid:         -${leg1_fee_usd:,.2f}")
        logger.info(f"      └─ Slippage cost:    -${float(leg1_slippage_usd_ml):,.2f}")
        logger.info(f"  3️⃣  After Leg2:           ${float(leg2_amount_out_usd):,.2f}")
        logger.info(f"      ├─ Fee paid:         -${leg2_fee_usd:,.2f}")
        logger.info(f"      └─ Slippage cost:    -${float(leg2_slippage_usd_ml):,.2f}")
        logger.info(f"  4️⃣  Flash loan fee:      -${flash_loan_fee_usd:,.2f}")
        logger.info(f"  5️⃣  Net returned:         ${float(leg2_amount_out_usd - flash_loan_fee_usd):,.2f}")
        logger.info("")
        logger.info("COSTS BREAKDOWN (USD):")
        logger.info(f"  Flash Loan Fee:      ${flash_loan_fee_usd:,.2f}  ({flash_loan_fee_pct:.4f}% of loan)")
        logger.info(f"  DEX Fees (STATIC):   ${total_dex_fees_usd:,.2f}  ({total_dex_fees_pct:.4f}% of loan)")
        logger.info(f"  Slippage (ML):       ${total_slippage_usd:,.2f}  ({total_slippage_pct_display:.4f}% of loan)")
        logger.info("  ─────────────────────────────────")
        logger.info(f"  TOTAL COSTS:         ${float(total_costs_usd):,.2f}")
        logger.info(f"  Gas (paid separate): ${gas_cost_usd:,.4f} (Buffered to ${buffered_gas_cost_usd:,.4f})")
        logger.info("")
        logger.info("PROFIT (USD):")
        logger.info(f"  Gross Profit:        ${gross_profit_usd:,.2f}")
        logger.info(f"  Net Profit (pre-gas):${net_profit_usd:,.2f}")
        logger.info(f"  Net Profit (after gas): ${net_profit_after_gas_usd:,.2f}")
        logger.info(f"  ROI:                 {roi_percent:.4f}%")
        logger.info("")
        logger.info("⚠️  NOTE: Percentages shown are for reference only.")
        logger.info("    All calculations use USD amounts (different bases can't be added as %)!")
        logger.info("=" * 80)
        
        # SANITY GATE: Ensure we aren't proposing a losing trade before creating the object.
        # This check uses the buffered gas cost for maximum safety.
        if net_profit_after_gas_usd <= Decimal(str(get_minimum_net_profit_usd())):
            logger.warning(f"Opportunity rejected by sanity gate: Net profit ${net_profit_after_gas_usd:,.2f} <= min profit ${get_minimum_net_profit_usd():.2f}")
            return None

        # Build legs (using ML slippage for real-world accuracy)
        leg1 = SwapLeg(
            pool=buy_pool.pool_address,
            dex=buy_pool.dex_name,
            dex_id=buy_pool.dex_id,
            protocol=buy_pool.protocol,
            token_in=buy_pool.token0,
            token_out=buy_pool.token1,
            amount_in_usd=float(loan_amount_usd),
            amount_out_usd=float(leg1_amount_out_usd),
            fee_paid_usd=leg1_fee_usd,
            slippage_usd=leg1_slippage_usd_ml,  # ✅ Using ML prediction (real-world)
            spot_price=buy_price,
            effective_price=leg1_result.effective_price,
            token_in_decimals=buy_pool.token0_decimals,
            token_out_decimals=buy_pool.token1_decimals,
            token_in_price_usd=token0_price_usd,
            token_out_price_usd=token1_price_usd,
            fee=buy_pool.fee, # Use the specific pool's fee tier
        )

        leg2 = SwapLeg(
            pool=sell_pool.pool_address,
            dex=sell_pool.dex_name,
            dex_id=sell_pool.dex_id,
            protocol=sell_pool.protocol,
            token_in=sell_pool.token1,
            token_out=sell_pool.token0,
            amount_in_usd=float(leg1_amount_out_usd),
            amount_out_usd=float(leg2_amount_out_usd),
            fee_paid_usd=leg2_fee_usd,
            slippage_usd=leg2_slippage_usd_ml,  # ✅ Using ML prediction (real-world)
            spot_price=sell_price,
            effective_price=leg2_result.effective_price,
            token_in_decimals=sell_pool.token1_decimals,
            token_out_decimals=sell_pool.token0_decimals,
            token_in_price_usd=token1_price_usd,
            token_out_price_usd=token0_price_usd,
            fee=sell_pool.fee, # Use the specific pool's fee tier
        )
        
        flash_loan = FlashLoanData(
            loan_amount_usd=float(loan_amount_usd),
            flash_loan_fee_bps=flash_loan_fee_bps,
            flash_loan_fee_usd=float(flash_loan_fee_usd),
            leg1=leg1,
            leg2=leg2,
            total_fees_usd=float(leg1_fee_usd + leg2_fee_usd + flash_loan_fee_usd),
            total_slippage_usd=float(leg1.slippage_usd + leg2.slippage_usd),
            gas_cost_usd=float(gas_cost_usd),
            gas_units=self.gas_units,
            repay_amount_usd=float(loan_amount_usd + flash_loan_fee_usd),
            net_profit_usd=float(net_profit_usd),
            net_profit_after_gas_usd=float(net_profit_after_gas_usd),
            roi_percent=float(roi_percent),
            is_executable=is_executable,
            hops=2,
            # Multi-provider details
            flash_loan_provider=primary_provider,
            balancer_profit_usd=float(balancer_profit),
            aave_profit_usd=float(aave_profit),
            dual_execution=dual_execution,
            total_extraction_usd=float(effective_total_extraction_usd),
        )
        
        # Get token pair name
        t0_info = self.get_token_info(buy_pool.token0)
        t1_info = self.get_token_info(buy_pool.token1)
        token_pair = f"{t0_info['symbol']}/{t1_info['symbol']}"
        
        return SpreadOpportunity(
            id=str(uuid.uuid4()),
            timestamp=int(time.time() * 1000),
            token_pair=token_pair,
            min_reserve_usd=v.min_reserve,
            flash_loan=flash_loan,
        )

    def attempt_execution(self, opportunity: SpreadOpportunity) -> Optional[str]:
        """
        Uses the TransactionBuilder to run an opportunity through all proof gates
        and prepare it for signing and broadcast.

        Args:
            opportunity: The SpreadOpportunity to execute.

        Returns:
            The raw signed transaction hex if successful, otherwise None.
        """
        logger.info(f"Attempting to build and execute opportunity {opportunity.id}")

        if not self.private_key or not self.wallet_address:
            logger.error("❌ Execution context not configured. Set PRIVATE_KEY and EXECUTOR_WALLET.")
            return None

        try:
            # 1. Instantiate the builder with the opportunity and execution context.
            builder = TransactionBuilder(opportunity, self.w3, self.wallet_address, self.private_key)

            # 2. Run all proof gates in a fluent chain.
            #    These gates act as the final line of defense before committing capital.
            builder.gate_wallet_readiness() \
                   .gate_rpc_liveness() \
                   .gate_contract_readiness() \
                   .gate_profitability() \
                   .gate_slippage_and_depth() \
                   .construct_payload() \
                   .simulate()

            # 3. Build the final transaction. This will raise an error if any gate failed.
            unsigned_tx = builder.build()
            logger.info(f"✅ All proof gates passed. Transaction built: {unsigned_tx}")

            # 4. Sign the transaction.
            signed_tx_hex = builder.get_signed_tx()
            logger.info(f"✍️ Transaction signed: {signed_tx_hex[:20]}...")

            # 5. In a real system, you would now broadcast the transaction.
            # tx_hash = self.w3.eth.send_raw_transaction(signed_tx_hex)
            # logger.info(f"🚀 Transaction broadcast! Hash: {tx_hash.hex()}")
            
            return signed_tx_hex

        except TransactionBuilderError as e:
            logger.error(f"❌ Execution stopped. {e.message}")
            for error in e.errors:
                logger.error(f"   - {error}")
            return None
        except Exception:
            logger.exception("An unexpected error occurred during transaction building.")
            return None

    def execute_best_opportunity(self) -> Optional[str]:
        """Finds the most profitable spread and attempts to execute it."""
        if not self.spreads:
            logger.info("No profitable spreads found to execute.")
            return None
        
        return self.attempt_execution(self.spreads[0])
    
    def update_pool(self, pool_data: Dict) -> PoolPrice:
        """Update pool data and return PoolPrice"""
        address = Web3.to_checksum_address(pool_data['poolAddress'])
        
        t0_info = self.get_token_info(pool_data['token0'])
        t1_info = self.get_token_info(pool_data['token1'])
        dex_name = self.get_dex_name(pool_data.get('dexId', 0))
        
        pool = PoolPrice(
            pool_address=address,
            dex_id=pool_data.get('dexId', 0),
            dex_name=dex_name,
            token0=pool_data['token0'],
            token1=pool_data['token1'],
            token0_symbol=t0_info['symbol'],
            token1_symbol=t1_info['symbol'],
            spot_price=pool_data.get('spotPrice', 0),
            reserve_usd=pool_data.get('reserveUsd', 0),
            protocol=pool_data.get('protocol', Protocol.V3),
            fee=pool_data.get('fee', 3000),
            liquidity=pool_data.get('liquidity', 0),
            tick=pool_data.get('tick', 0),
            sqrt_price_x96=pool_data.get('sqrtPriceX96', 0),
            last_updated=int(time.time()),
        )
        
        self.pools[address] = pool
        return pool
    
    def scan_for_spreads(self, loan_amount_usd: float = None, max_comparisons: int = 500) -> List[SpreadOpportunity]:
        """
        Scan all pools for spread opportunities with DYNAMIC OPTIMAL LOAN SIZING
        
        Args:
            loan_amount_usd: Optional fixed loan amount for testing/comparison
                           If None, calculates optimal loan for each pool pair
            max_comparisons: Maximum number of pool pair comparisons (prevents timeout)
        """
        # Wait for pools to finish loading if still in progress
        if self.pools_loading:
            logger.warning("⏳ Pools still loading with EXACT Web3 data, please wait...")
            return []
        
        if len(self.pools) == 0:
            logger.error("❌ No pools loaded - cannot scan for spreads")
            return []
        
        spreads = []
        comparisons = 0
        start_time = time.time()
        
        # Group pools by token pair
        pairs: Dict[frozenset, List[PoolPrice]] = {}
        for pool in self.pools.values():
            # Skip pools with very low TVL (< $1000) to reduce noise
            if pool.reserve_usd < 1000:
                continue
            pair = frozenset([pool.token0, pool.token1])
            if pair not in pairs:
                pairs[pair] = []
            pairs[pair].append(pool)
        
        logger.info(f"🔍 Scanning {len(pairs)} token pairs with EXACT on-chain data...")
        
        # Analyze spreads between pools of same pair
        pair_count = 0
        for pair, pools in pairs.items():
            if len(pools) < 2:
                continue
            
            pair_count += 1
            # Progress logging every 10 pairs
            if pair_count % 10 == 0:
                elapsed = time.time() - start_time
                logger.info(f"   Progress: {pair_count}/{len(pairs)} pairs, {comparisons} comparisons, {len(spreads)} opportunities, {elapsed:.1f}s")
            
            # Compare all combinations
            for i, pool1 in enumerate(pools):
                # Safety: Stop if we hit max comparisons GLOBALLY
                if comparisons >= max_comparisons:
                    logger.warning(f"⚠️ Reached max comparisons limit ({max_comparisons}). Stopping scan.")
                    break
                    
                for pool2 in pools[i+1:]:
                    comparisons += 1
                    
                    if comparisons >= max_comparisons:
                        break
                    
                    try:
                        if loan_amount_usd:
                            # FIXED LOAN MODE (for testing/comparison)
                            spread = self.analyze_spread(pool1, pool2, loan_amount_usd)
                            if spread:
                                decision = get_governance_service().evaluate_activation(
                                    opportunity_id=spread.id,
                                    stage="discovery_activation_fixed",
                                    net_profit_after_costs_usd=spread.flash_loan.net_profit_after_gas_usd,
                                    metadata={
                                        "pair": spread.token_pair,
                                        "loan_amount_usd": loan_amount_usd,
                                        "buy_pool": pool1.pool_address,
                                        "sell_pool": pool2.pool_address,
                                    },
                                )
                                if decision.accepted:
                                    spreads.append(spread)
                        else:
                            # DYNAMIC OPTIMAL LOAN SIZING MODE
                            optimal_loan, spread = self.find_optimal_loan_amount(pool1, pool2)
                            if spread and optimal_loan > 0:
                                decision = get_governance_service().evaluate_activation(
                                    opportunity_id=spread.id,
                                    stage="discovery_activation_dynamic",
                                    net_profit_after_costs_usd=spread.flash_loan.net_profit_after_gas_usd,
                                    metadata={
                                        "pair": spread.token_pair,
                                        "loan_amount_usd": optimal_loan,
                                        "buy_pool": pool1.pool_address,
                                        "sell_pool": pool2.pool_address,
                                    },
                                )
                                if decision.accepted:
                                    spreads.append(spread)
                    except Exception as e:
                        logger.debug(f"Error analyzing spread for {pool1.pool_address[:10]} vs {pool2.pool_address[:10]}: {e}")
                        continue
                
                # Break outer loop if max reached
                if comparisons >= max_comparisons:
                    break
        
        # Sort by profit
        spreads.sort(key=lambda s: s.flash_loan.net_profit_usd, reverse=True)
        self.spreads = spreads
        self.last_update = int(time.time() * 1000)
        
        elapsed_total = time.time() - start_time
        logger.info(f"✅ Scan complete: {len(spreads)} opportunities found from {comparisons} comparisons in {elapsed_total:.1f}s" + 
                   (" (dynamic optimal sizing)" if not loan_amount_usd else f" (fixed ${loan_amount_usd:,.0f} loans)"))
        
        return spreads
    
    def get_spreads(self) -> Dict:
        """Get current spreads in API format"""
        return {
            "timestamp": self.last_update,
            "spreads": [s.to_dict() for s in self.spreads],
        }
    
    def get_pool_prices(self) -> Dict:
        """Get current pool prices in API format"""
        return {
            "timestamp": self.last_update,
            "pools": [p.to_dict() for p in self.pools.values()],
        }


# Global engine instance
_engine: Optional[ArbitrageEngine] = None


def get_arbitrage_engine() -> ArbitrageEngine:
    """Get or create arbitrage engine instance"""
    global _engine
    if _engine is None:
        rpc_url = os.getenv('POLYGON_RPC_URL', '')
        _engine = ArbitrageEngine(rpc_url)
    return _engine


def get_spreads() -> Dict:
    """API helper: Get current spreads"""
    return get_arbitrage_engine().get_spreads()


def get_pool_prices() -> Dict:
    """API helper: Get current pool prices"""
    return get_arbitrage_engine().get_pool_prices()


def serialize_pool(pool: Any) -> Dict:
    """Serialize pool data for API"""
    return {
        "address": pool.get('address'),
        "dexId": pool.get('dexId'),
        "chainId": pool.get('chainId', 137),
        "token0": pool.get('token0'),
        "token1": pool.get('token1'),
        "fee": pool.get('fee'),
        "reserve0": str(pool.get('reserve0', 0)),
        "reserve1": str(pool.get('reserve1', 0)),
        "liquidity": str(pool.get('liquidity', 0)),
        "lastUpdated": pool.get('lastUpdated'),
        "isActive": pool.get('isActive', True),
    }


def serialize_price_data(price: Any) -> Dict:
    """Serialize price data for API"""
    return {
        "poolAddress": price.get('poolAddress'),
        "chainId": price.get('chainId', 137),
        "token0": price.get('token0'),
        "token1": price.get('token1'),
        "reserve0": str(price.get('reserve0', 0)),
        "reserve1": str(price.get('reserve1', 0)),
        "sqrtPriceX96": str(price.get('sqrtPriceX96', 0)),
        "tick": price.get('tick'),
        "liquidity": str(price.get('liquidity', 0)),
        "fee": price.get('fee'),
        "protocol": price.get('protocol'),
        "updatedAt": price.get('updatedAt'),
    }
