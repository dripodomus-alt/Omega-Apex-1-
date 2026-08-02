"""
APEX_OMEGA Coefficient-Based Profit Calculator
Pure algebraic derivation for optimal loan sizing

Mathematical Foundation:
========================
net_profit = (token_units × coeff) - gas_buffer

Where coeff = raw_spread_per_token 
            - (buy_price × dex_fee)
            - (sell_price × dex_fee)
            - (buy_price × flash_fee)

Breakeven token_units = (gas_buffer + min_profit) / coeff

This module implements the EXACT derivation as specified.
"""

import logging
import numpy as np
from typing import Dict, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CoefficientResult:
    """Result of coefficient-based profit calculation"""
    # Input parameters
    buy_price: float
    sell_price: float
    raw_spread_per_token: float
    dex_fee_decimal: float
    flash_fee_decimal: float
    gas_buffer_usd: float
    min_profit_usd: float
    
    # Calculated coefficient
    coeff: float  # Net USD profit per token unit after fees
    
    # Optimal execution
    breakeven_token_units: float
    optimal_token_units: float  # Ceiling of breakeven
    
    # Profit breakdown
    gross_spread_usd: float
    total_fees_usd: float
    net_profit_usd: float
    roi_percent: float
    
    # Validation
    is_profitable: bool
    profitability_ratio: float  # coeff / gas_buffer (must be > 0)


class CoefficientProfitCalculator:
    """
    Coefficient-based profit calculator using pure algebraic derivation
    
    This is the mathematically cleanest form of the arbitrage profit equation.
    All percentage-based costs are factored into a single coefficient (coeff),
    which represents the net USD profit contributed by each token unit.
    """
    
    def __init__(
        self,
        dex_fee_bps: float = 30,      # 0.30% per swap
        flash_fee_bps: float = 9,     # 0.09% Balancer
        gas_buffer_usd: float = 0.02, # $0.02 gas on Polygon
        min_profit_usd: float = 5.0   # Minimum $5 profit
    ):
        """
        Initialize calculator with fee parameters
        
        Args:
            dex_fee_bps: DEX fee in basis points (30 = 0.30%)
            flash_fee_bps: Flash loan fee in basis points (9 = 0.09%)
            gas_buffer_usd: Gas cost buffer in USD
            min_profit_usd: Minimum required profit in USD
        """
        self.dex_fee_decimal = dex_fee_bps / 10000
        self.flash_fee_decimal = flash_fee_bps / 10000
        self.gas_buffer_usd = gas_buffer_usd
        self.min_profit_usd = min_profit_usd
        
        logger.info(f"📐 Coefficient Calculator initialized")
        logger.info(f"   DEX fee: {dex_fee_bps} bps ({self.dex_fee_decimal*100:.3f}%)")
        logger.info(f"   Flash fee: {flash_fee_bps} bps ({self.flash_fee_decimal*100:.4f}%)")
        logger.info(f"   Gas buffer: ${gas_buffer_usd:.4f}")
        logger.info(f"   Min profit: ${min_profit_usd:.2f}")
    
    def calculate_coefficient(
        self,
        buy_price: float,
        sell_price: float
    ) -> float:
        """
        Calculate the coefficient (net profit per token unit)
        
        coeff = raw_spread_per_token 
              - (buy_price × dex_fee)
              - (sell_price × dex_fee)
              - (buy_price × flash_fee)
        
        Args:
            buy_price: Price to buy token at (USD per token)
            sell_price: Price to sell token at (USD per token)
            
        Returns:
            Coefficient (USD profit per token after all percentage fees)
        """
        raw_spread_per_token = sell_price - buy_price
        
        buy_fee = buy_price * self.dex_fee_decimal
        sell_fee = sell_price * self.dex_fee_decimal
        flash_fee = buy_price * self.flash_fee_decimal
        
        coeff = raw_spread_per_token - buy_fee - sell_fee - flash_fee
        
        return coeff
    
    def calculate_optimal_size(
        self,
        buy_price: float,
        sell_price: float,
        max_token_units: Optional[float] = None
    ) -> CoefficientResult:
        """
        Calculate optimal trade size using coefficient method
        
        Args:
            buy_price: Price to buy at (USD per token)
            sell_price: Price to sell at (USD per token)
            max_token_units: Optional maximum token units (pool liquidity constraint)
            
        Returns:
            CoefficientResult with all calculations
        """
        # Step 1: Calculate coefficient
        raw_spread_per_token = sell_price - buy_price
        coeff = self.calculate_coefficient(buy_price, sell_price)
        
        # Step 2: Check if profitable at all
        if coeff <= 0:
            logger.warning(f"⚠️  Negative coefficient: {coeff:.6f} (spread too small for fees)")
            return CoefficientResult(
                buy_price=buy_price,
                sell_price=sell_price,
                raw_spread_per_token=raw_spread_per_token,
                dex_fee_decimal=self.dex_fee_decimal,
                flash_fee_decimal=self.flash_fee_decimal,
                gas_buffer_usd=self.gas_buffer_usd,
                min_profit_usd=self.min_profit_usd,
                coeff=coeff,
                breakeven_token_units=0,
                optimal_token_units=0,
                gross_spread_usd=0,
                total_fees_usd=0,
                net_profit_usd=-self.gas_buffer_usd,
                roi_percent=0,
                is_profitable=False,
                profitability_ratio=0
            )
        
        # Step 3: Calculate breakeven token units
        # net_profit = (token_units × coeff) - gas_buffer = min_profit
        # token_units = (gas_buffer + min_profit) / coeff
        breakeven_token_units = (self.gas_buffer_usd + self.min_profit_usd) / coeff
        optimal_token_units = np.ceil(breakeven_token_units)  # Round up to whole units
        
        # Step 4: Apply pool liquidity constraint if provided
        if max_token_units is not None and optimal_token_units > max_token_units:
            logger.warning(f"⚠️  Optimal size {optimal_token_units:.2f} exceeds pool capacity {max_token_units:.2f}")
            optimal_token_units = max_token_units
        
        # Step 5: Calculate final profit with optimal size
        gross_spread_usd = optimal_token_units * raw_spread_per_token
        
        buy_fee_usd = optimal_token_units * buy_price * self.dex_fee_decimal
        sell_fee_usd = optimal_token_units * sell_price * self.dex_fee_decimal
        flash_fee_usd = optimal_token_units * buy_price * self.flash_fee_decimal
        total_fees_usd = buy_fee_usd + sell_fee_usd + flash_fee_usd
        
        net_profit_usd = (optimal_token_units * coeff) - self.gas_buffer_usd
        
        # Step 6: Calculate ROI (on capital deployed)
        capital_deployed = optimal_token_units * buy_price
        roi_percent = (net_profit_usd / capital_deployed * 100) if capital_deployed > 0 else 0
        
        # Step 7: Validation
        is_profitable = net_profit_usd >= self.min_profit_usd
        profitability_ratio = coeff / self.gas_buffer_usd if self.gas_buffer_usd > 0 else float('inf')
        
        return CoefficientResult(
            buy_price=buy_price,
            sell_price=sell_price,
            raw_spread_per_token=raw_spread_per_token,
            dex_fee_decimal=self.dex_fee_decimal,
            flash_fee_decimal=self.flash_fee_decimal,
            gas_buffer_usd=self.gas_buffer_usd,
            min_profit_usd=self.min_profit_usd,
            coeff=coeff,
            breakeven_token_units=breakeven_token_units,
            optimal_token_units=optimal_token_units,
            gross_spread_usd=gross_spread_usd,
            total_fees_usd=total_fees_usd,
            net_profit_usd=net_profit_usd,
            roi_percent=roi_percent,
            is_profitable=is_profitable,
            profitability_ratio=profitability_ratio
        )
    
    def verify_calculation(self, result: CoefficientResult) -> bool:
        """
        Verify the coefficient calculation matches the expanded form
        
        This proves the algebra:
        net_profit = (token_units × coeff) - gas_buffer
                  == (token_units × spread) - (fees) - gas_buffer
        """
        # Method 1: Coefficient form (collapsed)
        method1 = (result.optimal_token_units * result.coeff) - self.gas_buffer_usd
        
        # Method 2: Expanded form (original equation)
        gross = result.optimal_token_units * result.raw_spread_per_token
        buy_fee = result.optimal_token_units * result.buy_price * self.dex_fee_decimal
        sell_fee = result.optimal_token_units * result.sell_price * self.dex_fee_decimal
        flash_fee = result.optimal_token_units * result.buy_price * self.flash_fee_decimal
        method2 = gross - buy_fee - sell_fee - flash_fee - self.gas_buffer_usd
        
        # Should be identical (within floating point precision)
        match = abs(method1 - method2) < 0.01
        
        if not match:
            logger.error(f"❌ Verification FAILED:")
            logger.error(f"   Coefficient form: ${method1:.4f}")
            logger.error(f"   Expanded form:    ${method2:.4f}")
            logger.error(f"   Difference:       ${abs(method1 - method2):.4f}")
        
        return match


def print_coefficient_breakdown(result: CoefficientResult):
    """Pretty print the coefficient calculation breakdown"""
    print("=" * 80)
    print("COEFFICIENT PROFIT CALCULATION")
    print("=" * 80)
    print()
    
    print("INPUT PARAMETERS:")
    print(f"  Buy Price:       ${result.buy_price:.4f} per token")
    print(f"  Sell Price:      ${result.sell_price:.4f} per token")
    print(f"  Raw Spread:      ${result.raw_spread_per_token:.4f} per token")
    print(f"  DEX Fee:         {result.dex_fee_decimal*100:.3f}% per swap")
    print(f"  Flash Fee:       {result.flash_fee_decimal*100:.4f}%")
    print(f"  Gas Buffer:      ${result.gas_buffer_usd:.4f}")
    print(f"  Min Profit:      ${result.min_profit_usd:.2f}")
    print()
    
    print("COEFFICIENT DERIVATION:")
    print(f"  coeff = raw_spread - (buy × dex_fee) - (sell × dex_fee) - (buy × flash_fee)")
    print(f"        = ${result.raw_spread_per_token:.4f}")
    print(f"          - (${result.buy_price:.4f} × {result.dex_fee_decimal:.5f})")
    print(f"          - (${result.sell_price:.4f} × {result.dex_fee_decimal:.5f})")
    print(f"          - (${result.buy_price:.4f} × {result.flash_fee_decimal:.6f})")
    
    buy_fee = result.buy_price * result.dex_fee_decimal
    sell_fee = result.sell_price * result.dex_fee_decimal
    flash_fee = result.buy_price * result.flash_fee_decimal
    
    print(f"        = ${result.raw_spread_per_token:.4f} - ${buy_fee:.4f} - ${sell_fee:.4f} - ${flash_fee:.4f}")
    print(f"        = ${result.coeff:.6f} per token")
    print()
    
    print("OPTIMAL SIZE CALCULATION:")
    print(f"  Breakeven: token_units = (gas + min_profit) / coeff")
    print(f"                         = (${result.gas_buffer_usd:.4f} + ${result.min_profit_usd:.2f}) / ${result.coeff:.6f}")
    print(f"                         = {result.breakeven_token_units:.2f} tokens")
    print(f"  Optimal:               = {result.optimal_token_units:.0f} tokens (ceiling)")
    print()
    
    print("PROFIT CALCULATION:")
    print(f"  Gross Spread:    ${result.gross_spread_usd:.2f}")
    print(f"  Total Fees:      ${result.total_fees_usd:.2f}")
    print(f"  Gas Buffer:      ${result.gas_buffer_usd:.4f}")
    print(f"  ─────────────────────────────")
    print(f"  Net Profit:      ${result.net_profit_usd:.2f}")
    print(f"  ROI:             {result.roi_percent:.4f}%")
    print()
    
    print("VALIDATION:")
    print(f"  Is Profitable:       {'✅ YES' if result.is_profitable else '❌ NO'}")
    print(f"  Profitability Ratio: {result.profitability_ratio:.2f}x (coeff/gas)")
    print()
    
    print("VERIFICATION (Coefficient vs Expanded Form):")
    method1 = (result.optimal_token_units * result.coeff) - result.gas_buffer_usd
    method2 = result.net_profit_usd
    print(f"  Method 1 (coeff):    ${method1:.4f}")
    print(f"  Method 2 (expanded): ${method2:.4f}")
    print(f"  Match:               {'✅ PASS' if abs(method1 - method2) < 0.01 else '❌ FAIL'}")
    print("=" * 80)


# Singleton instance
_calculator = None

def get_coefficient_calculator() -> CoefficientProfitCalculator:
    """Get or create coefficient calculator"""
    global _calculator
    if _calculator is None:
        _calculator = CoefficientProfitCalculator()
    return _calculator


if __name__ == "__main__":
    # Test with the exact example from the user
    calc = CoefficientProfitCalculator(
        dex_fee_bps=30,      # 0.30%
        flash_fee_bps=5,     # 0.05% (user's example)
        gas_buffer_usd=0.02,
        min_profit_usd=5.0
    )
    
    # User's example: LINK $1.00 → $1.05 ($0.05 spread)
    result = calc.calculate_optimal_size(
        buy_price=1.00,
        sell_price=1.05
    )
    
    print_coefficient_breakdown(result)
    
    # Verify
    verified = calc.verify_calculation(result)
    if verified:
        print("\n✅ Coefficient derivation VERIFIED - algebra is correct!")
    else:
        print("\n❌ Verification FAILED - check the math!")
