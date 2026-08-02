"""
APEX_OMEGA AMM Math Library
Exact swap calculations for all Polygon DEX protocols

Verified Protocol Support (as of April 2026):
- QuickSwap V2 (Constant Product)
- QuickSwap V3 Algebra (Concentrated Liquidity)
- Sushi cpAMM / V2 (Constant Product)
- Sushi clAMM / V3 (Concentrated Liquidity)
- Sushi Trident (Constant Product)
- Curve StableSwap (Iterative D-invariant)
- Balancer Weighted Pools (Weighted Product)

Reference: User-provided verified formulas (April 11, 2026)
"""

import math
from typing import Dict, Tuple, Optional
from decimal import Decimal, getcontext
import logging

logger = logging.getLogger(__name__)

# Set high precision for Curve iterative solving
getcontext().prec = 50


class AMMCalculator:
    """
    Exact AMM swap calculations for Polygon protocols.
    
    Uses protocol-native invariants for precise slippage prediction.
    """
    
    # ========================================================================
    # CONSTANT PRODUCT (QuickSwap V2, Sushi cpAMM/V2, Trident)
    # ========================================================================
    
    @staticmethod
    def constant_product_exact_input(
        reserve_in: float,
        reserve_out: float,
        amount_in: float,
        fee: float = 0.003  # 0.3% default
    ) -> Dict[str, float]:
        """
        Constant Product: x·y = k
        
        QuickSwap V2, Sushi cpAMM, Sushi V2, Trident constant-product
        
        Formula:
            Δx' = Δx(1-f)  [fee-adjusted input]
            Δy = (Δx' · y) / (x + Δx')  [exact output]
        
        Returns:
            {
                'amount_out': float,
                'price_impact': float,
                'execution_price': float,
                'slippage': float
            }
        """
        # Fee-adjusted input
        amount_in_after_fee = amount_in * (1 - fee)
        
        # Exact output
        amount_out = (amount_in_after_fee * reserve_out) / (reserve_in + amount_in_after_fee)
        
        # Spot price before trade
        spot_price = reserve_out / reserve_in
        
        # Average execution price
        execution_price = amount_in / amount_out if amount_out > 0 else 0
        
        # Slippage = 1 - (actual_price / spot_price)
        slippage = 1 - ((amount_out / amount_in) / spot_price) if spot_price > 0 and amount_in > 0 else 0
        
        # Price impact (alternative metric)
        new_reserve_in = reserve_in + amount_in_after_fee
        new_reserve_out = reserve_out - amount_out
        new_spot_price = new_reserve_out / new_reserve_in if new_reserve_in > 0 else 0
        price_impact = abs(new_spot_price - spot_price) / spot_price if spot_price > 0 else 0
        
        return {
            'amount_out': amount_out,
            'price_impact': price_impact,
            'execution_price': execution_price,
            'slippage': slippage,
            'spot_price': spot_price
        }
    
    @staticmethod
    def constant_product_exact_output(
        reserve_in: float,
        reserve_out: float,
        amount_out: float,
        fee: float = 0.003
    ) -> Dict[str, float]:
        """
        Constant Product exact-output:
        
        Formula:
            Δx = (x · Δy) / ((y - Δy)(1-f))
        
        Returns amount_in needed for desired amount_out.
        """
        amount_in = (reserve_in * amount_out) / ((reserve_out - amount_out) * (1 - fee))
        
        # Add 1 wei for integer EVM rounding
        amount_in += 1e-18
        
        return {
            'amount_in': amount_in,
            'slippage': AMMCalculator.constant_product_exact_input(
                reserve_in, reserve_out, amount_in, fee
            )['slippage']
        }
    
    # ========================================================================
    # CONCENTRATED LIQUIDITY (QuickSwap V3 Algebra, Sushi clAMM)
    # ========================================================================
    
    @staticmethod
    def concentrated_liquidity_exact_input(
        sqrt_price: float,  # P (current sqrt price)
        liquidity: float,   # L (active liquidity in range)
        amount_in: float,
        fee: float = 0.003,
        is_token0_in: bool = True
    ) -> Dict[str, float]:
        """
        Concentrated Liquidity (QuickSwap V3 Algebra, Sushi clAMM)
        
        Single active range (no tick crossing):
        
        Token0 in:
            Δx' = Δx(1-f)
            P' = (L·P) / (L + Δx'·P)
            Δy = L(P - P')
        
        Token1 in:
            Δy' = Δy(1-f)
            P' = P + Δy'/L
            Δx = L(1/P - 1/P')
        
        Note: This is single-range math. Real execution requires tick-walking.
        """
        amount_in_after_fee = amount_in * (1 - fee)
        
        if is_token0_in:
            # Token0 → Token1
            sqrt_price_new = (liquidity * sqrt_price) / (liquidity + amount_in_after_fee * sqrt_price)
            amount_out = liquidity * (sqrt_price - sqrt_price_new)
        else:
            # Token1 → Token0
            sqrt_price_new = sqrt_price + (amount_in_after_fee / liquidity)
            amount_out = liquidity * ((1 / sqrt_price) - (1 / sqrt_price_new))
        
        # Slippage
        spot_price = sqrt_price ** 2 if is_token0_in else 1 / (sqrt_price ** 2)
        execution_price = amount_in / amount_out if amount_out > 0 else 0
        slippage = 1 - ((amount_out / amount_in) / spot_price) if spot_price > 0 and amount_in > 0 else 0
        
        return {
            'amount_out': amount_out,
            'sqrt_price_new': sqrt_price_new,
            'slippage': slippage,
            'execution_price': execution_price,
            'warning': 'Single-range approximation. Real execution may cross ticks.'
        }
    
    # ========================================================================
    # CURVE STABLESWAP
    # ========================================================================
    
    @staticmethod
    def curve_stable_get_y(
        A: int,           # Amplification coefficient
        balances: list,   # Pool balances [x_i, x_j, ...]
        D: Decimal,       # Invariant
        i: int,           # Index of input coin
        j: int            # Index of output coin
    ) -> Decimal:
        """
        Curve StableSwap: Solve for new y iteratively.
        
        Invariant:
            A·n^n·∑x_i + D = A·D·n^n + D^(n+1) / (n^n·∏x_i)
        
        This is an iterative Newton-Raphson solve.
        """
        num_coins = len(balances)
        Ann = A * num_coins ** num_coins
        
        # Sum of all balances except j
        S = sum(Decimal(balances[k]) for k in range(num_coins) if k != j)
        
        # Initial guess
        y = D
        
        # Newton-Raphson iteration
        for _ in range(255):  # Max iterations
            y_prev = y
            
            # Calculate product of all balances except j
            P = Decimal(1)
            for k in range(num_coins):
                if k != j:
                    P *= Decimal(balances[k])
            P *= y
            
            # Newton step
            numerator = y * y + (D ** (num_coins + 1)) / (num_coins ** num_coins * P) - D * (Ann * S / Ann + D)
            denominator = 2 * y + (D ** (num_coins + 1)) / (num_coins ** num_coins * P * y) - D
            
            y = numerator / denominator
            
            # Convergence check
            if abs(y - y_prev) <= 1:
                return y
        
        raise ValueError("Curve stable swap did not converge")
    
    @staticmethod
    def curve_stable_exact_input(
        A: int,
        balances: list,
        amount_in: float,
        i: int,  # Input coin index
        j: int,  # Output coin index
        fee: float = 0.0004  # 0.04% typical Curve fee
    ) -> Dict[str, float]:
        """
        Curve StableSwap exact-input calculation.
        
        Process:
        1. Calculate invariant D
        2. Apply fee to input
        3. Add fee-adjusted input to balance[i]
        4. Solve for new balance[j] iteratively
        5. Output = old_balance[j] - new_balance[j]
        """
        num_coins = len(balances)
        
        # Convert to Decimal for precision
        balances_decimal = [Decimal(str(b)) for b in balances]
        amount_in_decimal = Decimal(str(amount_in))
        
        # Calculate D (invariant) - simplified for 2-coin case
        # For production, use exact Curve D-solving algorithm
        S = sum(balances_decimal)
        D = S  # Approximation for demo
        
        # Apply fee
        amount_in_after_fee = amount_in_decimal * (1 - Decimal(str(fee)))
        
        # Update input balance
        new_balances = balances_decimal.copy()
        new_balances[i] += amount_in_after_fee
        
        # Solve for new output balance
        try:
            new_balance_j = AMMCalculator.curve_stable_get_y(A, new_balances, D, i, j)
            amount_out = float(balances_decimal[j] - new_balance_j)
        except ValueError:
            logger.error("Curve stable calculation failed")
            amount_out = 0
        
        # Slippage
        # For stable pools, spot price ≈ 1.0
        spot_price = 1.0
        execution_price = amount_in / amount_out if amount_out > 0 else 0
        slippage = abs(execution_price - spot_price) / spot_price if spot_price > 0 else 0
        
        return {
            'amount_out': amount_out,
            'slippage': slippage,
            'execution_price': execution_price,
            'warning': 'Simplified D calculation. Use on-chain get_dy for production.'
        }
    
    # ========================================================================
    # BALANCER WEIGHTED POOLS
    # ========================================================================
    
    @staticmethod
    def balancer_weighted_exact_input(
        balance_in: float,      # B_i
        balance_out: float,     # B_o
        weight_in: float,       # w_i (normalized, e.g., 0.8 for 80%)
        weight_out: float,      # w_o
        amount_in: float,
        fee: float = 0.003      # Balancer pool fee
    ) -> Dict[str, float]:
        """
        Balancer Weighted Pool exact-input.
        
        Invariant:
            V = ∏(B_i^w_i)
        
        Formula:
            Δi' = Δi(1-f)
            Δo = B_o · [1 - (B_i / (B_i + Δi'))^(w_i/w_o)]
        
        Works for any weight ratio (80/20, 60/40, 50/50, etc.)
        """
        # Fee-adjusted input
        amount_in_after_fee = amount_in * (1 - fee)
        
        # Calculate amount out
        base = balance_in / (balance_in + amount_in_after_fee)
        exponent = weight_in / weight_out
        amount_out = balance_out * (1 - (base ** exponent))
        
        # Spot price
        spot_price = (balance_in / weight_in) / (balance_out / weight_out)
        
        # Execution price
        execution_price = amount_in / amount_out if amount_out > 0 else 0
        
        # Slippage
        slippage = 1 - ((amount_out / amount_in) / spot_price) if spot_price > 0 and amount_in > 0 else 0
        
        return {
            'amount_out': amount_out,
            'slippage': slippage,
            'execution_price': execution_price,
            'spot_price': spot_price
        }
    
    @staticmethod
    def balancer_weighted_exact_output(
        balance_in: float,
        balance_out: float,
        weight_in: float,
        weight_out: float,
        amount_out: float,
        fee: float = 0.003
    ) -> Dict[str, float]:
        """
        Balancer Weighted Pool exact-output.
        
        Formula:
            Δi = B_i · [(B_o / (B_o - Δo))^(w_o/w_i) - 1] / (1-f)
        """
        base = balance_out / (balance_out - amount_out)
        exponent = weight_out / weight_in
        amount_in = balance_in * ((base ** exponent) - 1) / (1 - fee)
        
        return {
            'amount_in': amount_in,
            'slippage': AMMCalculator.balancer_weighted_exact_input(
                balance_in, balance_out, weight_in, weight_out, amount_in, fee
            )['slippage']
        }


# ============================================================================
# PROTOCOL ROUTER (Auto-detect and use correct math)
# ============================================================================

class ProtocolRouter:
    """
    Automatically routes to correct AMM math based on DEX protocol.
    """
    
    CONSTANT_PRODUCT_DEXS = {
        'quickswap_v2',
        'sushi_v2',
        'sushi_cpamm',
        'sushi_trident'
    }
    
    CONCENTRATED_LIQUIDITY_DEXS = {
        'quickswap_v3',
        'quickswap_algebra',
        'sushi_v3',
        'sushi_clamm'
    }
    
    STABLE_DEXS = {
        'curve',
        'curve_stable'
    }
    
    WEIGHTED_DEXS = {
        'balancer',
        'balancer_weighted'
    }
    
    @classmethod
    def calculate_swap(
        cls,
        dex: str,
        pool_data: Dict,
        amount_in: float,
        **kwargs
    ) -> Dict[str, float]:
        """
        Calculate swap using correct AMM math for the protocol.
        
        Args:
            dex: Protocol identifier (e.g., 'quickswap_v2', 'sushi_clamm')
            pool_data: Pool-specific data (reserves, liquidity, weights, etc.)
            amount_in: Input amount
            **kwargs: Additional parameters (fee, etc.)
        
        Returns:
            Swap calculation result with slippage
        """
        dex_normalized = dex.lower().replace('-', '_')
        
        if dex_normalized in cls.CONSTANT_PRODUCT_DEXS:
            return AMMCalculator.constant_product_exact_input(
                reserve_in=pool_data['reserve_in'],
                reserve_out=pool_data['reserve_out'],
                amount_in=amount_in,
                fee=kwargs.get('fee', 0.003)
            )
        
        elif dex_normalized in cls.CONCENTRATED_LIQUIDITY_DEXS:
            return AMMCalculator.concentrated_liquidity_exact_input(
                sqrt_price=pool_data['sqrt_price'],
                liquidity=pool_data['liquidity'],
                amount_in=amount_in,
                fee=kwargs.get('fee', 0.003),
                is_token0_in=kwargs.get('is_token0_in', True)
            )
        
        elif dex_normalized in cls.STABLE_DEXS:
            return AMMCalculator.curve_stable_exact_input(
                A=pool_data['amplification_coefficient'],
                balances=pool_data['balances'],
                amount_in=amount_in,
                i=kwargs.get('i', 0),
                j=kwargs.get('j', 1),
                fee=kwargs.get('fee', 0.0004)
            )
        
        elif dex_normalized in cls.WEIGHTED_DEXS:
            return AMMCalculator.balancer_weighted_exact_input(
                balance_in=pool_data['balance_in'],
                balance_out=pool_data['balance_out'],
                weight_in=pool_data['weight_in'],
                weight_out=pool_data['weight_out'],
                amount_in=amount_in,
                fee=kwargs.get('fee', 0.003)
            )
        
        else:
            logger.warning(f"Unknown DEX protocol: {dex}. Falling back to constant product.")
            return AMMCalculator.constant_product_exact_input(
                reserve_in=pool_data.get('reserve_in', pool_data.get('balance_in', 0)),
                reserve_out=pool_data.get('reserve_out', pool_data.get('balance_out', 0)),
                amount_in=amount_in,
                fee=kwargs.get('fee', 0.003)
            )


# Singleton
_calculator = AMMCalculator()
_router = ProtocolRouter()


def get_amm_calculator() -> AMMCalculator:
    """Get singleton AMM calculator."""
    return _calculator


def get_protocol_router() -> ProtocolRouter:
    """Get singleton protocol router."""
    return _router
