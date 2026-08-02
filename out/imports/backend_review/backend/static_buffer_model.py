"""
Simple Static Buffer Slippage Model for Testing

Replaces ML + calibration with a single tunable constant
"""

from typing import Dict, Literal

BufferType = Literal['multiplier', 'fixed_bps']


class StaticBufferSlippage:
    """
    Simplified slippage model with static buffer for testing.
    
    Two modes:
    1. MULTIPLIER: predicted = exact × buffer (e.g., 1.2x)
    2. FIXED_BPS: predicted = exact + buffer (e.g., +20 bps)
    """
    
    def __init__(
        self,
        buffer_type: BufferType = 'multiplier',
        buffer_value: float = 1.15  # 15% buffer for multiplier, or bps for fixed
    ):
        """
        Initialize static buffer model.
        
        Args:
            buffer_type: 'multiplier' or 'fixed_bps'
            buffer_value: 
                - If multiplier: 1.15 = 15% buffer
                - If fixed_bps: 20 = 20 basis points buffer
        """
        self.buffer_type = buffer_type
        self.buffer_value = buffer_value
    
    def predict_slippage(
        self,
        exact_slippage: float,  # From AMM math (decimal, e.g., 0.01955)
    ) -> Dict[str, float]:
        """
        Predict slippage with static buffer.
        
        Args:
            exact_slippage: Exact AMM slippage (decimal format)
            
        Returns:
            {
                'predicted_slippage': float (decimal),
                'predicted_slippage_bps': float,
                'exact_slippage_bps': float,
                'buffer_applied': str
            }
        """
        exact_bps = exact_slippage * 10000
        
        if self.buffer_type == 'multiplier':
            predicted = exact_slippage * self.buffer_value
            buffer_desc = f"{self.buffer_value:.2f}x multiplier"
        
        elif self.buffer_type == 'fixed_bps':
            predicted = exact_slippage + (self.buffer_value / 10000)
            buffer_desc = f"+{self.buffer_value} bps addon"
        
        else:
            raise ValueError(f"Unknown buffer_type: {self.buffer_type}")
        
        predicted_bps = predicted * 10000
        
        return {
            'predicted_slippage': float(predicted),
            'predicted_slippage_bps': float(predicted_bps),
            'exact_slippage': float(exact_slippage),
            'exact_slippage_bps': float(exact_bps),
            'buffer_applied': buffer_desc,
            'buffer_type': self.buffer_type,
            'buffer_value': self.buffer_value
        }
    
    def is_trade_profitable(
        self,
        exact_slippage: float,
        spread_bps: float,
        fixed_costs_bps: float = 69.5  # DEX fees + gas + flash loan
    ) -> Dict[str, any]:
        """
        Determine if trade is profitable with static buffer.
        
        Returns:
            {
                'is_profitable': bool,
                'net_profit_bps': float,
                'predicted_slippage_bps': float,
                'total_costs_bps': float
            }
        """
        result = self.predict_slippage(exact_slippage)
        
        predicted_bps = result['predicted_slippage_bps']
        total_costs = predicted_bps + fixed_costs_bps
        net_profit = spread_bps - total_costs
        
        return {
            'is_profitable': net_profit > 0,
            'net_profit_bps': float(net_profit),
            'predicted_slippage_bps': float(predicted_bps),
            'total_costs_bps': float(total_costs),
            'spread_bps': float(spread_bps),
            'buffer_applied': result['buffer_applied']
        }


# Easy-to-use presets
def create_aggressive_buffer():
    """5% safety margin - high risk, more potential profits"""
    return StaticBufferSlippage(buffer_type='multiplier', buffer_value=1.05)

def create_balanced_buffer():
    """15% safety margin - balanced risk/reward"""
    return StaticBufferSlippage(buffer_type='multiplier', buffer_value=1.15)

def create_conservative_buffer():
    """25% safety margin - lower risk"""
    return StaticBufferSlippage(buffer_type='multiplier', buffer_value=1.25)

def create_no_buffer():
    """No buffer - use exact AMM math only"""
    return StaticBufferSlippage(buffer_type='multiplier', buffer_value=1.0)


if __name__ == "__main__":
    """Test the static buffer model"""
    
    print("="*80)
    print("STATIC BUFFER SLIPPAGE - TESTING MODULE")
    print("="*80)
    print()
    
    # Test data
    exact_slippage = 0.01955  # 195.5 bps from AMM
    spread_bps = 164  # Market opportunity
    
    print(f"Test scenario:")
    print(f"  Exact AMM slippage: {exact_slippage*10000:.1f} bps")
    print(f"  Market spread: {spread_bps} bps")
    print()
    
    # Test different strategies
    strategies = [
        ("No Buffer", create_no_buffer()),
        ("Aggressive (5%)", create_aggressive_buffer()),
        ("Balanced (15%)", create_balanced_buffer()),
        ("Conservative (25%)", create_conservative_buffer()),
    ]
    
    print("TESTING DIFFERENT BUFFERS:")
    print("-"*80)
    
    for name, model in strategies:
        result = model.is_trade_profitable(
            exact_slippage=exact_slippage,
            spread_bps=spread_bps
        )
        
        status = "✅ PROFIT" if result['is_profitable'] else "❌ LOSS"
        
        print(f"\n{name}:")
        print(f"  Buffer: {result['buffer_applied']}")
        print(f"  Predicted slippage: {result['predicted_slippage_bps']:.1f} bps")
        print(f"  Total costs: {result['total_costs_bps']:.1f} bps")
        print(f"  Net profit: {result['net_profit_bps']:+.1f} bps {status}")
    
    print()
    print("="*80)
    print("USAGE EXAMPLE")
    print("="*80)
    print()
    print("""
# Create model with custom buffer
model = StaticBufferSlippage(
    buffer_type='multiplier',  # or 'fixed_bps'
    buffer_value=1.15          # 15% multiplier or 15 bps
)

# Predict slippage
result = model.predict_slippage(exact_slippage=0.01955)
print(result['predicted_slippage_bps'])  # 224.8 bps

# Check profitability
trade = model.is_trade_profitable(
    exact_slippage=0.01955,
    spread_bps=164
)
print(trade['is_profitable'])  # False
print(trade['net_profit_bps'])  # -130.3 bps
    """)
