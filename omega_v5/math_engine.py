# ==============================================================================
# math_engine.py  —  Cross-protocol invariant pricing mathematics
# Extracted from Cell 2 of notebooks/omega_v5.ipynb
# Covers: Uniswap V2, Uniswap V3, Curve StableSwap, Balancer Weighted
# ==============================================================================

from decimal import Decimal, localcontext
from typing import List

from .invariant_math import (
    quote_uniswap_v3_token0_to_1,
    quote_uniswap_v3_token1_to_0,
)


class DeFiEngineMath:
    """Pure-math AMM pricing library.  All methods are static and side-effect free."""

    @staticmethod
    def _normalize_balancer_weight(weight: Decimal) -> Decimal:
        """Return Balancer normalized weight as a 0..1 Decimal."""
        weight = Decimal(weight)
        if weight > Decimal("1"):
            weight = weight / Decimal("100")
        return weight

    @staticmethod
    def _normalize_fee(fee: Decimal) -> Decimal:
        """Accept fraction fees or bps-style values and return a 0..1 Decimal."""
        fee = Decimal(fee)
        if fee > Decimal("1"):
            fee = fee / Decimal("10000")
        return fee

    @staticmethod
    def _decimal_power(base: Decimal, exponent: Decimal) -> Decimal:
        """Decimal-native non-integer power used by Balancer weighted math."""
        if base <= 0:
            return Decimal("0")
        with localcontext() as ctx:
            ctx.prec = max(ctx.prec, 50)
            return (base.ln() * exponent).exp()

    @staticmethod
    def query_uniswap_v2(
        reserves_a: Decimal,
        reserves_b: Decimal,
        amount_in: Decimal,
        fee: Decimal = Decimal("0.003"),
    ) -> Decimal:
        """Standard Constant Product Formula: x * y = k with custom fee parameters."""
        reserves_a = Decimal(str(reserves_a))
        reserves_b = Decimal(str(reserves_b))
        amount_in = Decimal(str(amount_in))
        fee = Decimal(str(fee))

        if amount_in <= 0 or reserves_a <= 0 or reserves_b <= 0:
            return Decimal("0")
        amount_in_with_fee = amount_in * (Decimal("1") - fee)
        return (amount_in_with_fee * reserves_b) / (reserves_a + amount_in_with_fee)

    @staticmethod
    def query_uniswap_v3(
        sqrt_price_x96: Decimal,
        liquidity: Decimal,
        amount_in: Decimal,
        zero_for_one: bool,
        fee_bps: int,
        decimal_adjustment: Decimal = Decimal("1"),
    ) -> Decimal:
        """
        Calculates concentrated liquidity math for a single active tick by composing
        the canonical functions from the invariant_math module.
        """
        sqrt_price_x96 = Decimal(str(sqrt_price_x96))
        liquidity = Decimal(str(liquidity))
        amount_in = Decimal(str(amount_in))
        fee_bps = int(fee_bps)
        decimal_adjustment = Decimal(str(decimal_adjustment))

        if amount_in <= 0 or liquidity <= 0:
            return Decimal("0")

        fee_fraction = Decimal(fee_bps) / Decimal("10000")

        # Route to the correct canonical formula based on swap direction.
        if zero_for_one:
            # Token 0 -> Token 1
            return quote_uniswap_v3_token0_to_1(
                sqrt_price=sqrt_price_x96,
                liquidity=liquidity,
                amount_in_token0=amount_in,
                fee_fraction=fee_fraction,
            )
        else:
            # Token 1 -> Token 0
            return quote_uniswap_v3_token1_to_0(
                sqrt_price=sqrt_price_x96,
                liquidity=liquidity,
                amount_in_token1=amount_in,
                fee_fraction=fee_fraction,
            )

    @staticmethod
    def _get_D_curve(reserves: list[Decimal], A: Decimal) -> Decimal:
        """
        Iteratively calculates the Curve invariant D using Newton's method.
        This is the canonical method for finding the total "virtual" liquidity.
        """
        n_coins = Decimal(len(reserves))
        S = sum(reserves)
        if S == 0:
            return Decimal("0")

        D = S
        Ann = A * n_coins

        for _ in range(255):
            D_P = D
            for x in reserves:
                D_P = D_P * D / (n_coins * x)

            D_prev = D
            numerator = (Ann * S + D_P * n_coins) * D
            denominator = (Ann - 1) * D + (n_coins + 1) * D_P

            if denominator == 0:
                return Decimal("0")

            D = numerator / denominator

            if abs(D - D_prev) <= 1:  # Using raw integer precision check
                break
        return D

    @staticmethod
    def _get_y_curve(i: int, j: int, x: Decimal, reserves: list[Decimal], A: Decimal, D: Decimal) -> Decimal:
        """
        Calculates the output balance of token j for a given input x of token i.
        This is solved iteratively using Newton's method to find the root of the
        invariant equation.
        """
        n_coins = Decimal(len(reserves))
        Ann = A * n_coins

        # Create a temporary list of reserves with the input amount added.
        new_reserves = list(reserves)
        new_reserves[i] += x

        # S_ is the sum of all reserves except for the output token j
        S_ = sum(new_reserves[k] for k in range(int(n_coins)) if k != j)
        
        # Iteratively solve for y (the new balance of token j)
        y = D / n_coins
        for _ in range(255):
            y_prev = y
            
            # f(y) = y + (S_ - D) + D^(n+1)/(Ann * n^n * P * y) is not the right form.
            # The invariant is: Ann * S + D = Ann * D + D**(n+1) / (n**n * P)
            # We need to find y such that this holds for the new balances.
            # Let f(y) = Ann * (S_ + y) + D - Ann * D - (D**(n_coins + 1)) / (n_coins**n_coins * product(all other reserves) * y)
            
            P_ = y
            for k in range(int(n_coins)):
                if k != j:
                    P_ *= new_reserves[k]

            f = Ann * (S_ + y) + D - Ann * D - (D**(n_coins + 1)) / ((n_coins**n_coins) * P_)
            f_prime = Ann + (D**(n_coins + 1)) / ((n_coins**n_coins) * P_ * y)

            if f_prime == 0:
                return Decimal("0")

            y = y - f / f_prime

            if abs(y - y_prev) <= 1:
                break
        return y

    @staticmethod
    def query_curve_stable(
        reserves: List[Decimal],
        amounts_in: List[Decimal],
        i: int,
        j: int,
        A: Decimal = Decimal("100"),
        fee: Decimal = Decimal("0.0004"),
    ) -> Decimal:
        """
        Calculates the output of a Curve StableSwap trade using an iterative solver.
        This is a more precise implementation than the previous linear approximation.
        """
        with localcontext() as ctx:
            reserves = [Decimal(str(r)) for r in reserves]
            amounts_in = [Decimal(str(a)) for a in amounts_in]
            i = int(i)
            j = int(j)
            A = Decimal(str(A))
            fee = Decimal(str(fee))
            ctx.prec = 78  # Use high precision for iterative solvers
            D = DeFiEngineMath._get_D_curve(reserves, A)
            if D <= 0: return Decimal("0")
            y = DeFiEngineMath._get_y_curve(i, j, amounts_in[i], reserves, A, D)
            amount_out = (reserves[j] - y) * (Decimal("1") - fee)
            return amount_out if amount_out > 0 else Decimal("0")

    @staticmethod
    def query_balancer_weighted(
        reserves: List[Decimal],
        weights: List[Decimal],
        amount_in: Decimal,
        i: int,
        j: int,
        swap_fee: Decimal = Decimal("0.0025"),
    ) -> Decimal:
        """
        Implements Balancer Out-In Weighted Invariant formula:
        Out = BalanceOut * (1 - (BalanceIn / (BalanceIn + AmountIn*(1-Fee)))^(Wi/Wj))
        """
        weights = [DeFiEngineMath._normalize_balancer_weight(Decimal(w)) for w in weights]
        reserves = [Decimal(str(r)) for r in reserves]
        amount_in = Decimal(str(amount_in))
        i = int(i)
        j = int(j)
        swap_fee = Decimal(str(swap_fee))

        swap_fee = DeFiEngineMath._normalize_fee(swap_fee)
        if (
            amount_in <= 0
            or i < 0
            or j < 0
            or i >= len(reserves)
            or j >= len(reserves)
            or i >= len(weights)
            or j >= len(weights)
            or reserves[i] <= 0
            or reserves[j] <= 0
            or weights[i] <= 0
            or weights[j] <= 0
            or swap_fee < 0
            or swap_fee >= 1
        ):
            return Decimal("0")

        with localcontext() as ctx:
            ctx.prec = max(ctx.prec, 50)
            effective_in = amount_in * (Decimal("1") - swap_fee)
            weight_ratio = weights[i] / weights[j]
            base_ratio = reserves[i] / (reserves[i] + effective_in)
            power_term = DeFiEngineMath._decimal_power(base_ratio, weight_ratio)
            return reserves[j] * (Decimal("1") - power_term)

    @staticmethod
    def balancer_weighted_spot_price(
        reserves: List[Decimal],
        weights: List[Decimal],
        i: int,
        j: int,
    ) -> Decimal:
        """
        Balancer weighted spot price:
        spotPrice = (B_i / W_i) / (B_o / W_o)
        """
        weights = [DeFiEngineMath._normalize_balancer_weight(Decimal(w)) for w in weights]
        reserves = [Decimal(str(r)) for r in reserves]
        i = int(i)
        j = int(j)

        if (
            i < 0
            or j < 0
            or i >= len(reserves)
            or j >= len(reserves)
            or i >= len(weights)
            or j >= len(weights)
            or reserves[i] <= 0
            or reserves[j] <= 0
            or weights[i] <= 0
            or weights[j] <= 0
        ):
            return Decimal("0")
        with localcontext() as ctx:
            ctx.prec = max(ctx.prec, 50)
            return (reserves[i] / weights[i]) / (reserves[j] / weights[j])
