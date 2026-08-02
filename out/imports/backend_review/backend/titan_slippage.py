"""
TITAN V12.4 Slippage Engine - Python Bindings
Multi-Protocol Slippage Prediction & Execution
"""

import ctypes
import os
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass
from enum import IntEnum
import logging

logger = logging.getLogger(__name__)


class ProtocolType(IntEnum):
    """DEX Protocol Types"""
    UNISWAP_V2 = 0
    UNISWAP_V3 = 1
    CURVE = 2
    BALANCER = 3


@dataclass
class SlippageResult:
    """Result of slippage calculation"""
    protocol: str
    predicted_slippage_pct: float
    optimal_size_usd: float
    is_within_tolerance: bool


@dataclass
class ProfitCalculation:
    """Net profit after gas"""
    gross_profit_usd: float
    gas_cost_usd: float
    net_profit_usd: float
    is_profitable: bool
    profit_to_gas_ratio: float


class TitanSlippageEngine:
    """
    Python wrapper for TITAN V12.4 C Slippage Engine.
    Provides high-performance slippage calculations for multiple DEX protocols.
    """
    
    def __init__(self, lib_path: Optional[str] = None):
        self._lib = None
        self._use_native = False
        
        if lib_path is None:
            lib_path = Path(__file__).parent / "libslippage.so"
        
        try:
            if os.path.exists(lib_path):
                self._lib = ctypes.CDLL(str(lib_path))
                self._setup_functions()
                self._use_native = True
                logger.info("TITAN Slippage Engine: Native C library loaded")
            else:
                logger.warning("TITAN Slippage Engine: Using Python fallback (compile C lib for better performance)")
        except Exception as e:
            logger.warning(f"TITAN Slippage Engine: C library load failed ({e}), using Python fallback")
    
    def _setup_functions(self):
        """Setup C function signatures"""
        # Curve slippage
        self._lib.simulate_curve_slippage.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_double]
        self._lib.simulate_curve_slippage.restype = ctypes.c_double
        
        # Balancer slippage
        self._lib.simulate_weighted_slippage.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double]
        self._lib.simulate_weighted_slippage.restype = ctypes.c_double
        
        # V3 slippage
        self._lib.simulate_v3_slippage.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_double]
        self._lib.simulate_v3_slippage.restype = ctypes.c_double
        
        # V2 slippage
        self._lib.simulate_v2_slippage.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double]
        self._lib.simulate_v2_slippage.restype = ctypes.c_double
        
        # Optimal size
        self._lib.calculate_optimal_size.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_int]
        self._lib.calculate_optimal_size.restype = ctypes.c_double
        
        # Net profit
        self._lib.calculate_net_profit.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double]
        self._lib.calculate_net_profit.restype = ctypes.c_double
    
    # ============ SLIPPAGE CALCULATIONS ============
    
    def curve_slippage(self, amount_in: float, total_reserve: float, amp_factor: float = 100) -> float:
        """Calculate Curve StableSwap slippage"""
        if self._use_native:
            return self._lib.simulate_curve_slippage(amount_in, total_reserve, amp_factor)
        # Python fallback
        ratio = amount_in / total_reserve
        slip = (ratio ** 2 / (amp_factor / 100.0)) * 100.0
        return max(slip, 0.0001)
    
    def balancer_slippage(self, amount_in: float, reserve_in: float, weight_in: float = 0.5, weight_out: float = 0.5) -> float:
        """Calculate Balancer weighted pool slippage"""
        if self._use_native:
            return self._lib.simulate_weighted_slippage(amount_in, reserve_in, weight_in, weight_out)
        # Python fallback
        weight_ratio = weight_in / weight_out
        price_impact = 1.0 - pow((reserve_in / (reserve_in + amount_in)), weight_ratio)
        return price_impact * 100.0
    
    def v3_slippage(self, amount_in_usd: float, active_liquidity: float, fee_bps: float = 30) -> float:
        """Calculate Uniswap V3 concentrated liquidity slippage"""
        if self._use_native:
            return self._lib.simulate_v3_slippage(amount_in_usd, active_liquidity, fee_bps)
        # Python fallback
        fee = fee_bps / 10000.0
        amount_after_fee = amount_in_usd * (1.0 - fee)
        delta_sqrt_p = amount_after_fee / active_liquidity
        predicted_slip = delta_sqrt_p * 102.0
        return min(predicted_slip, 10.0)
    
    def v2_slippage(self, amount_in: float, reserve_in: float, reserve_out: float, fee_bps: float = 30) -> float:
        """Calculate Uniswap V2 constant product slippage"""
        if self._use_native:
            return self._lib.simulate_v2_slippage(amount_in, reserve_in, reserve_out, fee_bps)
        # Python fallback
        fee = fee_bps / 10000.0
        amount_with_fee = amount_in * (1.0 - fee)
        new_reserve_in = reserve_in + amount_with_fee
        k = reserve_in * reserve_out
        new_reserve_out = k / new_reserve_in
        amount_out = reserve_out - new_reserve_out
        expected_rate = reserve_out / reserve_in
        actual_rate = amount_out / amount_in
        slippage = ((expected_rate - actual_rate) / expected_rate) * 100.0
        return max(slippage, 0)
    
    # ============ OPTIMIZATION ============
    
    def optimal_trade_size(self, liquidity: float, max_slippage_pct: float, fee_bps: float, protocol: ProtocolType) -> float:
        """Calculate optimal trade size for given slippage tolerance"""
        if self._use_native:
            return self._lib.calculate_optimal_size(liquidity, max_slippage_pct, fee_bps, int(protocol))
        # Python fallback
        fee = fee_bps / 10000.0
        max_slip = max_slippage_pct / 100.0
        
        if protocol == ProtocolType.UNISWAP_V2:
            return liquidity * max_slip / (2.0 + max_slip)
        elif protocol == ProtocolType.UNISWAP_V3:
            return (max_slip * liquidity) / (102.0 * (1.0 - fee))
        elif protocol == ProtocolType.CURVE:
            return liquidity * (max_slip / 100.0) ** 0.5
        elif protocol == ProtocolType.BALANCER:
            return liquidity * (1.0 - (1.0 - max_slip) ** 2)
        else:
            return liquidity * 0.01
    
    # ============ PROFITABILITY ============
    
    def calculate_profit(
        self,
        gross_profit_usd: float,
        gas_price_gwei: float,
        gas_units: float,
        matic_price_usd: float,
        min_ratio: float = 1.1
    ) -> ProfitCalculation:
        """Calculate net profit after gas costs"""
        if self._use_native:
            net = self._lib.calculate_net_profit(gross_profit_usd, gas_price_gwei, gas_units, matic_price_usd)
        else:
            gas_cost_matic = (gas_price_gwei * gas_units) / 1e9
            gas_cost_usd = gas_cost_matic * matic_price_usd
            net = gross_profit_usd - gas_cost_usd
        
        gas_cost_matic = (gas_price_gwei * gas_units) / 1e9
        gas_cost_usd = gas_cost_matic * matic_price_usd
        ratio = gross_profit_usd / gas_cost_usd if gas_cost_usd > 0 else float('inf')
        
        return ProfitCalculation(
            gross_profit_usd=gross_profit_usd,
            gas_cost_usd=gas_cost_usd,
            net_profit_usd=net,
            is_profitable=net > 0 and ratio >= min_ratio,
            profit_to_gas_ratio=ratio
        )
    
    # ============ AGGREGATE ============
    
    def multi_hop_slippage(self, slippages: List[float]) -> float:
        """Calculate aggregate slippage for multi-hop routes"""
        total = 1.0
        for slip in slippages:
            total *= (1.0 - slip / 100.0)
        return (1.0 - total) * 100.0
    
    def analyze_opportunity(
        self,
        amount_usd: float,
        liquidity: float,
        fee_bps: float,
        protocol: ProtocolType,
        max_slippage_pct: float = 3.0
    ) -> SlippageResult:
        """Full opportunity analysis with slippage prediction"""
        # Initialize slip to prevent UnboundLocalError
        slip = 0.0
        
        # Calculate slippage based on protocol
        if protocol == ProtocolType.UNISWAP_V3:
            slip = self.v3_slippage(amount_usd, liquidity, fee_bps)
        elif protocol == ProtocolType.UNISWAP_V2:
            slip = self.v2_slippage(amount_usd, liquidity, liquidity, fee_bps)
        elif protocol == ProtocolType.CURVE:
            slip = self.curve_slippage(amount_usd, liquidity * 2)
        else:
            slip = self.balancer_slippage(amount_usd, liquidity)
        
        optimal = self.optimal_trade_size(liquidity, max_slippage_pct, fee_bps, protocol)
        
        return SlippageResult(
            protocol=protocol.name,
            predicted_slippage_pct=round(slip, 6),
            optimal_size_usd=round(optimal, 2),
            is_within_tolerance=slip <= max_slippage_pct
        )


# Global instance
titan_engine = TitanSlippageEngine()
