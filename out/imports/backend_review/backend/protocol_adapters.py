"""
UNIVERSAL PROTOCOL ADAPTER SYSTEM
Enables arbitrage calculation between ANY venue vs ANY venue

Supported Protocols:
- Uniswap V2 / QuickSwap V2 / SushiSwap (constant product xy=k)
- Uniswap V3 / QuickSwap V3 (concentrated liquidity, tick-based)
- Balancer V2 (weighted pools)
- Curve Finance (StableSwap with amplification)

Key Innovation: Protocol-agnostic interface allows V2↔V3, V3↔Balancer, Curve↔V2, etc.
"""

import math
from typing import Protocol, Dict, Optional, Tuple, Any, List
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ProtocolType(Enum):
    """Supported AMM protocol types"""
    V2 = "v2"  # Constant product xy=k
    V3 = "v3"  # Concentrated liquidity
    BALANCER = "balancer"  # Weighted pools
    CURVE = "curve"  # StableSwap
    UNKNOWN = "unknown"


@dataclass
class SwapResult:
    """Universal swap result across all protocols"""
    amount_out: float
    price_impact_bps: float
    effective_price: float
    slippage_bps: float
    gas_estimate: int
    protocol: ProtocolType
    
    def to_dict(self) -> Dict:
        return {
            "amount_out": self.amount_out,
            "price_impact_bps": self.price_impact_bps,
            "effective_price": self.effective_price,
            "slippage_bps": self.slippage_bps,
            "gas_estimate": self.gas_estimate,
            "protocol": self.protocol.value
        }


class ProtocolAdapter(Protocol):
    """
    Abstract interface that ALL protocol adapters must implement
    This enables ANY venue vs ANY venue arbitrage
    """
    
    def calculate_output(
        self,
        amount_in: float,
        pool: Dict,
        zero_for_one: bool = True
    ) -> SwapResult:
        """
        Calculate swap output for ANY protocol
        
        Args:
            amount_in: Input amount (normalized units)
            pool: Pool data (protocol-specific fields)
            zero_for_one: True = token0→token1, False = token1→token0
            
        Returns:
            SwapResult with output amount and metrics
        """
        ...
    
    def get_spot_price(self, pool: Dict, zero_for_one: bool = True) -> float:
        """Get current spot price (no slippage)"""
        ...
    
    def get_depth_score(self, pool: Dict) -> float:
        """Calculate pool depth score for quality filtering"""
        ...
    
    def get_max_tradeable(self, pool: Dict, max_slippage_bps: float = 40) -> float:
        """Get maximum tradeable amount before hitting slippage limit"""
        ...


class V2Adapter:
    """
    Uniswap V2 / QuickSwap V2 / SushiSwap Adapter
    Constant product: xy = k
    """
    
    protocol_type = ProtocolType.V2
    
    def calculate_output(
        self,
        amount_in: float,
        pool: Dict,
        zero_for_one: bool = True
    ) -> SwapResult:
        """
        V2 swap calculation: y_out = (x_in * y) / (x + x_in * (1 - fee))
        """
        
        # Extract pool data
        reserve_in = pool['reserve0'] if zero_for_one else pool['reserve1']
        reserve_out = pool['reserve1'] if zero_for_one else pool['reserve0']
        fee_bps = pool.get('fee_bps', 30)  # Default 0.3%
        
        # Validation
        if reserve_in <= 0 or reserve_out <= 0:
            return SwapResult(0, 0, 0, 0, 100_000, self.protocol_type)
        
        # Apply fee
        fee_decimal = fee_bps / 10_000
        amount_in_after_fee = amount_in * (1 - fee_decimal)
        
        # Constant product formula
        amount_out = (amount_in_after_fee * reserve_out) / (reserve_in + amount_in_after_fee)
        
        # Calculate metrics
        spot_price = reserve_out / reserve_in if reserve_in > 0 else 0
        effective_price = amount_out / amount_in if amount_in > 0 else 0
        price_impact_bps = abs(1 - effective_price / spot_price) * 10_000 if spot_price > 0 else 0
        
        # Slippage = price impact for V2 (embedded in AMM math)
        slippage_bps = price_impact_bps
        
        return SwapResult(
            amount_out=amount_out,
            price_impact_bps=price_impact_bps,
            effective_price=effective_price,
            slippage_bps=slippage_bps,
            gas_estimate=100_000,  # V2 swap gas
            protocol=self.protocol_type
        )
    
    def get_spot_price(self, pool: Dict, zero_for_one: bool = True) -> float:
        """V2 spot price = reserve_out / reserve_in"""
        reserve_in = pool['reserve0'] if zero_for_one else pool['reserve1']
        reserve_out = pool['reserve1'] if zero_for_one else pool['reserve0']
        return reserve_out / reserve_in if reserve_in > 0 else 0
    
    def get_depth_score(self, pool: Dict) -> float:
        """
        V2 depth = sqrt(reserve0 * reserve1) * (1 - fee)
        """
        reserve0 = pool.get('reserve0', 0)
        reserve1 = pool.get('reserve1', 0)
        fee_bps = pool.get('fee_bps', 30)
        fee_decimal = fee_bps / 10_000
        
        if reserve0 <= 0 or reserve1 <= 0:
            return 0
        
        return math.sqrt(reserve0 * reserve1) * (1 - fee_decimal)
    
    def get_max_tradeable(self, pool: Dict, max_slippage_bps: float = 40) -> float:
        """
        V2 max tradeable: solve for amount_in where price_impact = max_slippage
        """
        reserve_in = pool.get('reserve0', 0)
        reserve_out = pool.get('reserve1', 0)
        fee_bps = pool.get('fee_bps', 30)
        
        if reserve_in <= 0 or reserve_out <= 0:
            return 0
        
        # Approximate: max_amount ≈ reserve_in * (max_slippage / 10000)
        # This is a simplification; exact formula is more complex
        max_slippage_decimal = max_slippage_bps / 10_000
        max_amount = reserve_in * max_slippage_decimal * 0.5  # Conservative
        
        return max_amount


class V3Adapter:
    """
    Uniswap V3 / QuickSwap V3 Adapter
    Concentrated liquidity with tick-based pricing
    """
    
    protocol_type = ProtocolType.V3
    
    def calculate_output(
        self,
        amount_in: float,
        pool: Dict,
        zero_for_one: bool = True
    ) -> SwapResult:
        """
        V3 swap calculation using tick math
        
        Simplified implementation using virtual reserves
        Full implementation would walk ticks for large trades
        """
        
        # Extract V3-specific data
        sqrt_price_x96 = pool.get('sqrt_price_x96', 0)
        liquidity = pool.get('liquidity', 0)
        fee_bps = pool.get('fee_bps', 30)
        
        if sqrt_price_x96 <= 0 or liquidity <= 0:
            return SwapResult(0, 0, 0, 0, 150_000, self.protocol_type)
        
        # Calculate virtual reserves from sqrt_price and liquidity
        # sqrt_price = sqrt(reserve1 / reserve0)
        # L = sqrt(reserve0 * reserve1)
        
        sqrt_price = sqrt_price_x96 / (2**96)
        
        # Virtual reserves
        reserve0_virtual = liquidity / sqrt_price if sqrt_price > 0 else 0
        reserve1_virtual = liquidity * sqrt_price
        
        # Use V2-style calculation with virtual reserves
        # (This is an approximation; real V3 uses tick crossing)
        reserve_in = reserve0_virtual if zero_for_one else reserve1_virtual
        reserve_out = reserve1_virtual if zero_for_one else reserve0_virtual
        
        fee_decimal = fee_bps / 10_000
        amount_in_after_fee = amount_in * (1 - fee_decimal)
        
        # Constant product on virtual reserves
        amount_out = (amount_in_after_fee * reserve_out) / (reserve_in + amount_in_after_fee)
        
        # Calculate metrics
        spot_price = reserve_out / reserve_in if reserve_in > 0 else 0
        effective_price = amount_out / amount_in if amount_in > 0 else 0
        price_impact_bps = abs(1 - effective_price / spot_price) * 10_000 if spot_price > 0 else 0
        
        return SwapResult(
            amount_out=amount_out,
            price_impact_bps=price_impact_bps,
            effective_price=effective_price,
            slippage_bps=price_impact_bps,
            gas_estimate=150_000,  # V3 swap gas (higher than V2)
            protocol=self.protocol_type
        )
    
    def get_spot_price(self, pool: Dict, zero_for_one: bool = True) -> float:
        """
        V3 spot price from sqrtPriceX96
        price = (sqrtPriceX96 / 2^96)^2
        """
        sqrt_price_x96 = pool.get('sqrt_price_x96', 0)
        if sqrt_price_x96 <= 0:
            return 0
        
        sqrt_price = sqrt_price_x96 / (2**96)
        price = sqrt_price ** 2
        
        # If zero_for_one, we want reserve1/reserve0, which is price
        # If one_for_zero, we want reserve0/reserve1, which is 1/price
        return price if zero_for_one else (1 / price if price > 0 else 0)
    
    def get_depth_score(self, pool: Dict) -> float:
        """
        V3 depth = liquidity / sqrt(current_price)
        Higher liquidity = more depth
        """
        liquidity = pool.get('liquidity', 0)
        sqrt_price_x96 = pool.get('sqrt_price_x96', 0)
        
        if liquidity <= 0 or sqrt_price_x96 <= 0:
            return 0
        
        sqrt_price = sqrt_price_x96 / (2**96)
        
        # Normalize depth score to be comparable with V2
        # V3 liquidity is already sqrt(xy), so use directly
        depth = liquidity * 0.001  # Scale factor for comparability
        
        return depth
    
    def get_max_tradeable(self, pool: Dict, max_slippage_bps: float = 40) -> float:
        """V3 max tradeable (approximate using virtual reserves)"""
        liquidity = pool.get('liquidity', 0)
        sqrt_price_x96 = pool.get('sqrt_price_x96', 0)
        
        if liquidity <= 0 or sqrt_price_x96 <= 0:
            return 0
        
        sqrt_price = sqrt_price_x96 / (2**96)
        reserve0_virtual = liquidity / sqrt_price if sqrt_price > 0 else 0
        
        max_slippage_decimal = max_slippage_bps / 10_000
        max_amount = reserve0_virtual * max_slippage_decimal * 0.3  # More conservative for V3
        
        return max_amount


class BalancerAdapter:
    """
    Balancer V2 Adapter
    Weighted pools: spotPrice = (balanceOut/weightOut) / (balanceIn/weightIn)
    """
    
    protocol_type = ProtocolType.BALANCER
    
    def calculate_output(
        self,
        amount_in: float,
        pool: Dict,
        zero_for_one: bool = True
    ) -> SwapResult:
        """
        Balancer weighted pool swap
        Formula: amountOut = balanceOut * (1 - (balanceIn / (balanceIn + amountIn * (1-fee)))^(weightIn/weightOut))
        """
        
        # Extract Balancer-specific data
        balance_in = pool.get('balance0' if zero_for_one else 'balance1', 0)
        balance_out = pool.get('balance1' if zero_for_one else 'balance0', 0)
        weight_in = pool.get('weight0' if zero_for_one else 'weight1', 0.5)
        weight_out = pool.get('weight1' if zero_for_one else 'weight0', 0.5)
        fee_bps = pool.get('fee_bps', 30)
        
        if balance_in <= 0 or balance_out <= 0:
            return SwapResult(0, 0, 0, 0, 120_000, self.protocol_type)
        
        # Apply fee
        fee_decimal = fee_bps / 10_000
        amount_in_after_fee = amount_in * (1 - fee_decimal)
        
        # Balancer formula
        try:
            base = balance_in / (balance_in + amount_in_after_fee)
            exponent = weight_in / weight_out if weight_out > 0 else 1
            amount_out = balance_out * (1 - math.pow(base, exponent))
        except (ValueError, ZeroDivisionError, OverflowError):
            return SwapResult(0, 0, 0, 0, 120_000, self.protocol_type)
        
        # Calculate metrics
        spot_price = (balance_out / weight_out) / (balance_in / weight_in) if weight_in > 0 and weight_out > 0 else 0
        effective_price = amount_out / amount_in if amount_in > 0 else 0
        price_impact_bps = abs(1 - effective_price / spot_price) * 10_000 if spot_price > 0 else 0
        
        return SwapResult(
            amount_out=amount_out,
            price_impact_bps=price_impact_bps,
            effective_price=effective_price,
            slippage_bps=price_impact_bps,
            gas_estimate=120_000,
            protocol=self.protocol_type
        )
    
    def get_spot_price(self, pool: Dict, zero_for_one: bool = True) -> float:
        """Balancer spot price = (balanceOut/weightOut) / (balanceIn/weightIn)"""
        balance_in = pool.get('balance0' if zero_for_one else 'balance1', 0)
        balance_out = pool.get('balance1' if zero_for_one else 'balance0', 0)
        weight_in = pool.get('weight0' if zero_for_one else 'weight1', 0.5)
        weight_out = pool.get('weight1' if zero_for_one else 'weight0', 0.5)
        
        if balance_in <= 0 or balance_out <= 0 or weight_in <= 0 or weight_out <= 0:
            return 0
        
        return (balance_out / weight_out) / (balance_in / weight_in)
    
    def get_depth_score(self, pool: Dict) -> float:
        """Balancer depth = sqrt(balance0 * balance1) * (1 - fee)"""
        balance0 = pool.get('balance0', 0)
        balance1 = pool.get('balance1', 0)
        fee_bps = pool.get('fee_bps', 30)
        
        if balance0 <= 0 or balance1 <= 0:
            return 0
        
        fee_decimal = fee_bps / 10_000
        return math.sqrt(balance0 * balance1) * (1 - fee_decimal)
    
    def get_max_tradeable(self, pool: Dict, max_slippage_bps: float = 40) -> float:
        """Balancer max tradeable (approximate)"""
        balance_in = pool.get('balance0', 0)
        max_slippage_decimal = max_slippage_bps / 10_000
        return balance_in * max_slippage_decimal * 0.4


class CurveAdapter:
    """
    Curve Finance Adapter
    StableSwap with amplification coefficient
    """
    
    protocol_type = ProtocolType.CURVE
    
    def calculate_output(
        self,
        amount_in: float,
        pool: Dict,
        zero_for_one: bool = True
    ) -> SwapResult:
        """
        Curve StableSwap calculation (simplified)
        Full implementation uses Newton iteration for D and y
        """
        
        # Extract Curve-specific data
        balance_in = pool.get('balance0' if zero_for_one else 'balance1', 0)
        balance_out = pool.get('balance1' if zero_for_one else 'balance0', 0)
        amplification = pool.get('A', 2000)  # Default A=2000
        fee_bps = pool.get('fee_bps', 1)  # Curve typically 0.01%
        
        if balance_in <= 0 or balance_out <= 0:
            return SwapResult(0, 0, 0, 0, 180_000, self.protocol_type)
        
        # Simplified Curve calculation (uses constant product as approximation)
        # Real implementation would use _curve_get_dy from your SSOT
        
        fee_decimal = fee_bps / 10_000
        amount_in_after_fee = amount_in * (1 - fee_decimal)
        
        # For stable pairs, use near-constant sum approximation
        # dy ≈ dx * (1 - small_slippage)
        # This is very rough - real Curve uses iterative Newton method
        
        # Price impact is minimal for stables
        price_impact_decimal = (amount_in_after_fee / balance_in) * 0.01  # Very small
        amount_out = amount_in_after_fee * (1 - price_impact_decimal)
        
        price_impact_bps = price_impact_decimal * 10_000
        
        return SwapResult(
            amount_out=amount_out,
            price_impact_bps=price_impact_bps,
            effective_price=amount_out / amount_in if amount_in > 0 else 1.0,
            slippage_bps=price_impact_bps,
            gas_estimate=180_000,  # Curve is more gas-intensive
            protocol=self.protocol_type
        )
    
    def get_spot_price(self, pool: Dict, zero_for_one: bool = True) -> float:
        """Curve spot price ≈ 1.0 for stable pairs"""
        # For stablecoin pairs, price should be very close to 1.0
        # Could calculate exact price using Curve math, but approximation works
        return 1.0
    
    def get_depth_score(self, pool: Dict) -> float:
        """Curve depth = sum(balances) * (1 - fee)"""
        balance0 = pool.get('balance0', 0)
        balance1 = pool.get('balance1', 0)
        fee_bps = pool.get('fee_bps', 1)
        
        fee_decimal = fee_bps / 10_000
        return (balance0 + balance1) * (1 - fee_decimal)
    
    def get_max_tradeable(self, pool: Dict, max_slippage_bps: float = 40) -> float:
        """Curve max tradeable (very high for stable pairs)"""
        balance_in = pool.get('balance0', 0)
        # Curve can handle large trades with minimal slippage
        return balance_in * 0.5  # Up to 50% of pool




# ============================================================================
# EXECUTION ENCODING ADAPTERS
# ============================================================================

ZERO_ADDRESS = "0x" + "0" * 40
POLYGON_EXECUTOR_ADDRESS = "0xa75f6372eee406Ab17dC957FA8FCB49cFaE0a33f"

# Polygon routers used by the deployed InstitutionalExecutor. These are kept
# here so both execution builders resolve venue/protocol combinations through a
# single fail-closed adapter registry instead of embedding fallbacks.
POLYGON_ROUTERS: Dict[str, str] = {
    "uniswap_v3": "0xE592427A0AEce92De3Edee1F18E0157C05861564",
    "quickswap_v2": "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff",
    "sushi_v2": "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506",
    "quickswap_algebra_v3": "0xf5b509bB0909a69B1c207E495f687a596C168E12",
    "balancer_vault": "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
}

# Minimal chain router map for the generic payload builder. Unknown combinations
# intentionally raise instead of falling back to a different protocol.
CHAIN_ROUTERS: Dict[int, Dict[str, str]] = {
    137: POLYGON_ROUTERS,
    1: {
        "uniswap_v3": "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
        "sushi_v2": "0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F",
        "balancer_vault": "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
    },
    42161: {
        "uniswap_v3": "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
        "sushi_v2": "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506",
        "balancer_vault": "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
    },
}


def _selector(signature: str) -> bytes:
    from web3 import Web3

    return Web3.keccak(text=signature)[:4]


@dataclass(frozen=True)
class SwapEncodingContext:
    chain_id: int
    dex: str
    protocol: Any
    pool: str
    token_in: str
    token_out: str
    amount_in: int
    amount_out_min: int
    recipient: str
    deadline: int
    pool_meta: Dict[str, Any]


@dataclass(frozen=True)
class EncodedSwap:
    router: str
    calldata: bytes
    adapter: str
    protocol: str
    fee_tier: Optional[int] = None
    tick_spacing: Optional[int] = None

    @property
    def calldata_hex(self) -> str:
        return "0x" + self.calldata.hex()


class SwapEncodingAdapter(Protocol):
    adapter_name: str

    def supports(self, dex: str, protocol: Any) -> bool:
        ...

    def encode(self, ctx: SwapEncodingContext) -> EncodedSwap:
        ...


class BaseSwapEncodingAdapter:
    adapter_name = "base"

    @staticmethod
    def _checksum(address: str) -> str:
        from web3 import Web3

        return Web3.to_checksum_address(address)

    @staticmethod
    def _router(chain_id: int, key: str) -> str:
        router = CHAIN_ROUTERS.get(chain_id, {}).get(key)
        if not router:
            raise ValueError(f"No router configured for chain={chain_id} venue={key}")
        return router

    @staticmethod
    def _meta_int(meta: Dict[str, Any], keys: List[str]) -> Optional[int]:
        for key in keys:
            value = meta.get(key)
            if value is None:
                continue
            return int(value)
        return None


class V2SwapEncodingAdapter(BaseSwapEncodingAdapter):
    router_key = ""
    adapter_name = "v2"

    def supports(self, dex: str, protocol: Any) -> bool:
        return False

    def encode(self, ctx: SwapEncodingContext) -> EncodedSwap:
        from eth_abi import encode

        router = self._router(ctx.chain_id, self.router_key)
        path = [self._checksum(ctx.token_in), self._checksum(ctx.token_out)]
        calldata = _selector("swapExactTokensForTokens(uint256,uint256,address[],address,uint256)") + encode(
            ["uint256", "uint256", "address[]", "address", "uint256"],
            [ctx.amount_in, ctx.amount_out_min, path, self._checksum(ctx.recipient), ctx.deadline],
        )
        return EncodedSwap(router=router, calldata=calldata, adapter=self.adapter_name, protocol="v2")


class QuickSwapV2EncodingAdapter(V2SwapEncodingAdapter):
    router_key = "quickswap_v2"
    adapter_name = "quickswap_v2"

    def supports(self, dex: str, protocol: Any) -> bool:
        return "quick" in dex.lower() and _protocol_number(protocol) == 2


class SushiV2EncodingAdapter(V2SwapEncodingAdapter):
    router_key = "sushi_v2"
    adapter_name = "sushi_v2"

    def supports(self, dex: str, protocol: Any) -> bool:
        dex_l = dex.lower()
        return ("sushi" in dex_l or "sushiswap" in dex_l) and _protocol_number(protocol) == 2


class UniswapV3EncodingAdapter(BaseSwapEncodingAdapter):
    adapter_name = "uniswap_v3"

    def supports(self, dex: str, protocol: Any) -> bool:
        return "uniswap" in dex.lower() and _protocol_number(protocol) == 3

    def encode(self, ctx: SwapEncodingContext) -> EncodedSwap:
        from eth_abi import encode

        fee_tier = resolve_fee_tier(ctx.pool_meta)
        router = self._router(ctx.chain_id, "uniswap_v3")
        params = (
            self._checksum(ctx.token_in),
            self._checksum(ctx.token_out),
            fee_tier,
            self._checksum(ctx.recipient),
            ctx.deadline,
            ctx.amount_in,
            ctx.amount_out_min,
            0,
        )
        calldata = _selector("exactInputSingle((address,address,uint24,address,uint256,uint256,uint256,uint160))") + encode(
            ["(address,address,uint24,address,uint256,uint256,uint256,uint160)"],
            [params],
        )
        return EncodedSwap(
            router=router,
            calldata=calldata,
            adapter=self.adapter_name,
            protocol="v3",
            fee_tier=fee_tier,
            tick_spacing=resolve_tick_spacing(ctx.pool_meta, fee_tier),
        )


class QuickSwapAlgebraV3EncodingAdapter(BaseSwapEncodingAdapter):
    adapter_name = "quickswap_algebra_v3"

    def supports(self, dex: str, protocol: Any) -> bool:
        dex_l = dex.lower()
        return ("quick" in dex_l or "algebra" in dex_l) and _protocol_number(protocol) == 3

    def encode(self, ctx: SwapEncodingContext) -> EncodedSwap:
        from eth_abi import encode

        tick_spacing = require_tick_spacing(ctx.pool_meta)
        router = self._router(ctx.chain_id, "quickswap_algebra_v3")
        params = (
            self._checksum(ctx.token_in),
            self._checksum(ctx.token_out),
            self._checksum(ctx.recipient),
            ctx.deadline,
            ctx.amount_in,
            ctx.amount_out_min,
            0,
        )
        calldata = _selector("exactInputSingle((address,address,address,uint256,uint256,uint256,uint160))") + encode(
            ["(address,address,address,uint256,uint256,uint256,uint160)"],
            [params],
        )
        return EncodedSwap(
            router=router,
            calldata=calldata,
            adapter=self.adapter_name,
            protocol="algebra_v3",
            tick_spacing=tick_spacing,
        )


class CurveEncodingAdapter(BaseSwapEncodingAdapter):
    adapter_name = "curve"

    def supports(self, dex: str, protocol: Any) -> bool:
        p = str(protocol).lower()
        return "curve" in dex.lower() or "curve" in p

    def encode(self, ctx: SwapEncodingContext) -> EncodedSwap:
        from eth_abi import encode

        if not ctx.pool:
            raise ValueError("Curve pool address is required")
        i, j = resolve_curve_indices(ctx.token_in, ctx.token_out, ctx.pool_meta)
        calldata = _selector("exchange(int128,int128,uint256,uint256)") + encode(
            ["int128", "int128", "uint256", "uint256"],
            [i, j, ctx.amount_in, ctx.amount_out_min],
        )
        return EncodedSwap(router=self._checksum(ctx.pool), calldata=calldata, adapter=self.adapter_name, protocol="curve")


class BalancerEncodingAdapter(BaseSwapEncodingAdapter):
    adapter_name = "balancer"

    def supports(self, dex: str, protocol: Any) -> bool:
        p = str(protocol).lower()
        return "balancer" in dex.lower() or "balancer" in p

    def encode(self, ctx: SwapEncodingContext) -> EncodedSwap:
        from eth_abi import encode

        pool_id = ctx.pool_meta.get("pool_id")
        if not pool_id:
            raise ValueError("Balancer pool_id is required")
        pool_id_bytes = pool_id if isinstance(pool_id, bytes) else bytes.fromhex(str(pool_id).replace("0x", ""))
        if len(pool_id_bytes) != 32:
            raise ValueError("Balancer pool_id must be bytes32")
        vault = self._router(ctx.chain_id, "balancer_vault")
        single_swap = (pool_id_bytes, 0, self._checksum(ctx.token_in), self._checksum(ctx.token_out), ctx.amount_in, b"")
        funds = (POLYGON_EXECUTOR_ADDRESS if ctx.recipient.lower() == POLYGON_EXECUTOR_ADDRESS.lower() else self._checksum(ctx.recipient), False, self._checksum(ctx.recipient), False)
        calldata = _selector("swap((bytes32,uint8,address,address,uint256,bytes),(address,bool,address,bool),uint256,uint256)") + encode(
            ["(bytes32,uint8,address,address,uint256,bytes)", "(address,bool,address,bool)", "uint256", "uint256"],
            [single_swap, funds, ctx.amount_out_min, ctx.deadline],
        )
        return EncodedSwap(router=vault, calldata=calldata, adapter=self.adapter_name, protocol="balancer")


ENCODING_ADAPTERS: Tuple[SwapEncodingAdapter, ...] = (
    QuickSwapV2EncodingAdapter(),
    SushiV2EncodingAdapter(),
    UniswapV3EncodingAdapter(),
    QuickSwapAlgebraV3EncodingAdapter(),
    CurveEncodingAdapter(),
    BalancerEncodingAdapter(),
)


def _protocol_number(protocol: Any) -> Optional[int]:
    if protocol in (2, 3):
        return int(protocol)
    text = str(protocol).lower()
    if "v2" in text or text == "2":
        return 2
    if "v3" in text or "algebra" in text or text == "3":
        return 3
    return None


def resolve_fee_tier(pool_meta: Optional[Dict[str, Any]]) -> int:
    """Resolve a Uniswap V3 fee tier from pool-derived metadata only."""
    meta = pool_meta or {}
    for key in ("fee_tier", "fee", "feeTier"):
        value = meta.get(key)
        if value is not None:
            fee = int(value)
            if fee <= 0:
                raise ValueError("V3 fee tier must be positive")
            return fee
    fee_bps = meta.get("fee_bps")
    if fee_bps is not None:
        converted = int(fee_bps) * 100
        if converted > 0:
            return converted
    raise ValueError("Uniswap V3 fee tier is required in pool metadata")


def resolve_tick_spacing(pool_meta: Optional[Dict[str, Any]], fee_tier: Optional[int] = None) -> int:
    meta = pool_meta or {}
    for key in ("tick_spacing", "tickSpacing"):
        value = meta.get(key)
        if value is not None:
            spacing = int(value)
            if spacing <= 0:
                raise ValueError("tick spacing must be positive")
            return spacing
    if fee_tier is not None:
        canonical = {100: 1, 500: 10, 3000: 60, 10000: 200}
        if fee_tier in canonical:
            return canonical[fee_tier]
    raise ValueError("V3 tick spacing is required in pool metadata")


def require_tick_spacing(pool_meta: Optional[Dict[str, Any]]) -> int:
    return resolve_tick_spacing(pool_meta, None)


def resolve_curve_indices(token_in: str, token_out: str, pool_meta: Optional[Dict[str, Any]]) -> Tuple[int, int]:
    meta = pool_meta or {}
    if "i" in meta and "j" in meta:
        return int(meta["i"]), int(meta["j"])
    tokens = [t.lower() for t in meta.get("tokens", []) if isinstance(t, str)]
    if token_in.lower() in tokens and token_out.lower() in tokens:
        return tokens.index(token_in.lower()), tokens.index(token_out.lower())
    raise ValueError("Curve token indices are required in pool metadata")


def get_swap_encoding_adapter(dex: str, protocol: Any) -> SwapEncodingAdapter:
    for adapter in ENCODING_ADAPTERS:
        if adapter.supports(dex or "", protocol):
            return adapter
    raise ValueError(f"Unsupported DEX/protocol combination dex={dex!r} protocol={protocol!r}")


def encode_swap(ctx: SwapEncodingContext) -> EncodedSwap:
    return get_swap_encoding_adapter(ctx.dex, ctx.protocol).encode(ctx)


# Protocol Adapter Factory
class ProtocolAdapterFactory:
    """
    Factory to get the correct adapter for any pool
    Enables universal cross-protocol arbitrage
    """
    
    _adapters = {
        ProtocolType.V2: V2Adapter(),
        ProtocolType.V3: V3Adapter(),
        ProtocolType.BALANCER: BalancerAdapter(),
        ProtocolType.CURVE: CurveAdapter(),
    }
    
    @classmethod
    def get_adapter(cls, pool: Dict) -> Optional[ProtocolAdapter]:
        """
        Get correct adapter for pool based on protocol type
        
        Args:
            pool: Pool data with 'protocol' field
            
        Returns:
            Appropriate ProtocolAdapter instance
        """
        protocol_str = pool.get('protocol', '').lower()
        
        # Map protocol strings to types
        if protocol_str in ['v2', 'uniswap_v2', 'quickswap_v2', 'sushiswap']:
            protocol_type = ProtocolType.V2
        elif protocol_str in ['v3', 'uniswap_v3', 'quickswap_v3']:
            protocol_type = ProtocolType.V3
        elif protocol_str in ['balancer', 'balancer_v2']:
            protocol_type = ProtocolType.BALANCER
        elif protocol_str in ['curve', 'curve_stable']:
            protocol_type = ProtocolType.CURVE
        else:
            logger.warning(f"Unknown protocol: {protocol_str}; refusing to select an adapter")
            return None
        
        return cls._adapters.get(protocol_type)
    
    @classmethod
    def detect_protocol(cls, pool: Dict) -> ProtocolType:
        """Detect protocol type from pool data"""
        protocol_str = pool.get('protocol', '').lower()
        
        # Check for V3-specific fields
        if 'sqrt_price_x96' in pool or 'tick' in pool or 'v3' in protocol_str:
            return ProtocolType.V3
        
        # Check for Balancer-specific fields
        if 'weights' in pool or 'weight0' in pool or 'balancer' in protocol_str:
            return ProtocolType.BALANCER
        
        # Check for Curve-specific fields
        if 'A' in pool or 'amplification' in pool or 'curve' in protocol_str:
            return ProtocolType.CURVE
        
        return ProtocolType.UNKNOWN


# Convenience function
def calculate_cross_protocol_swap(
    amount_in: float,
    pool1: Dict,
    pool2: Dict,
    zero_for_one_1: bool = True,
    zero_for_one_2: bool = True
) -> Tuple[float, Dict]:
    """
    Calculate 2-leg arbitrage across ANY protocols
    
    Example: V2 → V3, V3 → Balancer, Curve → V2
    
    Returns:
        (final_amount_out, swap_details)
    """
    
    # Get adapters for each pool
    adapter1 = ProtocolAdapterFactory.get_adapter(pool1)
    adapter2 = ProtocolAdapterFactory.get_adapter(pool2)
    
    if not adapter1 or not adapter2:
        return 0, {"error": "Protocol adapter not found"}
    
    # Leg 1
    leg1_result = adapter1.calculate_output(amount_in, pool1, zero_for_one_1)
    
    # Leg 2 (uses output from leg 1)
    leg2_result = adapter2.calculate_output(leg1_result.amount_out, pool2, zero_for_one_2)
    
    # Calculate total profit
    gross_profit = leg2_result.amount_out - amount_in
    
    return leg2_result.amount_out, {
        "leg1": leg1_result.to_dict(),
        "leg2": leg2_result.to_dict(),
        "gross_profit": gross_profit,
        "protocol_combo": f"{leg1_result.protocol.value}→{leg2_result.protocol.value}"
    }
