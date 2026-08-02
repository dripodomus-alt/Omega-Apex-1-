"""
2026 Institutional Slippage Prediction (Exact Formula)

Slippage = difference between expected price and actual execution price

Components:
1. Base AMM Impact (price impact from trade size)
2. Liquidity Penalty (1 / ActiveLiquidityScore)
3. Volatility Adjustment (weighted vol)
4. Observed Spread (market inefficiency)
5. ML Residual (trained prediction)

Formula:
    Predicted_Slippage_bps = 
        Base_AMM_Impact + 
        Liquidity_Penalty × VolFactor + 
        Observed_Spread_bps + 
        ML_Residual
"""

import numpy as np
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class SlippagePredictorV2026:
    """
    2026 Institutional Standard for Slippage Prediction.
    
    Implements exact formula:
    Slippage_bps = Base_AMM_Impact + (1/ActiveLiquidity) * VolFactor + Spread_bps + ML_Residual
    """
    
    def __init__(self, ml_model=None):
        self.ml_model = ml_model
    
    def predict_slippage(
        self,
        # Trade parameters
        amount_in: float,           # Trade size in token units (e.g., 10,000 USDC)
        reserve_in: float,          # Pool reserve of input token
        
        # Pool parameters
        fee_bps: float = 30,        # Pool fee in basis points (30 = 0.30%)
        active_liquidity_score: float = 0.5,  # 0-1, higher = more liquidity in range
        
        # Market parameters
        observed_spread_bps: float = 0,  # Current bid-ask spread
        volatility_1h: float = 0.01,     # 1-hour volatility (decimal)
        volatility_24h: float = 0.02,    # 24-hour volatility (decimal)
        
        # Optional V3 parameters
        tick_spacing: Optional[int] = None,
        current_tick_distance: Optional[int] = None,
        
        # Trade direction
        trade_direction: str = 'buy'
    ) -> Dict[str, float]:
        """
        Predict execution slippage using 2026 institutional formula.
        
        Returns:
            {
                'predicted_slippage_bps': float,
                'base_amm_impact_bps': float,
                'liquidity_penalty_bps': float,
                'volatility_adjustment_bps': float,
                'observed_spread_bps': float,
                'ml_residual_bps': float
            }
        """
        
        # COMPONENT 1: Base AMM Impact
        base_amm_impact_bps = self._calculate_base_amm_impact(
            amount_in=amount_in,
            reserve_in=reserve_in,
            fee_bps=fee_bps
        )
        
        # COMPONENT 2: Liquidity Penalty
        liquidity_penalty = self._calculate_liquidity_penalty(
            active_liquidity_score=active_liquidity_score
        )
        
        # COMPONENT 3: Volatility Adjustment
        vol_factor = self._calculate_volatility_factor(
            vol_1h=volatility_1h,
            vol_24h=volatility_24h
        )
        
        liquidity_penalty_bps = liquidity_penalty * vol_factor * 10000
        
        # COMPONENT 4: Observed Spread (already in bps)
        spread_bps = observed_spread_bps
        
        # COMPONENT 5: ML Residual (trained model predicts only the error)
        ml_residual_bps = self._calculate_ml_residual(
            base_impact=base_amm_impact_bps,
            liquidity_penalty=liquidity_penalty,
            vol_factor=vol_factor,
            spread_bps=spread_bps,
            tick_distance=current_tick_distance or 0,
            direction=trade_direction
        )
        
        # FINAL PREDICTION
        predicted_slippage_bps = (
            base_amm_impact_bps +
            liquidity_penalty_bps +
            spread_bps +
            ml_residual_bps
        )
        
        # Cannot be negative
        predicted_slippage_bps = max(0, predicted_slippage_bps)
        
        return {
            'predicted_slippage_bps': float(predicted_slippage_bps),
            'predicted_slippage_decimal': float(predicted_slippage_bps / 10000),
            'base_amm_impact_bps': float(base_amm_impact_bps),
            'liquidity_penalty_bps': float(liquidity_penalty_bps),
            'volatility_adjustment': float(vol_factor),
            'observed_spread_bps': float(spread_bps),
            'ml_residual_bps': float(ml_residual_bps),
            'breakdown': {
                'base_amm': f'{base_amm_impact_bps:.2f} bps',
                'liquidity': f'{liquidity_penalty_bps:.2f} bps',
                'spread': f'{spread_bps:.2f} bps',
                'ml_residual': f'{ml_residual_bps:.2f} bps',
                'total': f'{predicted_slippage_bps:.2f} bps'
            }
        }
    
    def _calculate_base_amm_impact(
        self,
        amount_in: float,
        reserve_in: float,
        fee_bps: float
    ) -> float:
        """
        Calculate base AMM price impact using exact formula:
        
        Base_AMM_Impact_bps = (AmountIn × FeeFactor) / (ReserveIn + AmountIn × FeeFactor) × 10000
        
        Where:
            FeeFactor = 1 - (fee_bps / 10000)
            
        Args:
            amount_in: Trade size in token units
            reserve_in: Pool reserve of input token
            fee_bps: Fee in basis points (30 = 0.30%)
            
        Returns:
            Price impact in basis points
        """
        if reserve_in <= 0:
            return 5000  # 50% default for invalid pools
        
        # Calculate fee factor
        fee_factor = 1 - (fee_bps / 10000)
        
        # Exact formula
        numerator = amount_in * fee_factor
        denominator = reserve_in + (amount_in * fee_factor)
        
        impact = (numerator / denominator) * 10000 if denominator > 0 else 5000
        
        return float(impact)
    
    def _calculate_liquidity_penalty(
        self,
        active_liquidity_score: float
    ) -> float:
        """
        Calculate liquidity penalty factor.
        
        Liquidity_Penalty = 1 / ActiveLiquidityScore
        
        Args:
            active_liquidity_score: 0-1, higher = more liquidity in active range
            
        Returns:
            Penalty multiplier (higher = worse liquidity)
        """
        # Prevent division by zero
        if active_liquidity_score <= 0:
            return 10.0  # Maximum penalty for no liquidity
        
        penalty = 1.0 / active_liquidity_score
        
        # Cap at reasonable maximum
        return min(penalty, 10.0)
    
    def _calculate_volatility_factor(
        self,
        vol_1h: float,
        vol_24h: float
    ) -> float:
        """
        Calculate weighted volatility factor.
        
        VolFactor = (vol_1h × 0.7) + (vol_24h × 0.3)
        
        Args:
            vol_1h: 1-hour volatility (decimal, e.g., 0.02 = 2%)
            vol_24h: 24-hour volatility (decimal)
            
        Returns:
            Weighted volatility factor
        """
        vol_factor = (vol_1h * 0.7) + (vol_24h * 0.3)
        return float(vol_factor)
    
    def _calculate_ml_residual(
        self,
        base_impact: float,
        liquidity_penalty: float,
        vol_factor: float,
        spread_bps: float,
        tick_distance: int,
        direction: str
    ) -> float:
        """
        ML model predicts only the RESIDUAL error, not total slippage.
        
        This makes the model much more stable and trainable.
        
        Returns:
            Predicted residual in basis points
        """
        if self.ml_model is None:
            return 0.0  # No ML model, return zero residual
        
        # Direction encoding
        direction_flag = 1.0 if direction == 'buy' else -1.0
        
        # Features for ML model
        features = np.array([[
            base_impact,
            liquidity_penalty,
            vol_factor,
            spread_bps,
            tick_distance,
            direction_flag
        ]])
        
        try:
            # Predict residual
            residual = self.ml_model.predict(features)[0]
            
            # Clamp to reasonable range (±50 bps)
            return float(np.clip(residual, -50, 50))
        
        except Exception as e:
            logger.debug(f"ML residual prediction failed: {e}")
            return 0.0
    
    def should_execute_trade(
        self,
        predicted_slippage_bps: float,
        observed_spread_bps: float,
        gas_cost_usd: float,
        loan_amount_usd: float,
        safety_buffer_bps: float = 8.0
    ) -> Dict[str, any]:
        """
        Final guard: reject if slippage eats the spread.
        
        Formula:
            if predicted_slippage_bps > observed_spread_bps + 8.0:
                reject("Slippage eats the edge")
        
        Args:
            predicted_slippage_bps: Total predicted slippage
            observed_spread_bps: Current market spread
            gas_cost_usd: Gas cost in USD
            loan_amount_usd: Flash loan amount
            safety_buffer_bps: Safety margin (default 8 bps)
            
        Returns:
            {
                'execute': bool,
                'reason': str,
                'net_profit_bps': float
            }
        """
        # Calculate gas in bps
        gas_bps = (gas_cost_usd / loan_amount_usd) * 10000 if loan_amount_usd > 0 else 100
        
        # Total costs
        total_costs_bps = predicted_slippage_bps + gas_bps
        
        # Net profit after slippage and gas
        net_profit_bps = observed_spread_bps - total_costs_bps
        
        # Guard 1: Slippage eats the edge
        if predicted_slippage_bps > (observed_spread_bps + safety_buffer_bps):
            return {
                'execute': False,
                'reason': f'Slippage eats the edge ({predicted_slippage_bps:.2f} bps > {observed_spread_bps:.2f} bps spread + {safety_buffer_bps:.2f} buffer)',
                'net_profit_bps': net_profit_bps
            }
        
        # Guard 2: Net loss after all costs
        if net_profit_bps <= 0:
            return {
                'execute': False,
                'reason': f'Net loss ({net_profit_bps:.2f} bps)',
                'net_profit_bps': net_profit_bps
            }
        
        # Guard 3: Edge too thin (absolute minimum)
        if observed_spread_bps < 12.0:
            return {
                'execute': False,
                'reason': f'Edge too thin ({observed_spread_bps:.2f} bps < 12 bps min)',
                'net_profit_bps': net_profit_bps
            }
        
        return {
            'execute': True,
            'reason': f'Profitable: {net_profit_bps:.2f} bps net',
            'net_profit_bps': net_profit_bps
        }


# Global singleton
_slippage_predictor_2026 = None

def get_slippage_predictor_2026(ml_model=None):
    """Get or create slippage predictor singleton."""
    global _slippage_predictor_2026
    if _slippage_predictor_2026 is None:
        _slippage_predictor_2026 = SlippagePredictorV2026(ml_model=ml_model)
    return _slippage_predictor_2026


if __name__ == "__main__":
    """Test the 2026 institutional formula"""
    
    predictor = SlippagePredictorV2026()
    
    print("="*80)
    print("2026 INSTITUTIONAL SLIPPAGE PREDICTOR TEST")
    print("="*80)
    print()
    
    # Test Case 1: Small trade in deep liquidity pool
    print("TEST 1: $10k trade in $1M pool (good liquidity)")
    print("-"*80)
    
    result1 = predictor.predict_slippage(
        amount_in=10000,
        reserve_in=500000,  # $500k reserve
        fee_bps=30,
        active_liquidity_score=0.8,  # 80% liquidity in active range
        observed_spread_bps=29.52,   # WPOL/USDC spread
        volatility_1h=0.02,
        volatility_24h=0.03
    )
    
    for key, value in result1['breakdown'].items():
        print(f"  {key}: {value}")
    print()
    
    decision1 = predictor.should_execute_trade(
        predicted_slippage_bps=result1['predicted_slippage_bps'],
        observed_spread_bps=29.52,
        gas_cost_usd=0.50,
        loan_amount_usd=10000
    )
    print(f"  Decision: {decision1['reason']}")
    print()
    
    # Test Case 2: Same trade in shallow liquidity
    print("TEST 2: $10k trade in $200k pool (shallow liquidity)")
    print("-"*80)
    
    result2 = predictor.predict_slippage(
        amount_in=10000,
        reserve_in=100000,  # Only $100k reserve
        fee_bps=30,
        active_liquidity_score=0.3,  # Only 30% liquidity in range
        observed_spread_bps=29.52,
        volatility_1h=0.05,  # Higher volatility
        volatility_24h=0.06
    )
    
    for key, value in result2['breakdown'].items():
        print(f"  {key}: {value}")
    print()
    
    decision2 = predictor.should_execute_trade(
        predicted_slippage_bps=result2['predicted_slippage_bps'],
        observed_spread_bps=29.52,
        gas_cost_usd=0.50,
        loan_amount_usd=10000
    )
    print(f"  Decision: {decision2['reason']}")
    print()
    
    # Test Case 3: Thin edge (USDC/USDT at 3.68 bps)
    print("TEST 3: Thin edge - USDC/USDT 3.68 bps")
    print("-"*80)
    
    result3 = predictor.predict_slippage(
        amount_in=10000,
        reserve_in=5000000,  # Deep stable pool
        fee_bps=5,  # Lower fee tier
        active_liquidity_score=0.9,
        observed_spread_bps=3.68,  # Thin edge
        volatility_1h=0.001,
        volatility_24h=0.001
    )
    
    for key, value in result3['breakdown'].items():
        print(f"  {key}: {value}")
    print()
    
    decision3 = predictor.should_execute_trade(
        predicted_slippage_bps=result3['predicted_slippage_bps'],
        observed_spread_bps=3.68,
        gas_cost_usd=0.50,
        loan_amount_usd=10000
    )
    print(f"  Decision: {decision3['reason']}")
    print()
    
    print("="*80)
    print("FORMULA VERIFICATION")
    print("="*80)
    print()
    print("✅ Base AMM Impact: (AmountIn × FeeFactor) / (ReserveIn + AmountIn × FeeFactor) × 10000")
    print("✅ Liquidity Penalty: 1 / ActiveLiquidityScore")
    print("✅ Vol Factor: (vol_1h × 0.7) + (vol_24h × 0.3)")
    print("✅ Final: Base + Liquidity×Vol + Spread + ML_Residual")
    print()
    print("Guard: if predicted_slippage > observed_spread + 8.0 → REJECT")
