"""
Breakeven Guard - Gas-Aware Trade Filter

Prevents bot from chasing edges too thin to profit.
Implements VelvetOracle 2026 standard minimum profitability threshold.
"""

import logging

logger = logging.getLogger(__name__)


class BreakevenGuard:
    """
    Gas-aware breakeven filter for arbitrage opportunities.
    
    Rejects trades where:
    - Spread < (gas_cost + dex_fees + min_slippage + safety_buffer)
    """
    
    def __init__(
        self,
        gas_cost_usd: float = 0.50,  # Polygon: ~$0.50 per swap pair
        safety_buffer_bps: float = 8.0,  # 8 bps safety margin
        min_spread_bps: float = 12.0  # Absolute minimum 12 bps
    ):
        self.gas_cost_usd = gas_cost_usd
        self.safety_buffer_bps = safety_buffer_bps
        self.min_spread_bps = min_spread_bps
    
    def calculate_min_profitable_spread(
        self,
        loan_amount_usd: float,
        dex_fee_bps: float = 60.0  # 30 bps × 2 legs
    ) -> float:
        """
        Calculate minimum profitable spread in bps.
        
        Args:
            loan_amount_usd: Flash loan size
            dex_fee_bps: Total DEX fees (both legs)
            
        Returns:
            Minimum spread threshold in bps
        """
        # Gas cost as percentage of loan
        gas_bps = (self.gas_cost_usd / loan_amount_usd) * 10000 if loan_amount_usd > 0 else 100
        
        # Total minimum
        min_bps = gas_bps + dex_fee_bps + self.safety_buffer_bps
        
        # Apply absolute floor
        return max(self.min_spread_bps, min_bps)
    
    def should_execute(
        self,
        spread_bps: float,
        loan_amount_usd: float,
        predicted_slippage_bps: float,
        token_pair: str = "Unknown"
    ) -> dict:
        """
        Determine if trade should execute based on breakeven analysis.
        
        Returns:
            {
                'execute': bool,
                'reason': str,
                'min_required_bps': float,
                'net_profit_bps': float
            }
        """
        min_required = self.calculate_min_profitable_spread(loan_amount_usd)
        
        # Total costs
        total_costs_bps = predicted_slippage_bps + min_required
        
        # Net profit
        net_profit_bps = spread_bps - total_costs_bps
        
        # Decision logic
        if spread_bps < self.min_spread_bps:
            return {
                'execute': False,
                'reason': f'⚠️ Edge too thin ({spread_bps:.2f} bps < {self.min_spread_bps:.2f} bps min)',
                'min_required_bps': min_required,
                'net_profit_bps': net_profit_bps,
                'token_pair': token_pair
            }
        
        if spread_bps < min_required:
            return {
                'execute': False,
                'reason': f'⚠️ Below breakeven ({spread_bps:.2f} bps < {min_required:.2f} bps required)',
                'min_required_bps': min_required,
                'net_profit_bps': net_profit_bps,
                'token_pair': token_pair
            }
        
        if net_profit_bps <= 0:
            return {
                'execute': False,
                'reason': f'❌ Net loss after slippage ({net_profit_bps:.2f} bps)',
                'min_required_bps': min_required,
                'net_profit_bps': net_profit_bps,
                'token_pair': token_pair
            }
        
        return {
            'execute': True,
            'reason': f'✅ Profitable: {net_profit_bps:.2f} bps net',
            'min_required_bps': min_required,
            'net_profit_bps': net_profit_bps,
            'token_pair': token_pair
        }
    
    def log_rejection(self, decision: dict):
        """Log rejected trade with details."""
        logger.info(
            f"[GUARD] {decision['token_pair']}: {decision['reason']} "
            f"(min: {decision['min_required_bps']:.2f} bps)"
        )
    
    def log_approval(self, decision: dict):
        """Log approved trade with details."""
        logger.info(
            f"[GUARD] ✅ {decision['token_pair']}: {decision['reason']}"
        )


# Example usage in scanner
def apply_breakeven_guard_to_opportunities(opportunities, loan_amount_usd=10000):
    """
    Filter opportunities through breakeven guard.
    
    Args:
        opportunities: List of spreads from scanner
        loan_amount_usd: Flash loan size
        
    Returns:
        Filtered list of profitable opportunities
    """
    guard = BreakevenGuard()
    filtered = []
    
    rejected_count = {
        'too_thin': 0,
        'below_breakeven': 0,
        'net_loss': 0
    }
    
    for opp in opportunities:
        # Convert spread % to bps
        spread_bps = opp.get('spread_pct', 0) * 100
        predicted_slippage_bps = opp.get('predicted_slippage_pct', 0) * 100
        token_pair = opp.get('token_pair', 'Unknown')
        
        decision = guard.should_execute(
            spread_bps=spread_bps,
            loan_amount_usd=loan_amount_usd,
            predicted_slippage_bps=predicted_slippage_bps,
            token_pair=token_pair
        )
        
        if decision['execute']:
            guard.log_approval(decision)
            filtered.append(opp)
        else:
            guard.log_rejection(decision)
            
            # Track rejection reasons
            if 'too thin' in decision['reason']:
                rejected_count['too_thin'] += 1
            elif 'breakeven' in decision['reason']:
                rejected_count['below_breakeven'] += 1
            else:
                rejected_count['net_loss'] += 1
    
    # Summary
    logger.info(f"\n[GUARD] Breakeven Filter Results:")
    logger.info(f"  Total opportunities: {len(opportunities)}")
    logger.info(f"  ✅ Passed guard: {len(filtered)}")
    logger.info(f"  ❌ Rejected: {len(opportunities) - len(filtered)}")
    logger.info(f"     - Too thin: {rejected_count['too_thin']}")
    logger.info(f"     - Below breakeven: {rejected_count['below_breakeven']}")
    logger.info(f"     - Net loss: {rejected_count['net_loss']}")
    
    return filtered


if __name__ == "__main__":
    """Test breakeven guard"""
    
    guard = BreakevenGuard()
    
    print("="*80)
    print("BREAKEVEN GUARD TEST")
    print("="*80)
    print()
    
    # Test cases
    test_cases = [
        {'spread_bps': 3.68, 'name': 'USDC/USDT (too thin)'},
        {'spread_bps': 29.52, 'name': 'WPOL/USDC (profitable)'},
        {'spread_bps': 11.5, 'name': 'WETH/DAI (borderline)'},
        {'spread_bps': 164, 'name': 'Example from scan'},
    ]
    
    loan_amount = 10000
    
    for case in test_cases:
        spread = case['spread_bps']
        name = case['name']
        
        # Assume 2% slippage
        decision = guard.should_execute(
            spread_bps=spread,
            loan_amount_usd=loan_amount,
            predicted_slippage_bps=200,  # 2% = 200 bps
            token_pair=name
        )
        
        print(f"{name}:")
        print(f"  Spread: {spread:.2f} bps")
        print(f"  Min Required: {decision['min_required_bps']:.2f} bps")
        print(f"  Execute: {decision['execute']}")
        print(f"  Reason: {decision['reason']}")
        print(f"  Net Profit: {decision['net_profit_bps']:.2f} bps")
        print()
