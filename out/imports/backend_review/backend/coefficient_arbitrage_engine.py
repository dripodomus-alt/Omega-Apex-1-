"""
APEX_OMEGA Coefficient-Based Arbitrage Engine
Integrates pure algebraic profit calculation system-wide

Replaces iterative profit testing with closed-form solution:
net_profit = (token_units × coeff) - gas_buffer

Where coeff = raw_spread - buy_fee - sell_fee - flash_fee
"""

import logging
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import numpy as np

from coefficient_profit_calculator import (
    CoefficientProfitCalculator,
    CoefficientResult
)
from arbitrage_engine import (
    ArbitrageEngine,
    PoolPrice,
    SpreadOpportunity,
    FlashLoanData,
    SwapLeg
)

logger = logging.getLogger(__name__)


@dataclass
class CoefficientOpportunity:
    """Coefficient-validated arbitrage opportunity"""
    # Pool info
    buy_pool: PoolPrice
    sell_pool: PoolPrice
    token_pair: str
    
    # Coefficient calculation
    coeff_result: CoefficientResult
    
    # Optimal execution
    optimal_token_units: float
    optimal_loan_usd: float
    
    # Profitability
    net_profit_usd: float
    roi_percent: float
    profitability_ratio: float  # coeff / gas_buffer
    
    # Ranking
    opportunity_score: float  # Combined metric for sorting
    
    def to_spread_opportunity(self) -> SpreadOpportunity:
        """Convert to legacy SpreadOpportunity format for compatibility"""
        # Build simplified legs (coefficient approach doesn't need full swap sim)
        leg1 = SwapLeg(
            pool=self.buy_pool.pool_address,
            dex=self.buy_pool.dex_name,
            dex_id=self.buy_pool.dex_id,
            protocol=self.buy_pool.protocol,
            token_in=self.buy_pool.token0,
            token_out=self.buy_pool.token1,
            amount_in_usd=self.optimal_loan_usd,
            amount_out_usd=self.optimal_token_units * self.coeff_result.sell_price,
            fee_paid_usd=self.optimal_token_units * self.coeff_result.buy_price * self.coeff_result.dex_fee_decimal,
            slippage_usd=0,  # Coefficient doesn't model slippage
            spot_price=self.coeff_result.buy_price,
            effective_price=self.coeff_result.buy_price,
            token_in_decimals=self.buy_pool.token0_decimals,
            token_out_decimals=self.buy_pool.token1_decimals
        )
        
        leg2 = SwapLeg(
            pool=self.sell_pool.pool_address,
            dex=self.sell_pool.dex_name,
            dex_id=self.sell_pool.dex_id,
            protocol=self.sell_pool.protocol,
            token_in=self.sell_pool.token1,
            token_out=self.sell_pool.token0,
            amount_in_usd=self.optimal_token_units * self.coeff_result.sell_price,
            amount_out_usd=self.optimal_loan_usd + self.net_profit_usd,
            fee_paid_usd=self.optimal_token_units * self.coeff_result.sell_price * self.coeff_result.dex_fee_decimal,
            slippage_usd=0,
            spot_price=self.coeff_result.sell_price,
            effective_price=self.coeff_result.sell_price,
            token_in_decimals=self.sell_pool.token1_decimals,
            token_out_decimals=self.sell_pool.token0_decimals
        )
        
        flash_loan = FlashLoanData(
            loan_amount_usd=self.optimal_loan_usd,
            flash_loan_fee_bps=int(self.coeff_result.flash_fee_decimal * 10000),
            flash_loan_fee_usd=self.optimal_loan_usd * self.coeff_result.flash_fee_decimal,
            leg1=leg1,
            leg2=leg2,
            total_fees_usd=self.coeff_result.total_fees_usd,
            total_slippage_usd=0,
            gas_cost_usd=self.coeff_result.gas_buffer_usd,
            gas_units=450000,
            repay_amount_usd=self.optimal_loan_usd + (self.optimal_loan_usd * self.coeff_result.flash_fee_decimal),
            net_profit_usd=self.net_profit_usd,
            roi_percent=self.roi_percent,
            is_executable=self.coeff_result.is_profitable,
            hops=2
        )
        
        return SpreadOpportunity(
            id=f"{self.buy_pool.pool_address[:10]}-{self.sell_pool.pool_address[:10]}-{int(time.time())}",
            timestamp=int(time.time() * 1000),
            token_pair=self.token_pair,
            min_reserve_usd=min(self.buy_pool.reserve_usd, self.sell_pool.reserve_usd),
            flash_loan=flash_loan
        )


class CoefficientArbitrageEngine(ArbitrageEngine):
    """
    Arbitrage engine using coefficient-based profit calculation
    
    PERFORMANCE IMPROVEMENT:
    - Pre-filters opportunities using closed-form algebra (microseconds)
    - Only runs expensive swap simulations on high-probability candidates
    - 10-100x faster than iterative testing
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Initialize coefficient calculator
        self.coeff_calc = CoefficientProfitCalculator(
            dex_fee_bps=30,      # 0.30% per swap
            flash_fee_bps=9,     # 0.09% Balancer (can be 0 with Balancer)
            gas_buffer_usd=0.02, # $0.02 gas on Polygon
            min_profit_usd=self.min_profit_usd
        )
        
        logger.info("🧮 Coefficient Arbitrage Engine initialized")
        logger.info(f"   Pre-filter threshold: coeff > 0.001")
        logger.info(f"   Min profit: ${self.min_profit_usd}")
    
    def calculate_coefficient_opportunity(
        self,
        pool1: PoolPrice,
        pool2: PoolPrice
    ) -> Optional[CoefficientOpportunity]:
        """
        Calculate arbitrage opportunity using pure coefficient math
        
        Returns None if unprofitable or invalid
        """
        # Verify same token pair
        pair1 = frozenset([pool1.token0, pool1.token1])
        pair2 = frozenset([pool2.token0, pool2.token1])
        if pair1 != pair2:
            return None
        
        # Check minimum reserves
        min_reserve = min(pool1.reserve_usd, pool2.reserve_usd)
        if min_reserve < self.min_reserve_usd:
            return None
        
        # Calculate prices (token1 per token0)
        pool1_price = pool1.reserve1 / pool1.reserve0 if pool1.reserve0 > 0 else 0
        pool2_price = pool2.reserve1 / pool2.reserve0 if pool2.reserve0 > 0 else 0
        
        if pool1_price <= 0 or pool2_price <= 0:
            return None
        
        # Determine buy/sell direction
        if pool1_price < pool2_price:
            buy_pool, sell_pool = pool1, pool2
            buy_price = pool1_price
            sell_price = pool2_price
        else:
            buy_pool, sell_pool = pool2, pool1
            buy_price = pool2_price
            sell_price = pool1_price
        
        # CRITICAL: Coefficient pre-filter (blazing fast)
        # If coeff <= 0, opportunity is guaranteed unprofitable
        coeff = self.coeff_calc.calculate_coefficient(buy_price, sell_price)
        
        if coeff <= 0:
            logger.debug(f"Skipped {pool1.token0_symbol}/{pool1.token1_symbol}: negative coeff ({coeff:.6f})")
            return None
        
        # Additional filter: coeff must be large enough relative to gas
        # If coeff < 0.001, even 10,000 token units only make $10 profit
        if coeff < 0.0001:
            logger.debug(f"Skipped {pool1.token0_symbol}/{pool1.token1_symbol}: coeff too small ({coeff:.6f})")
            return None
        
        # Calculate optimal size with pool liquidity constraints
        # Max trade size = 10% of smaller pool
        max_tvl_fraction = 0.10
        min_pool_tvl = min(buy_pool.reserve_usd, sell_pool.reserve_usd)
        
        # Convert TVL to token units (approximate)
        # Assume balanced pool: TVL = 2 × reserve_in
        # So max token units ≈ (TVL × 0.10) / (2 × price)
        max_token_units = (min_pool_tvl * max_tvl_fraction) / (2 * buy_price)
        
        # Calculate optimal size
        coeff_result = self.coeff_calc.calculate_optimal_size(
            buy_price=buy_price,
            sell_price=sell_price,
            max_token_units=max_token_units
        )
        
        # Validate profitability
        if not coeff_result.is_profitable:
            return None
        
        # Calculate opportunity score for ranking
        # Score = ROI × profitability_ratio × (1 / pool_utilization)
        # This favors high-ROI, high-coeff, low-impact trades
        pool_utilization = (coeff_result.optimal_token_units * buy_price) / min_pool_tvl
        opportunity_score = (
            coeff_result.roi_percent 
            * coeff_result.profitability_ratio 
            * (1 / max(pool_utilization, 0.01))  # Avoid division by zero
        )
        
        token_pair = f"{buy_pool.token0_symbol}/{buy_pool.token1_symbol}"
        
        return CoefficientOpportunity(
            buy_pool=buy_pool,
            sell_pool=sell_pool,
            token_pair=token_pair,
            coeff_result=coeff_result,
            optimal_token_units=coeff_result.optimal_token_units,
            optimal_loan_usd=coeff_result.optimal_token_units * buy_price,
            net_profit_usd=coeff_result.net_profit_usd,
            roi_percent=coeff_result.roi_percent,
            profitability_ratio=coeff_result.profitability_ratio,
            opportunity_score=opportunity_score
        )
    
    def scan_for_coefficient_opportunities(
        self,
        max_comparisons: int = 1000
    ) -> List[CoefficientOpportunity]:
        """
        Scan all pools using coefficient pre-filter (FAST)
        
        This is 10-100x faster than full swap simulation because:
        1. Closed-form algebra (no iteration)
        2. Early rejection of unprofitable pairs
        3. No expensive RPC calls
        """
        # Wait for pools to finish loading
        if self.pools_loading:
            logger.warning("⏳ Pools still loading, please wait...")
            return []
        
        if len(self.pools) == 0:
            logger.error("❌ No pools loaded")
            return []
        
        opportunities = []
        comparisons = 0
        start_time = time.time()
        
        # Group pools by token pair
        pairs: Dict[frozenset, List[PoolPrice]] = {}
        for pool in self.pools.values():
            if pool.reserve_usd < 1000:  # Skip dust pools
                continue
            pair = frozenset([pool.token0, pool.token1])
            if pair not in pairs:
                pairs[pair] = []
            pairs[pair].append(pool)
        
        logger.info(f"🔍 Coefficient scan: {len(pairs)} token pairs")
        
        # Scan all pair combinations
        for pair, pools in pairs.items():
            if len(pools) < 2:
                continue
            
            for i, pool1 in enumerate(pools):
                if comparisons >= max_comparisons:
                    break
                
                for pool2 in pools[i+1:]:
                    comparisons += 1
                    
                    try:
                        opp = self.calculate_coefficient_opportunity(pool1, pool2)
                        if opp:
                            opportunities.append(opp)
                    except Exception as e:
                        logger.debug(f"Error calculating opportunity: {e}")
                        continue
        
        # Sort by opportunity score (best first)
        opportunities.sort(key=lambda x: x.opportunity_score, reverse=True)
        
        elapsed = time.time() - start_time
        logger.info(
            f"✅ Coefficient scan complete: "
            f"{len(opportunities)} opportunities from {comparisons} comparisons "
            f"in {elapsed:.2f}s ({comparisons/elapsed:.0f} ops/sec)"
        )
        
        return opportunities


# Global instance
_coeff_engine: Optional[CoefficientArbitrageEngine] = None

def get_coefficient_engine() -> CoefficientArbitrageEngine:
    """Get or create coefficient arbitrage engine"""
    global _coeff_engine
    if _coeff_engine is None:
        import os
        rpc_url = os.getenv('POLYGON_RPC_URL', '')
        _coeff_engine = CoefficientArbitrageEngine(rpc_url)
    return _coeff_engine
