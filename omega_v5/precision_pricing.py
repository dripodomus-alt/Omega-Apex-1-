import math
from decimal import Decimal

class PrecisionPricingEngine:
    """
    Translates Concentrated Liquidity (V3) and StableSwap (Curve) into
    standardized virtual reserves for the Bellman-Ford-Curve engine.
    """
    Q96 = 2**96

    @staticmethod
    def get_v3_virtual_reserves(sqrtPriceX96: int, liquidity: int):
        """
        Calculates r_in (token0) and r_out (token1) virtual reserves.
        Logic: Within a tick, x * y = L^2.
        x = L / sqrtP, y = L * sqrtP
        """
        if liquidity <= 0:
            return Decimal(0), Decimal(0)

        sqrtP = Decimal(sqrtPriceX96) / Decimal(PrecisionPricingEngine.Q96)
        L = Decimal(liquidity)

        # Virtual reserves for the current active tick range
        if sqrtP == 0:
            return Decimal(0), Decimal(0)
        r0_virtual = L / sqrtP
        r1_virtual = L * sqrtP

        return r0_virtual, r1_virtual

    @staticmethod
    def calculate_price_impact(amount_in: Decimal, r_in: Decimal, r_out: Decimal, fee_bps: int):
        """
        Advanced slippage calculation using the virtual constant product.
        """
        gamma = Decimal(1) - (Decimal(fee_bps) / 10000)
        amount_with_fee = amount_in * gamma
        if (r_in + amount_with_fee) == 0:
            return Decimal(0)
        amount_out = (amount_with_fee * r_out) / (r_in + amount_with_fee)

        # Marginal price after trade: (r_out - amount_out) / (r_in + amount_in)
        return amount_out