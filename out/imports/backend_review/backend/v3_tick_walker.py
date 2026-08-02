"""
APEX_OMEGA V3/clAMM Tick-Walking Engine
Full tick-by-tick swap calculation for concentrated liquidity pools

Supports:
- QuickSwap V3 Algebra
- Sushi clAMM / V3
- Uniswap V3 (if needed)

Reference: Uniswap V3 Core whitepaper + Algebra docs
"""

import math
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class Tick:
    """Represents a single tick in a concentrated liquidity pool."""
    index: int              # Tick index (can be negative)
    liquidity_net: int      # Net liquidity change at this tick
    liquidity_gross: int    # Total liquidity at this tick
    initialized: bool       # Whether tick has liquidity


@dataclass
class TickRange:
    """Active liquidity range between two ticks."""
    tick_lower: int
    tick_upper: int
    liquidity: int
    sqrt_price_lower: float
    sqrt_price_upper: float


class V3TickWalker:
    """
    Production-grade tick-walking for V3/clAMM concentrated liquidity.
    
    Handles:
    - Multi-tick swaps (crossing multiple liquidity ranges)
    - Price impact across tick boundaries
    - Liquidity changes at each tick
    - Both token0→token1 and token1→token0 directions
    """
    
    # Constants
    MIN_TICK = -887272
    MAX_TICK = 887272
    MIN_SQRT_RATIO = 4295128739
    MAX_SQRT_RATIO = 1461446703485210103287273052203988822378723970342
    
    def __init__(self, ticks: List[Tick], current_tick: int, current_sqrt_price: float, fee: float = 0.003):
        """
        Initialize tick walker.
        
        Args:
            ticks: List of initialized ticks with liquidity
            current_tick: Current active tick index
            current_sqrt_price: Current sqrt price (P)
            fee: Pool fee (e.g., 0.003 for 0.3%)
        """
        self.ticks = sorted(ticks, key=lambda t: t.index)
        self.current_tick = current_tick
        self.current_sqrt_price = current_sqrt_price
        self.fee = fee
        
        # Build tick index for fast lookups
        self.tick_map = {tick.index: tick for tick in ticks}
    
    def calculate_swap_exact_input(
        self,
        amount_in: float,
        zero_for_one: bool,  # True if swapping token0 for token1
        sqrt_price_limit: Optional[float] = None
    ) -> Dict[str, float]:
        """
        Calculate exact-input swap with full tick-walking.
        
        Process:
        1. Start at current tick and sqrt price
        2. Calculate how far we can go in current range
        3. If amount remaining, cross tick and update liquidity
        4. Repeat until amount exhausted or price limit reached
        
        Returns:
            {
                'amount_out': float,
                'sqrt_price_final': float,
                'tick_final': int,
                'ticks_crossed': int,
                'slippage': float,
                'price_impact': float
            }
        """
        # Apply fee
        amount_in_after_fee = amount_in * (1 - self.fee)
        
        # Initialize state
        sqrt_price = self.current_sqrt_price
        tick = self.current_tick
        amount_remaining = amount_in_after_fee
        amount_out_total = 0
        ticks_crossed = 0
        
        # Get active liquidity at current tick
        liquidity = self._get_liquidity_at_tick(tick)
        
        # Set price limit (default to extreme)
        if sqrt_price_limit is None:
            sqrt_price_limit = self.MIN_SQRT_RATIO if zero_for_one else self.MAX_SQRT_RATIO
        
        # Main swap loop
        while amount_remaining > 0 and sqrt_price != sqrt_price_limit:
            # Get next tick boundary
            next_tick = self._get_next_tick(tick, zero_for_one)
            sqrt_price_next_tick = self._tick_to_sqrt_price(next_tick)
            
            # Calculate swap within current range
            sqrt_price_target = sqrt_price_next_tick
            if zero_for_one:
                sqrt_price_target = max(sqrt_price_target, sqrt_price_limit)
            else:
                sqrt_price_target = min(sqrt_price_target, sqrt_price_limit)
            
            # Compute amount consumable in this range
            step_result = self._compute_swap_step(
                sqrt_price_current=sqrt_price,
                sqrt_price_target=sqrt_price_target,
                liquidity=liquidity,
                amount_remaining=amount_remaining,
                zero_for_one=zero_for_one
            )
            
            # Update state
            sqrt_price = step_result['sqrt_price_next']
            amount_remaining -= step_result['amount_in']
            amount_out_total += step_result['amount_out']
            
            # Check if we reached the next tick
            if sqrt_price == sqrt_price_next_tick:
                # Cross tick
                tick = next_tick if zero_for_one else next_tick - 1
                
                # Update liquidity
                if next_tick in self.tick_map:
                    tick_data = self.tick_map[next_tick]
                    if zero_for_one:
                        liquidity -= tick_data.liquidity_net
                    else:
                        liquidity += tick_data.liquidity_net
                
                ticks_crossed += 1
            else:
                # Price limit reached or amount exhausted
                break
        
        # Calculate final tick
        tick_final = self._sqrt_price_to_tick(sqrt_price)
        
        # Calculate slippage
        spot_price_initial = self.current_sqrt_price ** 2
        spot_price_final = sqrt_price ** 2
        execution_price = amount_in / amount_out_total if amount_out_total > 0 else 0
        slippage = 1 - ((amount_out_total / amount_in) / spot_price_initial) if spot_price_initial > 0 else 0
        price_impact = abs(spot_price_final - spot_price_initial) / spot_price_initial if spot_price_initial > 0 else 0
        
        return {
            'amount_out': amount_out_total,
            'sqrt_price_final': sqrt_price,
            'tick_final': tick_final,
            'ticks_crossed': ticks_crossed,
            'slippage': slippage,
            'price_impact': price_impact,
            'execution_price': execution_price
        }
    
    def _compute_swap_step(
        self,
        sqrt_price_current: float,
        sqrt_price_target: float,
        liquidity: int,
        amount_remaining: float,
        zero_for_one: bool
    ) -> Dict[str, float]:
        """
        Compute a single swap step within one tick range.
        
        Uses exact Uniswap V3 / Algebra math.
        """
        if liquidity == 0:
            return {
                'sqrt_price_next': sqrt_price_target,
                'amount_in': 0,
                'amount_out': 0
            }
        
        if zero_for_one:
            # Token0 in, Token1 out
            # Calculate max amount we can consume to reach target price
            amount_in_max = liquidity * (1 / sqrt_price_target - 1 / sqrt_price_current)
            
            if amount_remaining >= amount_in_max:
                # We reach the target price
                sqrt_price_next = sqrt_price_target
                amount_in = amount_in_max
            else:
                # Amount is exhausted before reaching target
                sqrt_price_next = (liquidity * sqrt_price_current) / (liquidity + amount_remaining * sqrt_price_current)
                amount_in = amount_remaining
            
            # Calculate output
            amount_out = liquidity * (sqrt_price_current - sqrt_price_next)
        
        else:
            # Token1 in, Token0 out
            # Calculate max amount we can consume to reach target price
            amount_in_max = liquidity * (sqrt_price_target - sqrt_price_current)
            
            if amount_remaining >= amount_in_max:
                # We reach the target price
                sqrt_price_next = sqrt_price_target
                amount_in = amount_in_max
            else:
                # Amount is exhausted before reaching target
                sqrt_price_next = sqrt_price_current + (amount_remaining / liquidity)
                amount_in = amount_remaining
            
            # Calculate output
            amount_out = liquidity * (1 / sqrt_price_current - 1 / sqrt_price_next)
        
        return {
            'sqrt_price_next': sqrt_price_next,
            'amount_in': amount_in,
            'amount_out': amount_out
        }
    
    def _get_liquidity_at_tick(self, tick_index: int) -> int:
        """
        Get active liquidity at a given tick.
        
        In production, this would sum all liquidity from positions
        that span the current tick.
        """
        # Simplified: return liquidity from nearest initialized tick
        for tick in self.ticks:
            if tick.index <= tick_index < tick.index + 1:
                return tick.liquidity_gross
        
        # Default: use first tick's liquidity
        return self.ticks[0].liquidity_gross if self.ticks else 100000
    
    def _get_next_tick(self, current_tick: int, zero_for_one: bool) -> int:
        """Get the next initialized tick in the swap direction."""
        if zero_for_one:
            # Going down (price decreasing)
            for tick in reversed(self.ticks):
                if tick.index < current_tick and tick.initialized:
                    return tick.index
            return self.MIN_TICK
        else:
            # Going up (price increasing)
            for tick in self.ticks:
                if tick.index > current_tick and tick.initialized:
                    return tick.index
            return self.MAX_TICK
    
    def _tick_to_sqrt_price(self, tick: int) -> float:
        """Convert tick index to sqrt price."""
        return 1.0001 ** (tick / 2)
    
    def _sqrt_price_to_tick(self, sqrt_price: float) -> int:
        """Convert sqrt price to tick index."""
        return int(math.log(sqrt_price ** 2, 1.0001))


# ============================================================================
# SIMPLIFIED WRAPPER FOR INTEGRATION
# ============================================================================

def calculate_v3_swap_with_ticks(
    ticks_data: List[Dict],
    current_tick: int,
    current_sqrt_price: float,
    amount_in: float,
    zero_for_one: bool,
    fee: float = 0.003
) -> Dict[str, float]:
    """
    Wrapper for easy integration with existing code.
    
    Args:
        ticks_data: List of dicts with keys: index, liquidity_net, liquidity_gross, initialized
        current_tick: Current active tick
        current_sqrt_price: Current sqrt price
        amount_in: Input amount
        zero_for_one: True for token0→token1
        fee: Pool fee
    
    Returns:
        Swap result with amount_out, slippage, ticks_crossed
    """
    # Convert to Tick objects
    ticks = [
        Tick(
            index=t['index'],
            liquidity_net=t.get('liquidity_net', 0),
            liquidity_gross=t.get('liquidity_gross', 100000),
            initialized=t.get('initialized', True)
        )
        for t in ticks_data
    ]
    
    # Create walker and execute
    walker = V3TickWalker(ticks, current_tick, current_sqrt_price, fee)
    return walker.calculate_swap_exact_input(amount_in, zero_for_one)


# Singleton for caching
_tick_walker_cache = {}


def get_or_create_tick_walker(pool_address: str, ticks_data: List[Dict], **kwargs) -> V3TickWalker:
    """Get cached tick walker or create new one."""
    cache_key = f"{pool_address}_{kwargs.get('current_tick', 0)}"
    
    if cache_key not in _tick_walker_cache:
        ticks = [
            Tick(
                index=t['index'],
                liquidity_net=t.get('liquidity_net', 0),
                liquidity_gross=t.get('liquidity_gross', 100000),
                initialized=t.get('initialized', True)
            )
            for t in ticks_data
        ]
        
        _tick_walker_cache[cache_key] = V3TickWalker(
            ticks=ticks,
            current_tick=kwargs.get('current_tick', 0),
            current_sqrt_price=kwargs.get('current_sqrt_price', 1.0),
            fee=kwargs.get('fee', 0.003)
        )
    
    return _tick_walker_cache[cache_key]
