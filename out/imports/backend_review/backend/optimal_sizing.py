"""
Angeris-Chitra Optimal Trade Sizing
Closed-form solution for maximum profit in 2-leg arbitrage

Paper: "Improved Price Oracles: Constant Function Market Makers" (2020)
https://arxiv.org/abs/2003.10001

Key insight: For cycle A → B → A across two pools, optimal input x* has closed form:
    x* = (√(γ₁γ₂ R₁ᵢR₁ₒR₂ᵢR₂ₒ) - R₁ᵢR₂ᵢ) / (γ₁(R₂ᵢ + γ₂R₁ₒ))
    
Where γᵢ = 1 - feeᵢ (after-fee multiplier)

Profitable iff: γ₁γ₂ R₁ₒ R₂ₒ > R₁ᵢ R₂ᵢ
"""

import math
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


def optimal_two_leg_input(
    r1_in: float,
    r1_out: float,
    fee1: float,
    r2_in: float,
    r2_out: float,
    fee2: float,
    min_input: float = 100,
    max_input: float = 1_000_000
) -> Tuple[float, bool]:
    """
    Calculate optimal input for 2-leg arbitrage using Angeris-Chitra formula
    
    Args:
        r1_in: Pool 1 input token reserve (normalized)
        r1_out: Pool 1 output token reserve (normalized)
        fee1: Pool 1 fee as decimal (e.g., 0.003 for 0.3%)
        r2_in: Pool 2 input token reserve (normalized, same as pool 1 output)
        r2_out: Pool 2 output token reserve (normalized, same as pool 1 input)
        fee2: Pool 2 fee as decimal
        min_input: Minimum viable trade size
        max_input: Maximum trade size (capital constraint)
        
    Returns:
        (optimal_input, is_profitable)
    """
    
    # After-fee multipliers
    gamma1 = 1 - fee1
    gamma2 = 1 - fee2
    
    # Profitability check: γ₁γ₂ R₁ₒ R₂ₒ > R₁ᵢ R₂ᵢ
    lhs = gamma1 * gamma2 * r1_out * r2_out
    rhs = r1_in * r2_in
    
    if lhs <= rhs:
        # Not profitable - no arbitrage opportunity
        return 0.0, False
    
    # Optimal input (Angeris-Chitra closed form)
    try:
        numerator = math.sqrt(gamma1 * gamma2 * r1_in * r1_out * r2_in * r2_out) - r1_in * r2_in
        denominator = gamma1 * (r2_in + gamma2 * r1_out)
        
        if denominator <= 0:
            return 0.0, False
        
        x_optimal = numerator / denominator
        
        # Apply bounds
        x_optimal = max(min_input, min(x_optimal, max_input))
        
        # Sanity check
        if x_optimal <= 0 or math.isnan(x_optimal) or math.isinf(x_optimal):
            return 0.0, False
        
        logger.debug(f"Optimal input: {x_optimal:.6f} (γ₁={gamma1:.4f}, γ₂={gamma2:.4f})")
        return x_optimal, True
        
    except (ValueError, ZeroDivisionError, OverflowError) as e:
        logger.debug(f"Optimal sizing error: {e}")
        return 0.0, False


def optimal_loan_amount_with_depth(
    r_in: float,
    r_out: float,
    fee_bps: int,
    depth_score: float,
    base_fee_gwei: float = 60,
    min_loan: float = 1000,
    max_loan: float = 100_000
) -> float:
    """
    Calculate optimal flash loan with depth and gas adjustments
    
    From SSOT:
        fee_term = max(1, 10_000 - fee_bps)
        optimal_base = (√(R_in · R_out · fee_term · 10_000) - R_in · 10_000) / fee_term
        size = optimal_base · depth_multiplier(depth_score, base_fee_gwei)
    
    Args:
        r_in: Input reserve (normalized)
        r_out: Output reserve (normalized)
        fee_bps: Fee in basis points (e.g., 30 for 0.3%)
        depth_score: Pool depth score (≥500)
        base_fee_gwei: Current base fee in Gwei
        min_loan: Minimum loan size
        max_loan: Maximum loan size
        
    Returns:
        Optimal loan amount in token units
    """
    
    # Fee term
    fee_term = max(1, 10_000 - fee_bps)
    
    try:
        # Base optimal size
        sqrt_term = math.sqrt(r_in * r_out * fee_term * 10_000)
        optimal_base = (sqrt_term - r_in * 10_000) / fee_term
        
        # Depth multiplier: min(1, depth_score/1500) · (1 - 0.3·base_fee/400)
        depth_factor = min(1.0, depth_score / 1500)
        gas_factor = max(0.4, 1 - 0.3 * base_fee_gwei / 400)  # Floor at 0.4
        depth_multiplier = depth_factor * gas_factor
        
        # Final size
        optimal_size = optimal_base * depth_multiplier
        
        # Apply bounds
        optimal_size = max(min_loan, min(optimal_size, max_loan))
        
        logger.debug(
            f"Optimal loan: {optimal_size:.2f} "
            f"(base={optimal_base:.2f}, depth_mult={depth_multiplier:.3f})"
        )
        
        return optimal_size
        
    except (ValueError, ZeroDivisionError, OverflowError) as e:
        logger.debug(f"Optimal loan calculation error: {e}")
        return min_loan


def calculate_expected_profit(
    input_amount: float,
    r1_in: float,
    r1_out: float,
    fee1: float,
    r2_in: float,
    r2_out: float,
    fee2: float
) -> float:
    """
    Calculate expected profit for given input using constant product formula
    
    Returns profit in input token units (can be negative)
    """
    
    gamma1 = 1 - fee1
    gamma2 = 1 - fee2
    
    # Leg 1: x → y
    x_after_fee = input_amount * gamma1
    y_out = (x_after_fee * r1_out) / (r1_in + x_after_fee)
    
    # Leg 2: y → x
    y_after_fee = y_out * gamma2
    x_final = (y_after_fee * r2_out) / (r2_in + y_after_fee)
    
    # Profit
    return x_final - input_amount


def verify_profitability(
    r1_in: float,
    r1_out: float,
    fee1: float,
    r2_in: float,
    r2_out: float,
    fee2: float
) -> Tuple[bool, float]:
    """
    Quick profitability check using Angeris-Chitra condition
    
    Returns:
        (is_profitable, price_ratio)
    """
    
    gamma1 = 1 - fee1
    gamma2 = 1 - fee2
    
    lhs = gamma1 * gamma2 * r1_out * r2_out
    rhs = r1_in * r2_in
    
    # Price ratio (how much better the arbitrage path is vs direct swap)
    ratio = lhs / rhs if rhs > 0 else 0
    
    return ratio > 1.0, ratio


# Global instance for easy import
def get_optimal_input(
    pool1_reserve_in: float,
    pool1_reserve_out: float,
    pool1_fee: float,
    pool2_reserve_in: float,
    pool2_reserve_out: float,
    pool2_fee: float,
    max_size_usd: float = 50_000
) -> Tuple[float, bool]:
    """
    Convenience wrapper for optimal sizing
    Returns (optimal_amount, is_profitable)
    """
    return optimal_two_leg_input(
        r1_in=pool1_reserve_in,
        r1_out=pool1_reserve_out,
        fee1=pool1_fee,
        r2_in=pool2_reserve_in,
        r2_out=pool2_reserve_out,
        fee2=pool2_fee,
        max_input=max_size_usd
    )
