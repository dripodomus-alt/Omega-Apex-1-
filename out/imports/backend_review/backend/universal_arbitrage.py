"""
UNIVERSAL CROSS-PROTOCOL ARBITRAGE CALCULATOR
Calculates arbitrage between ANY venue vs ANY venue

Supported combinations:
- V2 ↔ V2 (QuickSwap ↔ SushiSwap)
- V2 ↔ V3 (QuickSwap V2 ↔ Uniswap V3)
- V3 ↔ V3 (QuickSwap V3 ↔ Uniswap V3)
- V3 ↔ Balancer
- Balancer ↔ Curve
- Curve ↔ V2
- ANY ↔ ANY

Key Innovation: Protocol-agnostic optimization using numerical methods
"""

import math
import logging
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass

from protocol_adapters import (
    ProtocolAdapterFactory,
    ProtocolType,
    SwapResult,
    calculate_cross_protocol_swap
)

logger = logging.getLogger(__name__)


@dataclass
class UniversalArbitrageResult:
    """Result of universal arbitrage calculation"""
    optimal_input: float
    leg1_output: float
    leg2_output: float
    gross_profit: float
    net_profit: float
    roi_percent: float
    
    leg1_protocol: ProtocolType
    leg2_protocol: ProtocolType
    
    leg1_price_impact_bps: float
    leg2_price_impact_bps: float
    total_slippage_bps: float
    
    total_gas_estimate: int
    is_profitable: bool
    
    def to_dict(self) -> Dict:
        return {
            "optimal_input": self.optimal_input,
            "leg1_output": self.leg1_output,
            "leg2_output": self.leg2_output,
            "gross_profit": self.gross_profit,
            "net_profit": self.net_profit,
            "roi_percent": self.roi_percent,
            "protocol_path": f"{self.leg1_protocol.value}→{self.leg2_protocol.value}",
            "total_slippage_bps": self.total_slippage_bps,
            "total_gas": self.total_gas_estimate,
            "is_profitable": self.is_profitable
        }


class UniversalArbitrageCalculator:
    """
    Calculates arbitrage opportunities between ANY protocol combinations
    
    Uses numerical optimization since closed-form solutions only exist for V2↔V2
    """
    
    def __init__(self):
        self.adapter_factory = ProtocolAdapterFactory()
    
    def calculate_arbitrage(
        self,
        pool1: Dict,
        pool2: Dict,
        min_input: float = 100,
        max_input: float = 100_000,
        gas_cost_usd: float = 0.05,
        flash_fee_bps: float = 0,  # Balancer = 0%
        min_profit_usd: float = 5.0,
        optimize: bool = True
    ) -> Optional[UniversalArbitrageResult]:
        """
        Calculate arbitrage between any two pools
        
        Args:
            pool1: First pool (buy pool)
            pool2: Second pool (sell pool)
            min_input: Minimum trade size
            max_input: Maximum trade size
            gas_cost_usd: Estimated gas cost
            flash_fee_bps: Flash loan fee (0 for Balancer)
            min_profit_usd: Minimum profit threshold
            optimize: If True, find optimal size; if False, use max_input
            
        Returns:
            UniversalArbitrageResult if profitable, None otherwise
        """
        
        # Get adapters
        adapter1 = self.adapter_factory.get_adapter(pool1)
        adapter2 = self.adapter_factory.get_adapter(pool2)
        
        if not adapter1 or not adapter2:
            logger.warning("Could not get adapters for pools")
            return None
        
        # Check basic profitability (spot prices)
        spot_price_1 = adapter1.get_spot_price(pool1, zero_for_one=True)
        spot_price_2 = adapter2.get_spot_price(pool2, zero_for_one=False)  # Reverse direction
        
        if spot_price_1 <= 0 or spot_price_2 <= 0:
            return None
        
        # Quick profitability check: price difference must exceed fees
        price_ratio = spot_price_2 / spot_price_1 if spot_price_1 > 0 else 0
        fee1_bps = pool1.get('fee_bps', 30)
        fee2_bps = pool2.get('fee_bps', 30)
        total_fee_bps = fee1_bps + fee2_bps + flash_fee_bps
        
        # Must have price difference > total fees for profitability
        required_ratio = 1 + (total_fee_bps / 10_000)
        if price_ratio < required_ratio:
            return None  # Not profitable even before slippage
        
        # Find optimal input size
        if optimize:
            optimal_input = self._find_optimal_input(
                pool1, pool2, adapter1, adapter2,
                min_input, max_input
            )
        else:
            optimal_input = max_input
        
        if optimal_input <= 0:
            return None
        
        # Calculate final swap at optimal size
        leg1_result = adapter1.calculate_output(optimal_input, pool1, zero_for_one=True)
        leg2_result = adapter2.calculate_output(leg1_result.amount_out, pool2, zero_for_one=False)
        
        # Calculate profits
        gross_profit = leg2_result.amount_out - optimal_input
        flash_fee_cost = optimal_input * (flash_fee_bps / 10_000)
        net_profit = gross_profit - flash_fee_cost - gas_cost_usd
        roi_percent = (net_profit / optimal_input * 100) if optimal_input > 0 else 0
        
        # Total slippage
        total_slippage_bps = leg1_result.slippage_bps + leg2_result.slippage_bps
        
        # Build result
        result = UniversalArbitrageResult(
            optimal_input=optimal_input,
            leg1_output=leg1_result.amount_out,
            leg2_output=leg2_result.amount_out,
            gross_profit=gross_profit,
            net_profit=net_profit,
            roi_percent=roi_percent,
            leg1_protocol=leg1_result.protocol,
            leg2_protocol=leg2_result.protocol,
            leg1_price_impact_bps=leg1_result.price_impact_bps,
            leg2_price_impact_bps=leg2_result.price_impact_bps,
            total_slippage_bps=total_slippage_bps,
            total_gas_estimate=leg1_result.gas_estimate + leg2_result.gas_estimate,
            is_profitable=(net_profit >= min_profit_usd)
        )
        
        return result if result.is_profitable else None
    
    def _find_optimal_input(
        self,
        pool1: Dict,
        pool2: Dict,
        adapter1,
        adapter2,
        min_input: float,
        max_input: float,
        num_points: int = 24
    ) -> float:
        """
        Find optimal input using grid search
        
        Since we support cross-protocol arbs (e.g., V2↔V3), we can't use
        closed-form Angeris-Chitra. Instead, use numerical optimization.
        
        Grid search is robust and fast enough for real-time use.
        """
        
        # Generate logarithmic grid (more points at smaller sizes)
        grid_points = [
            min_input * ((max_input / min_input) ** (i / (num_points - 1)))
            for i in range(num_points)
        ]
        
        best_input = min_input
        best_profit = -float('inf')
        
        for input_amount in grid_points:
            # Calculate 2-leg swap
            try:
                leg1_result = adapter1.calculate_output(input_amount, pool1, zero_for_one=True)
                if leg1_result.amount_out <= 0:
                    continue
                
                leg2_result = adapter2.calculate_output(leg1_result.amount_out, pool2, zero_for_one=False)
                if leg2_result.amount_out <= 0:
                    continue
                
                # Gross profit (before fees)
                gross_profit = leg2_result.amount_out - input_amount
                
                if gross_profit > best_profit:
                    best_profit = gross_profit
                    best_input = input_amount
                    
            except Exception as e:
                logger.debug(f"Grid point {input_amount} failed: {e}")
                continue
        
        return best_input if best_profit > 0 else 0
    
    def verify_profitability(
        self,
        pool1: Dict,
        pool2: Dict
    ) -> Tuple[bool, float]:
        """
        Quick two-direction profitability check.

        Correct arb economics: if you buy on the cheaper pool and sell on the
        more expensive pool, the gross multiplicative factor is
            r = max(spot1, spot2) / min(spot1, spot2)
        where both spots are taken in the SAME direction (zero_for_one=True
        on both pools, i.e. the "token1 per token0" rate).

        Profitable iff r > 1 + total_fees_bps/10_000.
        Identical pools => r = 1 (NOT profitable). Falls open on bad inputs.
        """
        adapter1 = self.adapter_factory.get_adapter(pool1)
        adapter2 = self.adapter_factory.get_adapter(pool2)

        if not adapter1 or not adapter2:
            return False, 0.0

        # Use SAME direction on both pools — the difference between the spot
        # prices reveals the arb opportunity (regardless of which side we buy).
        spot1 = adapter1.get_spot_price(pool1, zero_for_one=True)
        spot2 = adapter2.get_spot_price(pool2, zero_for_one=True)

        if spot1 <= 0 or spot2 <= 0:
            return False, 0.0

        lo, hi = min(spot1, spot2), max(spot1, spot2)
        if lo <= 0:
            return False, 0.0
        ratio = hi / lo  # >= 1.0 always, == 1.0 when pools price identically

        fee1_bps = pool1.get('fee_bps', 30)
        fee2_bps = pool2.get('fee_bps', 30)
        total_fee_bps = fee1_bps + fee2_bps
        required_ratio = 1.0 + (total_fee_bps / 10_000.0)

        return (ratio > required_ratio, ratio)


# Global instance
_calculator = None

def get_universal_calculator() -> UniversalArbitrageCalculator:
    """Get or create universal calculator singleton"""
    global _calculator
    if _calculator is None:
        _calculator = UniversalArbitrageCalculator()
    return _calculator


# Convenience function for direct use
def calculate_universal_arbitrage(
    pool1: Dict,
    pool2: Dict,
    **kwargs
) -> Optional[UniversalArbitrageResult]:
    """
    Calculate arbitrage between ANY two pools
    
    Example:
        result = calculate_universal_arbitrage(
            pool1={"protocol": "v2", "reserve0": 50000, "reserve1": 20, "fee_bps": 30},
            pool2={"protocol": "v3", "sqrt_price_x96": ..., "liquidity": ..., "fee_bps": 30},
            max_input=10000
        )
    """
    calculator = get_universal_calculator()
    return calculator.calculate_arbitrage(pool1, pool2, **kwargs)
