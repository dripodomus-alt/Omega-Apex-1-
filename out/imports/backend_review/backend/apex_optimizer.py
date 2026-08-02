"""
APEX_OMEGA Apex Point Optimizer
Recursive Profit Maximization Engine

Calculates optimal C2 trade size that:
1. Captures C1-created alpha surface
2. Doesn't create reverse impact that negates profit
3. Maximizes combined (C1 + C2) profit

Uses binary search with Slippage Sentinel predictions.
"""

import numpy as np
from typing import Dict, Tuple
import logging
from slippage_sentinel import get_slippage_sentinel

logger = logging.getLogger(__name__)


class ApexOptimizer:
    """
    Finds the 'Apex Point' - optimal C2 size for dual-punch strategy.
    
    The Apex Point is where:
        ∂(P_C1 + P_C2)/∂C2 = 0
    
    In practice: Largest C2 that doesn't destroy the alpha it's trying to capture.
    """
    
    def __init__(self):
        self.sentinel = get_slippage_sentinel()
        self.search_iterations = 20
        self.min_combined_profit = 15.0  # $15 minimum for dual-punch
    
    def calculate_apex_point(
        self,
        c1_displacement_bps: float,
        pool_liquidity_usd: float,
        pool_price: float,
        volatility_1h: float = 0.01,
        volatility_24h: float = 0.02,
        gas_cost_usd: float = 0.02
    ) -> Dict:
        """
        Calculate optimal C2 trade size.
        
        Args:
            c1_displacement_bps: How many bps C1 moved the price (e.g., 50 = 0.50%)
            pool_liquidity_usd: Total pool TVL
            pool_price: Current pool price
            volatility_1h: 1-hour volatility
            volatility_24h: 24-hour volatility
            gas_cost_usd: Estimated gas cost per transaction
        
        Returns:
            {
                'c2_optimal_size_usd': 25000,
                'c2_predicted_profit': 18.50,
                'c2_predicted_slippage': 0.015,
                'apex_found': True,
                'search_iterations': 15
            }
        """
        # Alpha surface = artificial spread created by C1
        alpha_surface_bps = c1_displacement_bps
        alpha_surface_usd = (alpha_surface_bps / 10000) * pool_liquidity_usd
        
        # Binary search for optimal C2 size
        low = 0
        high = min(alpha_surface_usd * 3, pool_liquidity_usd * 0.3)  # Cap at 30% pool size
        best_c2_size = 0
        best_profit = 0
        
        for iteration in range(self.search_iterations):
            mid = (low + high) / 2
            
            # Predict C2 slippage
            c2_prediction = self.sentinel.predict_slippage(
                trade_amount_usd=mid,
                pool_liquidity_usd=pool_liquidity_usd,
                volatility_1h=volatility_1h,
                volatility_24h=volatility_24h,
                spread_bps=alpha_surface_bps
            )
            
            c2_slippage = c2_prediction['predicted_slippage']
            
            # Calculate C2 profit
            # Gross = alpha captured
            # Net = gross - slippage impact - gas
            gross_profit = (alpha_surface_bps / 10000) * mid
            slippage_cost = c2_slippage * mid
            net_profit = gross_profit - slippage_cost - gas_cost_usd
            
            # Track best
            if net_profit > best_profit:
                best_profit = net_profit
                best_c2_size = mid
            
            # Binary search logic
            if net_profit > 0:
                # Profit positive, try larger size
                low = mid
            else:
                # Profit negative, size too large
                high = mid
            
            # Convergence check
            if (high - low) < 100:  # Converged to $100 precision
                break
        
        # Final prediction at apex point
        final_prediction = self.sentinel.predict_slippage(
            trade_amount_usd=best_c2_size,
            pool_liquidity_usd=pool_liquidity_usd,
            volatility_1h=volatility_1h,
            volatility_24h=volatility_24h,
            spread_bps=alpha_surface_bps
        )
        
        return {
            'c2_optimal_size_usd': best_c2_size,
            'c2_predicted_profit': best_profit,
            'c2_predicted_slippage': final_prediction['predicted_slippage'],
            'c2_impact_category': final_prediction['impact_category'],
            'alpha_surface_bps': alpha_surface_bps,
            'apex_found': best_profit > 0,
            'search_iterations': iteration + 1,
            'utilization_ratio': best_c2_size / pool_liquidity_usd if pool_liquidity_usd > 0 else 0
        }
    
    def evaluate_dual_punch(
        self,
        c1_size_usd: float,
        c1_entry_price: float,
        c1_target_price: float,
        pool_liquidity_usd: float,
        pool_current_price: float,
        volatility_1h: float = 0.01,
        volatility_24h: float = 0.02,
        gas_cost_usd: float = 0.02
    ) -> Dict:
        """
        Full dual-punch evaluation: Should we execute C1+C2 or abort?
        
        Returns decision with complete profit breakdown.
        """
        # Step 1: Predict C1 slippage and profit
        c1_prediction = self.sentinel.predict_slippage(
            trade_amount_usd=c1_size_usd,
            pool_liquidity_usd=pool_liquidity_usd,
            volatility_1h=volatility_1h,
            volatility_24h=volatility_24h,
            spread_bps=abs(c1_target_price - c1_entry_price) / c1_entry_price * 10000
        )
        
        c1_slippage = c1_prediction['predicted_slippage']
        
        # C1 profit = (Amount * (1 - slippage) * Target) - (Amount * Entry + Gas)
        c1_gross = c1_size_usd * (1 - c1_slippage) * c1_target_price
        c1_cost = c1_size_usd * c1_entry_price + gas_cost_usd
        c1_profit = c1_gross - c1_cost
        
        # C1 creates displacement
        c1_displacement_bps = abs(c1_target_price - pool_current_price) / pool_current_price * 10000
        
        # Step 2: Find apex point for C2
        apex_result = self.calculate_apex_point(
            c1_displacement_bps=c1_displacement_bps,
            pool_liquidity_usd=pool_liquidity_usd,
            pool_price=c1_target_price,  # C2 trades at C1's displaced price
            volatility_1h=volatility_1h,
            volatility_24h=volatility_24h,
            gas_cost_usd=gas_cost_usd
        )
        
        c2_profit = apex_result['c2_predicted_profit']
        
        # Step 3: Combined profit
        total_profit = c1_profit + c2_profit
        
        # Step 4: Execution decision
        if c1_profit > 5.0:
            # C1 profitable standalone
            decision = "EXECUTE_C1_ONLY"
            reason = f"C1 profit ${c1_profit:.2f} > $5 threshold (sniper mode)"
        elif total_profit > self.min_combined_profit:
            # Combined profitable
            decision = "EXECUTE_DUAL_PUNCH"
            reason = f"Combined profit ${total_profit:.2f} > $15 threshold"
        else:
            # Abort
            decision = "ABORT"
            reason = f"Insufficient profit: C1=${c1_profit:.2f}, C2=${c2_profit:.2f}, Total=${total_profit:.2f}"
        
        return {
            'decision': decision,
            'reason': reason,
            'c1_profit': c1_profit,
            'c1_slippage': c1_slippage,
            'c1_displacement_bps': c1_displacement_bps,
            'c2_optimal_size': apex_result['c2_optimal_size_usd'],
            'c2_profit': c2_profit,
            'c2_slippage': apex_result['c2_predicted_slippage'],
            'total_profit': total_profit,
            'apex_found': apex_result['apex_found'],
            'roi_percent': (total_profit / (c1_size_usd + apex_result['c2_optimal_size_usd'])) * 100 if decision != "ABORT" else 0
        }


# Singleton
_optimizer_instance = None


def get_apex_optimizer() -> ApexOptimizer:
    """Get or create singleton Apex Optimizer instance."""
    global _optimizer_instance
    if _optimizer_instance is None:
        _optimizer_instance = ApexOptimizer()
    return _optimizer_instance


if __name__ == "__main__":
    # Test the Apex Optimizer
    optimizer = ApexOptimizer()
    
    print("\n" + "="*70)
    print("APEX_OMEGA DUAL-PUNCH EVALUATION TESTS")
    print("="*70)
    
    # Test Case 1: Strong C1 standalone (should execute C1 only)
    print("\n🧪 Test 1: Strong C1 Standalone ($10k trade, good spread)")
    result1 = optimizer.evaluate_dual_punch(
        c1_size_usd=10000,
        c1_entry_price=1.000,
        c1_target_price=1.008,  # 80 bps spread
        pool_liquidity_usd=500_000,
        pool_current_price=1.004,
        volatility_1h=0.01,
        gas_cost_usd=0.02
    )
    print(f"   Decision: {result1['decision']}")
    print(f"   Reason: {result1['reason']}")
    print(f"   C1 Profit: ${result1['c1_profit']:.2f}")
    print(f"   C1 Slippage: {result1['c1_slippage']*100:.2f}%")
    
    # Test Case 2: Weak C1, strong combined (should dual-punch)
    print("\n🧪 Test 2: Weak C1, Strong Combined ($20k trade, creates displacement)")
    result2 = optimizer.evaluate_dual_punch(
        c1_size_usd=20000,
        c1_entry_price=1.000,
        c1_target_price=1.003,  # 30 bps spread (weak)
        pool_liquidity_usd=300_000,
        pool_current_price=1.000,
        volatility_1h=0.015,
        gas_cost_usd=0.02
    )
    print(f"   Decision: {result2['decision']}")
    print(f"   Reason: {result2['reason']}")
    print(f"   C1 Profit: ${result2['c1_profit']:.2f}")
    print(f"   C1 Displacement: {result2['c1_displacement_bps']:.1f} bps")
    print(f"   C2 Optimal Size: ${result2['c2_optimal_size']:.0f}")
    print(f"   C2 Profit: ${result2['c2_profit']:.2f}")
    print(f"   Total Profit: ${result2['total_profit']:.2f}")
    print(f"   ROI: {result2['roi_percent']:.2f}%")
    
    # Test Case 3: Both weak (should abort)
    print("\n🧪 Test 3: Both Weak ($5k trade, tiny spread)")
    result3 = optimizer.evaluate_dual_punch(
        c1_size_usd=5000,
        c1_entry_price=1.000,
        c1_target_price=1.001,  # 10 bps spread
        pool_liquidity_usd=1_000_000,
        pool_current_price=1.000,
        volatility_1h=0.005,
        gas_cost_usd=0.02
    )
    print(f"   Decision: {result3['decision']}")
    print(f"   Reason: {result3['reason']}")
    print(f"   C1 Profit: ${result3['c1_profit']:.2f}")
    print(f"   C2 Profit: ${result3['c2_profit']:.2f}")
    print(f"   Total: ${result3['total_profit']:.2f}")
    
    print("\n" + "="*70)
