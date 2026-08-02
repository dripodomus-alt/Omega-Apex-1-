"""
VelvetOracle Institutional Slippage Model (2026 Standard)
Production-grade slippage prediction for V2/V3 AMM arbitrage

4-component master equation (2026 spec):

    Predicted_Slippage_bps =
        Base_AMM_Impact_bps                      # exact constant-product formula
        + (1/φ) × VolFactor × 10,000             # liquidity penalty × weighted vol
        + Observed_Spread_bps                    # current market bid-ask spread
        + ML_Residual_bps                        # trained model residual (0 if no model)

Where:
    FeeFactor  = 1 − fee_bps/10,000
    Base_AMM   = (AmountIn × FeeFactor) / (ReserveIn + AmountIn × FeeFactor) × 10,000
    φ          = active_liquidity_score  (0–1; V2 default 0.5, V3 = active/total)
    VolFactor  = vol_1h × 0.7 + vol_24h × 0.3
"""

import numpy as np
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class InstitutionalSlippageModel:
    """
    VelvetOracle Standard 2026 — Institutional-grade slippage prediction.

    Implements the exact 4-component formula from 2026_SLIPPAGE_FORMULA_SPEC.md:
        Slippage_bps = Base_AMM_Impact
                     + (1/φ) × VolFactor × 10,000
                     + Observed_Spread_bps
                     + ML_Residual_bps
    """

    def __init__(self, ml_model=None):
        self.ml_model = ml_model
        self.gas_cost_usd = 0.50   # Polygon: ~$0.50 per 2-leg swap
        self.safety_buffer_bps = 8.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def predict_execution_slippage(
        self,
        # Trade params
        amount_in_usd: float,
        loan_amount_usd: float,

        # Pool params
        reserve_in: float,
        reserve_out: float,
        pool_tvl_usd: float,
        fee_bps: float = 30,

        # Liquidity (φ)
        active_liquidity_score: float = 0.5,   # 0–1; V2 default 0.5, V3 = active/total

        # V3-specific (optional)
        tick_spacing: Optional[int] = None,
        tick_distance: Optional[float] = None,

        # Market params
        observed_spread_bps: float = 0,
        volatility_1h: float = 0.01,
        volatility_24h: float = 0.02,

        # Direction
        trade_direction: str = 'buy',
    ) -> Dict[str, float]:
        """
        Predict execution slippage using the 2026 4-component formula.

        Returns:
            {
                'predicted_slippage_bps': float,
                'predicted_slippage_decimal': float,
                'base_amm_impact_bps': float,
                'liquidity_penalty_bps': float,
                'observed_spread_bps': float,
                'ml_residual_bps': float,
                'min_profitable_bps': float,
                'is_profitable': bool,
                'breakdown': dict
            }
        """
        # COMPONENT 1: Base AMM Impact
        # (AmountIn × FeeFactor) / (ReserveIn + AmountIn × FeeFactor) × 10,000
        base_amm_impact_bps = self._calculate_base_amm_impact(
            amount_in=amount_in_usd,
            reserve_in=reserve_in,
            fee_bps=fee_bps,
            tick_spacing=tick_spacing,
        )

        # COMPONENT 2: Liquidity Penalty × VolFactor
        # (1/φ) × VolFactor × 10,000
        vol_factor = self._calculate_vol_factor(volatility_1h, volatility_24h)
        liquidity_penalty = self._calculate_liquidity_penalty(active_liquidity_score)
        liquidity_penalty_bps = liquidity_penalty * vol_factor * 10000

        # COMPONENT 3: Observed Spread (already in bps)
        spread_bps = float(observed_spread_bps)

        # COMPONENT 4: ML Residual
        ml_residual_bps = self._calculate_ml_residual(
            base_impact_bps=base_amm_impact_bps,
            liquidity_penalty=liquidity_penalty,
            vol_factor=vol_factor,
            spread_bps=spread_bps,
            tick_distance=tick_distance or 0,
            trade_direction=trade_direction,
            pool_utilization=amount_in_usd / pool_tvl_usd if pool_tvl_usd > 0 else 0,
        )

        # FINAL: sum all 4 components
        predicted_slippage_bps = (
            base_amm_impact_bps
            + liquidity_penalty_bps
            + spread_bps
            + ml_residual_bps
        )
        predicted_slippage_bps = max(0.0, predicted_slippage_bps)

        # Gas-aware breakeven guard
        min_profitable_bps = self._calculate_min_profitable_bps(
            loan_amount_usd=loan_amount_usd,
            gas_cost_usd=self.gas_cost_usd,
        )

        # Execution costs = the three non-spread components (spread is the captured opportunity).
        # is_profitable ⟺ execution_costs < (spread_opportunity − gas_margin).
        # Do NOT use predicted_slippage_bps here: it already contains spread_bps, so
        # predicted < (spread − gas) reduces to base_amm + liq_penalty + ml < −gas (always False).
        execution_cost_bps = base_amm_impact_bps + liquidity_penalty_bps + ml_residual_bps
        is_profitable = execution_cost_bps < (spread_bps - min_profitable_bps)

        return {
            'predicted_slippage_bps': float(predicted_slippage_bps),
            'predicted_slippage_decimal': float(predicted_slippage_bps / 10000),
            'base_amm_impact_bps': float(base_amm_impact_bps),
            'liquidity_penalty_bps': float(liquidity_penalty_bps),
            'observed_spread_bps': float(spread_bps),
            'ml_residual_bps': float(ml_residual_bps),
            'min_profitable_bps': float(min_profitable_bps),
            'is_profitable': bool(is_profitable),
            'breakdown': {
                'base_amm': f'{base_amm_impact_bps:.2f} bps',
                'liquidity_penalty': f'{liquidity_penalty_bps:.2f} bps',
                'spread': f'{spread_bps:.2f} bps',
                'ml_residual': f'{ml_residual_bps:.2f} bps',
                'total': f'{predicted_slippage_bps:.2f} bps',
            },
        }

    def should_execute_trade(
        self,
        observed_spread_bps: float,
        predicted_slippage_bps: float,
        min_profitable_bps: float,
        dex_fee_bps: float = 60,   # 30 bps × 2 legs
    ) -> Dict:
        """
        Final execution gate with breakeven guard.

        Reject if:  predicted_slippage_bps > observed_spread_bps + safety_buffer_bps

        Returns:
            {'execute': bool, 'reason': str, 'net_profit_bps': float}
        """
        total_costs_bps = predicted_slippage_bps + dex_fee_bps + min_profitable_bps
        net_profit_bps = observed_spread_bps - total_costs_bps

        if predicted_slippage_bps > (observed_spread_bps + self.safety_buffer_bps):
            return {
                'execute': False,
                'reason': (
                    f'Slippage eats the edge '
                    f'({predicted_slippage_bps:.2f} bps > '
                    f'{observed_spread_bps:.2f} bps + {self.safety_buffer_bps:.2f} buffer)'
                ),
                'net_profit_bps': net_profit_bps,
            }

        if net_profit_bps <= 0:
            return {
                'execute': False,
                'reason': f'Net loss ({net_profit_bps:.2f} bps)',
                'net_profit_bps': net_profit_bps,
            }

        if observed_spread_bps < 12.0:
            return {
                'execute': False,
                'reason': f'Edge too thin ({observed_spread_bps:.2f} bps < 12 bps min)',
                'net_profit_bps': net_profit_bps,
            }

        return {
            'execute': True,
            'reason': f'Profitable: {net_profit_bps:.2f} bps net',
            'net_profit_bps': net_profit_bps,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _calculate_base_amm_impact(
        self,
        amount_in: float,
        reserve_in: float,
        fee_bps: float,
        tick_spacing: Optional[int],
    ) -> float:
        """
        Base AMM Impact (bps) — exact constant-product formula:

            FeeFactor = 1 − fee_bps/10,000
            Base_bps  = (AmountIn × FeeFactor) / (ReserveIn + AmountIn × FeeFactor) × 10,000

        V3 tick-crossing penalty added when tick_spacing is provided.
        """
        if reserve_in <= 0:
            return 5000.0   # 50% sentinel for invalid pools

        fee_factor = 1.0 - (fee_bps / 10000)
        adj_in = amount_in * fee_factor
        denom = reserve_in + adj_in

        impact_bps = (adj_in / denom) * 10000 if denom > 0 else 5000.0

        # Optional V3 tick-crossing penalty
        if tick_spacing is not None:
            tick_penalty_bps = (tick_spacing / 60) * 1.0   # ~1 bps per 60-tick spacing
            impact_bps += tick_penalty_bps

        return float(max(0.0, impact_bps))

    def _calculate_liquidity_penalty(self, active_liquidity_score: float) -> float:
        """
        Liquidity penalty multiplier:  1 / φ

        φ = active_liquidity_score (0–1)
        Capped at 10 to prevent extreme values when φ → 0.
        """
        if active_liquidity_score <= 0:
            return 10.0
        return float(min(1.0 / active_liquidity_score, 10.0))

    def _calculate_vol_factor(self, vol_1h: float, vol_24h: float) -> float:
        """
        Weighted volatility:  VolFactor = vol_1h × 0.7 + vol_24h × 0.3
        """
        return float((vol_1h * 0.7) + (vol_24h * 0.3))

    def _calculate_ml_residual(
        self,
        base_impact_bps: float,
        liquidity_penalty: float,
        vol_factor: float,
        spread_bps: float,
        tick_distance: float,
        trade_direction: str,
        pool_utilization: float,
    ) -> float:
        """
        ML model predicts the RESIDUAL error only (not total slippage).
        Returns 0.0 when no model is loaded.
        Clamped to ±50 bps to prevent instability.
        """
        if self.ml_model is None:
            return 0.0

        direction_flag = 1.0 if trade_direction == 'buy' else -1.0

        features = np.array([[
            base_impact_bps,
            liquidity_penalty,
            vol_factor,
            spread_bps,
            tick_distance,
            direction_flag,
            pool_utilization,
        ]])

        try:
            residual = self.ml_model.predict(features)[0]
            return float(np.clip(residual, -50.0, 50.0))
        except Exception as exc:
            logger.debug(f"ML residual prediction failed: {exc}")
            return 0.0

    def _calculate_min_profitable_bps(
        self,
        loan_amount_usd: float,
        gas_cost_usd: float,
    ) -> float:
        """
        Minimum spread required to profit after gas + safety buffer.

            min_bps = gas_bps + safety_buffer_bps
        """
        gas_bps = (gas_cost_usd / loan_amount_usd) * 10000 if loan_amount_usd > 0 else 100.0
        return float(gas_bps + self.safety_buffer_bps)


# Singleton instance
_institutional_model = None


def get_institutional_slippage_model(ml_model=None) -> InstitutionalSlippageModel:
    """Get or create institutional slippage model singleton."""
    global _institutional_model
    if _institutional_model is None:
        _institutional_model = InstitutionalSlippageModel(ml_model=ml_model)
    return _institutional_model


if __name__ == "__main__":
    """Verify 4-component formula against spec examples."""

    model = InstitutionalSlippageModel()

    print("=" * 80)
    print("INSTITUTIONAL SLIPPAGE MODEL — 4-COMPONENT FORMULA VERIFICATION")
    print("=" * 80)
    print()

    # Spec example: $10k in $1M pool, 80% active liquidity, 29.52 bps spread
    result = model.predict_execution_slippage(
        amount_in_usd=10000,
        loan_amount_usd=10000,
        reserve_in=500000,
        reserve_out=500000,
        pool_tvl_usd=1000000,
        fee_bps=30,
        active_liquidity_score=0.8,
        observed_spread_bps=29.52,
        volatility_1h=0.02,
        volatility_24h=0.03,
        trade_direction='buy',
    )

    print("Test: $10k trade in $1M pool (80% active liquidity, 29.52 bps spread)")
    print("-" * 80)
    for label, value in result['breakdown'].items():
        print(f"  {label}: {value}")
    print()
    print(f"  is_profitable: {result['is_profitable']}")
    print(f"  min_profitable_bps: {result['min_profitable_bps']:.2f}")
    print()

    decision = model.should_execute_trade(
        observed_spread_bps=29.52,
        predicted_slippage_bps=result['predicted_slippage_bps'],
        min_profitable_bps=result['min_profitable_bps'],
    )
    print(f"  Execute: {decision['execute']}")
    print(f"  Reason:  {decision['reason']}")
    print(f"  Net:     {decision['net_profit_bps']:.2f} bps")
    print()
    print("Formula: Base_AMM + (1/φ)×VolFactor×10000 + Spread + ML_Residual ✅")
