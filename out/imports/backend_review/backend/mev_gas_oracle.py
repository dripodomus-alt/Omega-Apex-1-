"""
EIP-1559 Gas Oracle + Optimal Tip Calculator
Institutional-grade gas cost modeling with P(fill) optimization

Components:
1. Gas cost: units · (base + tip) · 1e-9 · native_price_usd
2. EIP-1559 maxFee: (base · 2 + tip) · 1e9 Wei
3. Logistic P(fill): 1 / (1 + exp(-(tip - μ) / σ))
4. Optimal tip: argmax_tip { P(fill|tip) · max(0, P_net - gas_cost(tip)) }
"""

import math
import os
from typing import Dict, Tuple, Optional
from dataclasses import dataclass
import logging
from web3 import Web3

logger = logging.getLogger(__name__)


def _ensure_poa_middleware(w3: Web3) -> None:
    """
    Polygon (and other POA chains) emit 97-byte `extraData` in block headers,
    which web3.py refuses to decode by default. Register `ExtraDataToPOAMiddleware`
    once so `eth_feeHistory` and `eth_getBlock` succeed without warnings.

    Idempotent — safe to call multiple times.
    """
    try:
        from web3.middleware import ExtraDataToPOAMiddleware  # web3.py v7+
        # web3.py v7 middleware_onion supports `inject(..., layer=0)`.
        # Use a sentinel attribute on w3 to avoid double-registration.
        if not getattr(w3, "_apex_poa_registered", False):
            try:
                w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
            except ValueError:
                # already injected under a different name
                pass
            w3._apex_poa_registered = True
    except ImportError:
        # Older web3.py — fall back gracefully (existing try/except handles it)
        logger.debug("ExtraDataToPOAMiddleware unavailable in this web3.py version")


# Default constants
DEFAULT_GAS_UNITS = 350_000  # 2-leg arb + flash loan
POL_USD = float(os.getenv('APEX_POL_USD', '0.85'))
ETH_USD = float(os.getenv('APEX_ETH_USD', '3500.0'))


@dataclass
class GasSnapshot:
    """Current gas market snapshot"""
    base_fee_gwei: float
    tip_p25_gwei: float
    tip_p50_gwei: float
    tip_p75_gwei: float
    tip_p90_gwei: float
    block_number: int
    timestamp: int


@dataclass
class TipRecommendation:
    """Optimal tip calculation result"""
    optimal_tip_gwei: float
    p_fill: float
    expected_profit: float
    gas_cost_usd: float
    max_fee_per_gas_wei: int
    max_priority_fee_wei: int


class PFillEstimator:
    """
    Logistic P(fill) model:
    P(fill | tip) = 1 / (1 + exp(-(tip - μ) / σ))
    
    Where:
    μ = tip_p50_gwei (median tip gets ~50% fill rate)
    σ = max((tip_p75 - tip_p25) / 4, 0.05) (IQR-based spread)
    
    Calibrated so:
    - P(fill) ≈ 0.5 at p50
    - P(fill) ≈ 0.88 at p75  
    - P(fill) ≈ 0.12 at p25
    """
    
    def __init__(self, tip_p25: float, tip_p50: float, tip_p75: float):
        self.mu = tip_p50
        self.sigma = max((tip_p75 - tip_p25) / 4, 0.05)
    
    def calculate(self, tip_gwei: float) -> float:
        """Calculate P(fill) for given tip"""
        if self.sigma <= 0:
            return 0.5  # Fallback
        
        z = -(tip_gwei - self.mu) / self.sigma
        
        # Prevent overflow
        if z > 20:
            return 0.0
        if z < -20:
            return 1.0
        
        return 1.0 / (1.0 + math.exp(z))


class MEVGasOracle:
    """
    Complete gas cost + tip optimization system
    """
    
    def __init__(
        self,
        w3: Web3,
        native_price_usd: float = POL_USD,
        default_gas_units: int = DEFAULT_GAS_UNITS
    ):
        self.w3 = w3
        # Register POA middleware so eth_feeHistory / eth_getBlock work on
        # Polygon (and any other POA chain) without the 97-byte extraData warning.
        _ensure_poa_middleware(self.w3)
        self.native_price_usd = native_price_usd
        self.default_gas_units = default_gas_units
    
    def get_gas_snapshot(self) -> GasSnapshot:
        """
        Fetch current gas market snapshot via eth_feeHistory
        Falls back to eth_gasPrice if feeHistory unavailable
        """
        try:
            # Get last 20 blocks for percentile calculation
            fee_history = self.w3.eth.fee_history(
                block_count=20,
                newest_block='latest',
                reward_percentiles=[25, 50, 75, 90]
            )
            
            # Latest base fee
            base_fee_wei = fee_history['baseFeePerGas'][-1]
            base_fee_gwei = base_fee_wei / 1e9
            
            # Tip percentiles (average last 20 blocks)
            rewards = fee_history['reward']
            tip_p25_gwei = sum(r[0] for r in rewards) / len(rewards) / 1e9
            tip_p50_gwei = sum(r[1] for r in rewards) / len(rewards) / 1e9
            tip_p75_gwei = sum(r[2] for r in rewards) / len(rewards) / 1e9
            tip_p90_gwei = sum(r[3] for r in rewards) / len(rewards) / 1e9
            
            block_number = self.w3.eth.block_number
            
            return GasSnapshot(
                base_fee_gwei=base_fee_gwei,
                tip_p25_gwei=max(tip_p25_gwei, 0.5),
                tip_p50_gwei=max(tip_p50_gwei, 1.0),
                tip_p75_gwei=max(tip_p75_gwei, 2.0),
                tip_p90_gwei=max(tip_p90_gwei, 5.0),
                block_number=block_number,
                timestamp=int(self.w3.eth.get_block('latest')['timestamp'])
            )
            
        except Exception as e:
            logger.warning(f"feeHistory failed, using fallback: {e}")
            
            # Fallback to simple gas price
            gas_price_wei = self.w3.eth.gas_price
            gas_price_gwei = gas_price_wei / 1e9
            
            # Conservative estimates
            base_fee_gwei = gas_price_gwei * 0.85
            tip_p25_gwei = max(gas_price_gwei * 0.03, 0.5)
            tip_p50_gwei = max(gas_price_gwei * 0.05, 1.0)
            tip_p75_gwei = max(gas_price_gwei * 0.08, 2.0)
            tip_p90_gwei = max(gas_price_gwei * 0.12, 5.0)
            
            return GasSnapshot(
                base_fee_gwei=base_fee_gwei,
                tip_p25_gwei=tip_p25_gwei,
                tip_p50_gwei=tip_p50_gwei,
                tip_p75_gwei=tip_p75_gwei,
                tip_p90_gwei=tip_p90_gwei,
                block_number=self.w3.eth.block_number,
                timestamp=0
            )
    
    def gas_cost_usd(
        self,
        base_fee_gwei: float,
        tip_gwei: float,
        gas_units: Optional[int] = None
    ) -> float:
        """
        Calculate gas cost in USD
        Formula: gas_units · (base + tip) · 1e-9 · native_price_usd
        """
        units = gas_units or self.default_gas_units
        total_gwei = base_fee_gwei + tip_gwei
        return units * total_gwei * 1e-9 * self.native_price_usd
    
    def build_eip1559_params(
        self,
        base_fee_gwei: float,
        tip_gwei: float
    ) -> Tuple[int, int]:
        """
        Build EIP-1559 transaction parameters
        
        Returns:
            (maxFeePerGas_wei, maxPriorityFeePerGas_wei)
        """
        # maxFeePerGas = (base · 2 + tip) · 1e9
        max_fee_gwei = base_fee_gwei * 2 + tip_gwei
        max_fee_wei = int(max_fee_gwei * 1e9)
        
        # maxPriorityFee = tip · 1e9
        max_priority_wei = int(tip_gwei * 1e9)
        
        return max_fee_wei, max_priority_wei


class TipOptimizer:
    """
    Optimal tip calculator via grid search:
    
    E[profit | tip] = P(fill | tip) · max(0, P_net - gas_cost(tip))
    
    Grid: [0, 3 · tip_p90_gwei], 200 steps
    """
    
    def __init__(self, gas_oracle: MEVGasOracle):
        self.gas_oracle = gas_oracle
    
    def optimal_tip(
        self,
        snapshot: GasSnapshot,
        p_net_before_gas: float,
        gas_units: Optional[int] = None,
        n_grid_points: int = 200
    ) -> TipRecommendation:
        """
        Find optimal tip via grid search
        
        Args:
            snapshot: Current gas market snapshot
            p_net_before_gas: Net profit BEFORE gas cost
            gas_units: Gas units (defaults to oracle default)
            n_grid_points: Grid resolution
            
        Returns:
            TipRecommendation with optimal tip and expected profit
        """
        
        # P(fill) estimator
        p_fill_model = PFillEstimator(
            tip_p25=snapshot.tip_p25_gwei,
            tip_p50=snapshot.tip_p50_gwei,
            tip_p75=snapshot.tip_p75_gwei
        )
        
        # Grid search
        max_tip = snapshot.tip_p90_gwei * 3
        tip_grid = [max_tip * i / (n_grid_points - 1) for i in range(n_grid_points)]
        
        best_tip = snapshot.tip_p50_gwei
        best_expected_profit = -float('inf')
        best_p_fill = 0.5
        
        for tip in tip_grid:
            # Gas cost at this tip
            gas_cost = self.gas_oracle.gas_cost_usd(
                snapshot.base_fee_gwei,
                tip,
                gas_units
            )
            
            # Net profit after gas
            p_net_after_gas = p_net_before_gas - gas_cost
            
            # P(fill) at this tip
            p_fill = p_fill_model.calculate(tip)
            
            # Expected profit
            expected_profit = p_fill * max(0, p_net_after_gas)
            
            if expected_profit > best_expected_profit:
                best_expected_profit = expected_profit
                best_tip = tip
                best_p_fill = p_fill
        
        # Build EIP-1559 params
        max_fee_wei, max_priority_wei = self.gas_oracle.build_eip1559_params(
            snapshot.base_fee_gwei,
            best_tip
        )
        
        # Final gas cost
        final_gas_cost = self.gas_oracle.gas_cost_usd(
            snapshot.base_fee_gwei,
            best_tip,
            gas_units
        )
        
        return TipRecommendation(
            optimal_tip_gwei=best_tip,
            p_fill=best_p_fill,
            expected_profit=best_expected_profit,
            gas_cost_usd=final_gas_cost,
            max_fee_per_gas_wei=max_fee_wei,
            max_priority_fee_wei=max_priority_wei
        )


# Global instances
_oracle = None
_optimizer = None

def get_gas_oracle(w3: Optional[Web3] = None) -> MEVGasOracle:
    """Get or create gas oracle singleton"""
    global _oracle
    if _oracle is None and w3 is not None:
        _oracle = MEVGasOracle(w3)
    return _oracle

def get_tip_optimizer(w3: Optional[Web3] = None) -> TipOptimizer:
    """Get or create tip optimizer singleton"""
    global _optimizer
    if _optimizer is None and w3 is not None:
        oracle = get_gas_oracle(w3)
        _optimizer = TipOptimizer(oracle)
    return _optimizer
