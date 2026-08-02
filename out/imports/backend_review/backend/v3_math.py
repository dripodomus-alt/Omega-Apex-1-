"""
UniswapV3 Concentrated Liquidity Math
True tick-based calculations for accurate V3 swaps
"""
import math
import logging
from typing import Tuple

logger = logging.getLogger(__name__)


class V3Math:
    """
    UniswapV3 concentrated liquidity mathematics
    Implements tick-based price calculations
    """
    
    # Constants
    Q96 = 2 ** 96
    Q128 = 2 ** 128
    MIN_TICK = -887272
    MAX_TICK = 887272
    MIN_SQRT_RATIO = 4295128739
    MAX_SQRT_RATIO = 1461446703485210103287273052203988822378723970342
    
    @staticmethod
    def get_sqrt_ratio_at_tick(tick: int) -> int:
        """
        Calculate sqrtPriceX96 from tick
        Formula: sqrt(1.0001^tick) * 2^96
        """
        abs_tick = abs(tick)
        
        if abs_tick > V3Math.MAX_TICK:
            raise ValueError(f"Tick {tick} out of bounds")
        
        # Use bit manipulation for efficient calculation
        ratio = 0xfffcb933bd6fad37aa2d162d1a594001 if abs_tick & 0x1 else 0x100000000000000000000000000000000
        
        if abs_tick & 0x2:
            ratio = (ratio * 0xfff97272373d413259a46990580e213a) >> 128
        if abs_tick & 0x4:
            ratio = (ratio * 0xfff2e50f5f656932ef12357cf3c7fdcc) >> 128
        if abs_tick & 0x8:
            ratio = (ratio * 0xffe5caca7e10e4e61c3624eaa0941cd0) >> 128
        if abs_tick & 0x10:
            ratio = (ratio * 0xffcb9843d60f6159c9db58835c926644) >> 128
        if abs_tick & 0x20:
            ratio = (ratio * 0xff973b41fa98c081472e6896dfb254c0) >> 128
        if abs_tick & 0x40:
            ratio = (ratio * 0xff2ea16466c96a3843ec78b326b52861) >> 128
        if abs_tick & 0x80:
            ratio = (ratio * 0xfe5dee046a99a2a811c461f1969c3053) >> 128
        if abs_tick & 0x100:
            ratio = (ratio * 0xfcbe86c7900a88aedcffc83b479aa3a4) >> 128
        if abs_tick & 0x200:
            ratio = (ratio * 0xf987a7253ac413176f2b074cf7815e54) >> 128
        if abs_tick & 0x400:
            ratio = (ratio * 0xf3392b0822b70005940c7a398e4b70f3) >> 128
        if abs_tick & 0x800:
            ratio = (ratio * 0xe7159475a2c29b7443b29c7fa6e889d9) >> 128
        if abs_tick & 0x1000:
            ratio = (ratio * 0xd097f3bdfd2022b8845ad8f792aa5825) >> 128
        if abs_tick & 0x2000:
            ratio = (ratio * 0xa9f746462d870fdf8a65dc1f90e061e5) >> 128
        if abs_tick & 0x4000:
            ratio = (ratio * 0x70d869a156d2a1b890bb3df62baf32f7) >> 128
        if abs_tick & 0x8000:
            ratio = (ratio * 0x31be135f97d08fd981231505542fcfa6) >> 128
        if abs_tick & 0x10000:
            ratio = (ratio * 0x9aa508b5b7a84e1c677de54f3e99bc9) >> 128
        if abs_tick & 0x20000:
            ratio = (ratio * 0x5d6af8dedb81196699c329225ee604) >> 128
        if abs_tick & 0x40000:
            ratio = (ratio * 0x2216e584f5fa1ea926041bedfe98) >> 128
        if abs_tick & 0x80000:
            ratio = (ratio * 0x48a170391f7dc42444e8fa2) >> 128
        
        if tick > 0:
            ratio = 0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff // ratio
        
        # Round up if needed
        sqrt_price_x96 = (ratio >> 32) + (1 if ratio % (1 << 32) > 0 else 0)
        
        return sqrt_price_x96
    
    @staticmethod
    def get_tick_at_sqrt_ratio(sqrt_price_x96: int) -> int:
        """
        Calculate tick from sqrtPriceX96
        Inverse of get_sqrt_ratio_at_tick
        """
        if sqrt_price_x96 < V3Math.MIN_SQRT_RATIO or sqrt_price_x96 > V3Math.MAX_SQRT_RATIO:
            raise ValueError(f"sqrtPrice {sqrt_price_x96} out of bounds")
        
        # Binary search for tick
        ratio = sqrt_price_x96 << 32
        
        r = ratio
        msb = 0
        
        # Find most significant bit
        f = (r > 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF) << 7
        msb = msb | f
        r = r >> f
        
        f = (r > 0xFFFFFFFFFFFFFFFF) << 6
        msb = msb | f
        r = r >> f
        
        f = (r > 0xFFFFFFFF) << 5
        msb = msb | f
        r = r >> f
        
        f = (r > 0xFFFF) << 4
        msb = msb | f
        r = r >> f
        
        f = (r > 0xFF) << 3
        msb = msb | f
        r = r >> f
        
        f = (r > 0xF) << 2
        msb = msb | f
        r = r >> f
        
        f = (r > 0x3) << 1
        msb = msb | f
        r = r >> f
        
        f = (r > 0x1)
        msb = msb | f
        
        # Calculate log2
        if msb >= 128:
            r = ratio >> (msb - 127)
        else:
            r = ratio << (127 - msb)
        
        log_2 = (int(msb) - 128) << 64
        
        for i in range(14):
            r = (r * r) >> 127
            f = r >> 128
            log_2 = log_2 | (f << (63 - i))
            r = r >> f
        
        # Convert to tick
        log_sqrt10001 = log_2 * 255738958999603826347141
        
        tick_low = (log_sqrt10001 - 3402992956809132418596140100660247210) >> 128
        tick_high = (log_sqrt10001 + 291339464771989622907027621153398088495) >> 128
        
        tick = tick_low if tick_low == tick_high else (
            tick_high if V3Math.get_sqrt_ratio_at_tick(tick_high) <= sqrt_price_x96 else tick_low
        )
        
        return int(tick)
    
    @staticmethod
    def get_amount0_delta(
        sqrt_price_a_x96: int,
        sqrt_price_b_x96: int,
        liquidity: int,
        round_up: bool = True
    ) -> int:
        """
        Calculate amount0 (token0) for a liquidity change between two prices
        """
        if sqrt_price_a_x96 > sqrt_price_b_x96:
            sqrt_price_a_x96, sqrt_price_b_x96 = sqrt_price_b_x96, sqrt_price_a_x96
        
        numerator1 = liquidity << 96
        numerator2 = sqrt_price_b_x96 - sqrt_price_a_x96
        
        if sqrt_price_a_x96 == 0:
            return 0
        
        if round_up:
            return ((numerator1 * numerator2) // sqrt_price_b_x96 + sqrt_price_a_x96 - 1) // sqrt_price_a_x96
        else:
            return (numerator1 * numerator2) // sqrt_price_b_x96 // sqrt_price_a_x96
    
    @staticmethod
    def get_amount1_delta(
        sqrt_price_a_x96: int,
        sqrt_price_b_x96: int,
        liquidity: int,
        round_up: bool = True
    ) -> int:
        """
        Calculate amount1 (token1) for a liquidity change between two prices
        """
        if sqrt_price_a_x96 > sqrt_price_b_x96:
            sqrt_price_a_x96, sqrt_price_b_x96 = sqrt_price_b_x96, sqrt_price_a_x96
        
        if round_up:
            return ((liquidity * (sqrt_price_b_x96 - sqrt_price_a_x96)) + V3Math.Q96 - 1) // V3Math.Q96
        else:
            return (liquidity * (sqrt_price_b_x96 - sqrt_price_a_x96)) // V3Math.Q96
    
    @staticmethod
    def compute_swap_step(
        sqrt_price_current_x96: int,
        sqrt_price_target_x96: int,
        liquidity: int,
        amount_remaining: int,
        fee_pips: int
    ) -> Tuple[int, int, int, int]:
        """
        Compute a single swap step
        Returns: (sqrtPriceNextX96, amountIn, amountOut, feeAmount)
        """
        zero_for_one = sqrt_price_current_x96 >= sqrt_price_target_x96
        exact_in = amount_remaining >= 0
        
        if exact_in:
            amount_remaining_less_fee = (amount_remaining * (1000000 - fee_pips)) // 1000000
            
            if zero_for_one:
                amount_in = V3Math.get_amount0_delta(
                    sqrt_price_target_x96, sqrt_price_current_x96, liquidity, True
                )
            else:
                amount_in = V3Math.get_amount1_delta(
                    sqrt_price_current_x96, sqrt_price_target_x96, liquidity, True
                )
            
            if amount_remaining_less_fee >= amount_in:
                sqrt_price_next_x96 = sqrt_price_target_x96
            else:
                sqrt_price_next_x96 = V3Math.get_next_sqrt_price_from_input(
                    sqrt_price_current_x96, liquidity, amount_remaining_less_fee, zero_for_one
                )
        else:
            if zero_for_one:
                amount_out = V3Math.get_amount1_delta(
                    sqrt_price_target_x96, sqrt_price_current_x96, liquidity, False
                )
            else:
                amount_out = V3Math.get_amount0_delta(
                    sqrt_price_current_x96, sqrt_price_target_x96, liquidity, False
                )
            
            if -amount_remaining >= amount_out:
                sqrt_price_next_x96 = sqrt_price_target_x96
            else:
                sqrt_price_next_x96 = V3Math.get_next_sqrt_price_from_output(
                    sqrt_price_current_x96, liquidity, -amount_remaining, zero_for_one
                )
        
        max_reached = sqrt_price_next_x96 == sqrt_price_target_x96
        
        if zero_for_one:
            amount_in = amount_in if (max_reached and exact_in) else V3Math.get_amount0_delta(
                sqrt_price_next_x96, sqrt_price_current_x96, liquidity, True
            )
            amount_out = amount_out if (max_reached and not exact_in) else V3Math.get_amount1_delta(
                sqrt_price_next_x96, sqrt_price_current_x96, liquidity, False
            )
        else:
            amount_in = amount_in if (max_reached and exact_in) else V3Math.get_amount1_delta(
                sqrt_price_current_x96, sqrt_price_next_x96, liquidity, True
            )
            amount_out = amount_out if (max_reached and not exact_in) else V3Math.get_amount0_delta(
                sqrt_price_current_x96, sqrt_price_next_x96, liquidity, False
            )
        
        if not exact_in and amount_out > -amount_remaining:
            amount_out = -amount_remaining
        
        if exact_in and sqrt_price_next_x96 != sqrt_price_target_x96:
            fee_amount = amount_remaining - amount_in
        else:
            fee_amount = (amount_in * fee_pips) // (1000000 - fee_pips) + 1
        
        return sqrt_price_next_x96, amount_in, amount_out, fee_amount
    
    @staticmethod
    def get_next_sqrt_price_from_input(
        sqrt_price_x96: int,
        liquidity: int,
        amount_in: int,
        zero_for_one: bool
    ) -> int:
        """Calculate next sqrt price given an input amount"""
        if zero_for_one:
            return V3Math.get_next_sqrt_price_from_amount0_rounding_up(
                sqrt_price_x96, liquidity, amount_in, True
            )
        else:
            return V3Math.get_next_sqrt_price_from_amount1_rounding_down(
                sqrt_price_x96, liquidity, amount_in, True
            )
    
    @staticmethod
    def get_next_sqrt_price_from_output(
        sqrt_price_x96: int,
        liquidity: int,
        amount_out: int,
        zero_for_one: bool
    ) -> int:
        """Calculate next sqrt price given an output amount"""
        if zero_for_one:
            return V3Math.get_next_sqrt_price_from_amount1_rounding_down(
                sqrt_price_x96, liquidity, amount_out, False
            )
        else:
            return V3Math.get_next_sqrt_price_from_amount0_rounding_up(
                sqrt_price_x96, liquidity, amount_out, False
            )
    
    @staticmethod
    def get_next_sqrt_price_from_amount0_rounding_up(
        sqrt_price_x96: int,
        liquidity: int,
        amount: int,
        add: bool
    ) -> int:
        """Calculate next price from amount0"""
        if amount == 0:
            return sqrt_price_x96
        
        numerator1 = liquidity << 96
        
        if add:
            product = amount * sqrt_price_x96
            if product // amount == sqrt_price_x96:
                denominator = numerator1 + product
                if denominator >= numerator1:
                    return (numerator1 * sqrt_price_x96 + denominator - 1) // denominator
            
            return (numerator1 + amount * sqrt_price_x96 - 1) // (numerator1 // sqrt_price_x96 + amount)
        else:
            product = amount * sqrt_price_x96
            denominator = numerator1 - product
            return (numerator1 * sqrt_price_x96 + denominator - 1) // denominator
    
    @staticmethod
    def get_next_sqrt_price_from_amount1_rounding_down(
        sqrt_price_x96: int,
        liquidity: int,
        amount: int,
        add: bool
    ) -> int:
        """Calculate next price from amount1"""
        if add:
            quotient = (amount << 96) // liquidity if amount <= 0xffffffffffffffffffffffffffffffff else (amount * V3Math.Q96) // liquidity
            return sqrt_price_x96 + quotient
        else:
            quotient = (amount << 96) // liquidity if amount <= 0xffffffffffffffffffffffffffffffff else (amount * V3Math.Q96) // liquidity
            return sqrt_price_x96 - quotient
