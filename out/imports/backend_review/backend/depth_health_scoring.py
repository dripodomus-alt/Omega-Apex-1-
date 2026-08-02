"""
Pool Depth & Health Scoring
Institutional-grade pool quality metrics

Metrics:
1. Gross Depth: √(R_in · R_out) · (1 - fee)
2. Slippage Impact: trade_size / reserve
3. Depth Score: gross_depth · (1 - slippage_impact) with floor at 500
4. Health Index: depth · volume / (tvl · age_penalty)
5. Path Liquidity Factor: geometric mean of leg depth scores

Gates:
- Slippage ≤ 40 bps per leg
- Depth score ≥ 500
- Health index ≥ 0.75
"""

import math
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class PoolMetrics:
    """Pool quality metrics"""
    gross_depth: float
    slippage_impact_bps: float
    depth_score: float
    health_index: float
    is_valid: bool
    rejection_reason: Optional[str] = None


class DepthHealthScorer:
    """
    Calculate pool depth and health metrics for arbitrage filtering
    """
    
    # Quality gates (from SSOT)
    MAX_SLIPPAGE_BPS = 40  # 0.4% max slippage per leg
    MIN_DEPTH_SCORE = 500
    MIN_HEALTH_INDEX = 0.75
    BLOCKS_PER_DAY = 43200  # Polygon: 2-second blocks
    
    def calculate_pool_metrics(
        self,
        reserve_in: float,
        reserve_out: float,
        fee_bps: int,
        trade_amount: float,
        tvl_usd: float = 0,
        volume_24h_usd: float = 0,
        age_blocks: int = 0
    ) -> PoolMetrics:
        """
        Calculate comprehensive pool metrics
        
        Args:
            reserve_in: Input token reserve (normalized)
            reserve_out: Output token reserve (normalized)
            fee_bps: Pool fee in basis points
            trade_amount: Trade size in input token units
            tvl_usd: Total value locked (optional)
            volume_24h_usd: 24h volume (optional)
            age_blocks: Pool age in blocks (optional)
            
        Returns:
            PoolMetrics with all quality indicators
        """
        
        # 1. Gross depth
        fee_decimal = fee_bps / 10_000
        gross_depth = math.sqrt(reserve_in * reserve_out) * (1 - fee_decimal)
        
        # 2. Slippage impact
        if reserve_in > 0:
            trade_after_fee = trade_amount * (1 - fee_decimal)
            slippage_impact_bps = 10_000 * trade_after_fee / reserve_in
        else:
            slippage_impact_bps = 10_000  # Max penalty
        
        # 3. Depth score (with floor at 500)
        slippage_impact_pct = slippage_impact_bps / 100
        depth_score = gross_depth * max(0, 1 - slippage_impact_pct / 100)
        depth_score = max(depth_score, self.MIN_DEPTH_SCORE if depth_score > 0 else 0)
        
        # 4. Health index
        if tvl_usd > 0 and volume_24h_usd > 0:
            age_penalty = 1 + age_blocks / self.BLOCKS_PER_DAY
            health_index = (depth_score * volume_24h_usd) / (tvl_usd * age_penalty)
        else:
            # Fallback: use depth score only
            health_index = depth_score / 1000  # Normalize to ~1.0 for good pools
        
        # Validation
        is_valid = True
        rejection_reason = None
        
        if slippage_impact_bps > self.MAX_SLIPPAGE_BPS:
            is_valid = False
            rejection_reason = f"Slippage {slippage_impact_bps:.2f} bps > {self.MAX_SLIPPAGE_BPS} bps"
        elif depth_score < self.MIN_DEPTH_SCORE:
            is_valid = False
            rejection_reason = f"Depth {depth_score:.0f} < {self.MIN_DEPTH_SCORE}"
        elif health_index < self.MIN_HEALTH_INDEX and tvl_usd > 0:
            is_valid = False
            rejection_reason = f"Health {health_index:.2f} < {self.MIN_HEALTH_INDEX}"
        
        return PoolMetrics(
            gross_depth=gross_depth,
            slippage_impact_bps=slippage_impact_bps,
            depth_score=depth_score,
            health_index=health_index,
            is_valid=is_valid,
            rejection_reason=rejection_reason
        )
    
    def calculate_path_liquidity_factor(
        self,
        depth_scores: List[float]
    ) -> float:
        """
        Calculate path liquidity factor (geometric mean of normalized depth scores)
        
        Formula: (Π min(1, depth_score_i / 1500))^(1/n)
        
        Args:
            depth_scores: List of depth scores for each leg
            
        Returns:
            Path liquidity factor (0.0 to 1.0)
        """
        if not depth_scores or any(d <= 0 for d in depth_scores):
            return 0.0
        
        # Normalize each score to [0, 1] with 1500 as target
        normalized = [min(1.0, score / 1500) for score in depth_scores]
        
        # Geometric mean
        product = 1.0
        for norm in normalized:
            product *= norm
        
        n = len(normalized)
        path_factor = product ** (1 / n) if n > 0 else 0.0
        
        return path_factor
    
    def depth_multiplier(
        self,
        depth_score: float,
        base_fee_gwei: float = 60
    ) -> float:
        """
        Calculate depth multiplier for optimal sizing
        
        Formula: min(1, depth_score/1500) · (1 - 0.3·base_fee/400)
        
        Args:
            depth_score: Pool depth score
            base_fee_gwei: Current base fee
            
        Returns:
            Multiplier (typically 0.4 to 1.0)
        """
        depth_factor = min(1.0, depth_score / 1500)
        gas_factor = max(0.4, 1 - 0.3 * base_fee_gwei / 400)
        
        return depth_factor * gas_factor
    
    def validate_two_leg_path(
        self,
        pool1_reserve_in: float,
        pool1_reserve_out: float,
        pool1_fee_bps: int,
        pool2_reserve_in: float,
        pool2_reserve_out: float,
        pool2_fee_bps: int,
        trade_size: float,
        pool1_tvl: float = 0,
        pool2_tvl: float = 0
    ) -> Tuple[bool, str, Dict[str, PoolMetrics]]:
        """
        Validate entire 2-leg arbitrage path
        
        Returns:
            (is_valid, reason, metrics_dict)
        """
        
        # Leg 1 metrics
        leg1_metrics = self.calculate_pool_metrics(
            reserve_in=pool1_reserve_in,
            reserve_out=pool1_reserve_out,
            fee_bps=pool1_fee_bps,
            trade_amount=trade_size,
            tvl_usd=pool1_tvl
        )
        
        if not leg1_metrics.is_valid:
            return False, f"Leg 1: {leg1_metrics.rejection_reason}", {
                "leg1": leg1_metrics,
                "leg2": None
            }
        
        # Leg 2 uses output from leg 1
        leg1_output = (trade_size * (1 - pool1_fee_bps / 10_000) * pool1_reserve_out) / \
                      (pool1_reserve_in + trade_size * (1 - pool1_fee_bps / 10_000))
        
        leg2_metrics = self.calculate_pool_metrics(
            reserve_in=pool2_reserve_in,
            reserve_out=pool2_reserve_out,
            fee_bps=pool2_fee_bps,
            trade_amount=leg1_output,
            tvl_usd=pool2_tvl
        )
        
        if not leg2_metrics.is_valid:
            return False, f"Leg 2: {leg2_metrics.rejection_reason}", {
                "leg1": leg1_metrics,
                "leg2": leg2_metrics
            }
        
        # Path liquidity check
        path_factor = self.calculate_path_liquidity_factor([
            leg1_metrics.depth_score,
            leg2_metrics.depth_score
        ])
        
        if path_factor < 0.5:
            return False, f"Path liquidity too low: {path_factor:.3f}", {
                "leg1": leg1_metrics,
                "leg2": leg2_metrics
            }
        
        return True, "Valid", {
            "leg1": leg1_metrics,
            "leg2": leg2_metrics
        }


# Global instance
_depth_scorer = None

def get_depth_scorer() -> DepthHealthScorer:
    """Get or create depth scorer singleton"""
    global _depth_scorer
    if _depth_scorer is None:
        _depth_scorer = DepthHealthScorer()
    return _depth_scorer


# Convenience functions
def calculate_depth_score(
    reserve_in: float,
    reserve_out: float,
    fee_bps: int,
    trade_amount: float
) -> float:
    """Quick depth score calculation"""
    scorer = get_depth_scorer()
    metrics = scorer.calculate_pool_metrics(
        reserve_in, reserve_out, fee_bps, trade_amount
    )
    return metrics.depth_score


def is_pool_valid(
    reserve_in: float,
    reserve_out: float,
    fee_bps: int,
    trade_amount: float
) -> Tuple[bool, str]:
    """Quick pool validation"""
    scorer = get_depth_scorer()
    metrics = scorer.calculate_pool_metrics(
        reserve_in, reserve_out, fee_bps, trade_amount
    )
    return metrics.is_valid, metrics.rejection_reason or "Valid"
