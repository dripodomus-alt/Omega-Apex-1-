"""
APEX OMEGA - 90-Day ROI Predictor
Flash Loan Arbitrage Revenue Forecasting Engine

Capital Model: INFINITE (Flash Loan Funded)
Constraints: Flash loan fees, gas costs, pool liquidity, execution success rate
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import statistics

logger = logging.getLogger(__name__)

# Constants
AAVE_FLASH_FEE_BPS = 9  # 0.09% Aave flash loan fee
BALANCER_FLASH_FEE_BPS = 0  # Balancer flash loans are FREE
DEFAULT_GAS_COST_USD = 0.02  # Average $0.02 per transaction on Polygon
MAX_GAS_COST_USD = 0.10  # Spike scenario
DEFAULT_CAPTURE_RATE = 0.40  # Assume 40% of opportunities captured (mempool competition)
DEFAULT_SUCCESS_RATE = 0.85  # 85% successful execution (15% fail due to frontrun/slippage)
OPERATING_HOURS_PER_DAY = 24  # Bot runs 24/7
FORECAST_DAYS = 90  # 90-day forecast period
BASIS_POINTS_DIVISOR = 10000  # For converting basis points to percentage


class FlashLoanROIPredictor:
    """
    Predicts 90-day ROI for flash loan arbitrage based on:
    - Current live spread opportunities
    - Historical execution patterns
    - Market volatility modeling
    - Gas cost projections
    """
    
    def __init__(self):
        # Flash loan parameters
        self.aave_flash_fee_bps = AAVE_FLASH_FEE_BPS
        self.balancer_flash_fee_bps = BALANCER_FLASH_FEE_BPS
        
        # Polygon gas costs (in USD)
        self.avg_gas_cost_usd = DEFAULT_GAS_COST_USD
        self.max_gas_cost_usd = MAX_GAS_COST_USD
        
        # Execution assumptions
        self.capture_rate = DEFAULT_CAPTURE_RATE
        self.success_rate = DEFAULT_SUCCESS_RATE
        
        # Operating hours
        self.hours_per_day = OPERATING_HOURS_PER_DAY
        
    def calculate_net_profit(
        self,
        gross_profit_usd: float,
        loan_amount_usd: float,
        flash_loan_provider: str = "aave"
    ) -> float:
        """
        Calculate net profit after flash loan fees and gas.
        
        Args:
            gross_profit_usd: Raw arbitrage profit before fees
            loan_amount_usd: Flash loan size
            flash_loan_provider: "aave" or "balancer"
            
        Returns:
            Net profit in USD
        """
        # Flash loan fee
        if flash_loan_provider == "balancer":
            flash_fee = 0  # Balancer flash loans are FREE
        else:
            flash_fee = (loan_amount_usd * self.aave_flash_fee_bps) / BASIS_POINTS_DIVISOR
        
        # Gas cost
        gas_cost = self.avg_gas_cost_usd
        
        # Net profit = Gross - Flash Fee - Gas
        net_profit = gross_profit_usd - flash_fee - gas_cost
        
        return net_profit
    
    def predict_90_day_roi(
        self,
        current_spreads: List[Dict],
        historical_daily_opportunities: int = None
    ) -> Dict:
        """
        Generate 90-day ROI forecast based on current market conditions.
        
        Args:
            current_spreads: List of current spread opportunities from arbitrage engine
            historical_daily_opportunities: Average daily opportunities (if available)
            
        Returns:
            Comprehensive ROI forecast with multiple scenarios
        """
        logger.info("🔮 Generating 90-day flash loan ROI forecast...")
        
        # STEP 1: Analyze current executable opportunities
        executable_spreads = [
            s for s in current_spreads 
            if s.get('flashLoan', {}).get('isExecutable', False)
        ]
        
        if not executable_spreads:
            logger.warning("⚠️  No executable spreads currently - using conservative estimates")
            # Use minimal baseline estimate
            avg_profit_per_opp = 5.0  # $5 average profit per opportunity
            daily_opportunities = 10  # Conservative: 10 opportunities per day
        else:
            # Calculate average profit per opportunity from current data
            profits = []
            for spread in executable_spreads:
                gross_profit = spread['flashLoan'].get('netProfitUsd', 0)
                loan_amount = spread['flashLoan'].get('loanAmountUsd', 10000)
                
                # Calculate net profit after fees
                net_profit = self.calculate_net_profit(gross_profit, loan_amount)
                if net_profit > 0:
                    profits.append(net_profit)
            
            if profits:
                avg_profit_per_opp = statistics.mean(profits)
                median_profit_per_opp = statistics.median(profits)
                max_profit_per_opp = max(profits)
            else:
                avg_profit_per_opp = 5.0
                median_profit_per_opp = 5.0
                max_profit_per_opp = 20.0
            
            # Estimate daily opportunities
            # If we have historical data, use it; otherwise extrapolate from current snapshot
            if historical_daily_opportunities:
                daily_opportunities = historical_daily_opportunities
            else:
                # Assume current snapshot represents ~1 hour of opportunities
                # Scale to 24 hours, apply capture rate
                snapshot_opportunities = len(executable_spreads)
                daily_opportunities = snapshot_opportunities * 24 * self.capture_rate
        
        logger.info(f"📊 Average profit per opportunity: ${avg_profit_per_opp:.2f}")
        logger.info(f"📊 Estimated daily opportunities: {daily_opportunities:.1f}")
        
        # STEP 2: Calculate 90-day projections
        days = FORECAST_DAYS
        
        # Expected Scenario (base case)
        expected_daily_profit = (
            daily_opportunities * 
            avg_profit_per_opp * 
            self.success_rate
        )
        expected_90day_profit = expected_daily_profit * days
        
        # Conservative Scenario (25th percentile)
        # - Lower capture rate (30% vs 40%)
        # - Lower success rate (75% vs 85%)
        # - Higher gas costs
        conservative_daily_opportunities = daily_opportunities * 0.75
        conservative_profit_per_opp = avg_profit_per_opp * 0.7  # Account for worse pricing
        conservative_daily_profit = (
            conservative_daily_opportunities * 
            conservative_profit_per_opp * 
            0.75  # 75% success rate
        )
        conservative_90day_profit = conservative_daily_profit * days
        
        # Optimistic Scenario (75th percentile)
        # - Higher capture rate (60% vs 40%)
        # - Higher success rate (95% vs 85%)
        # - More opportunities during volatile periods
        optimistic_daily_opportunities = daily_opportunities * 1.5  # 50% more opportunities
        optimistic_profit_per_opp = avg_profit_per_opp * 1.3  # Better execution
        optimistic_daily_profit = (
            optimistic_daily_opportunities * 
            optimistic_profit_per_opp * 
            0.95  # 95% success rate
        )
        optimistic_90day_profit = optimistic_daily_profit * days
        
        # STEP 3: Build detailed forecast
        forecast = {
            "timestamp": datetime.now().isoformat(),
            "forecast_period_days": days,
            "model": "flash_loan_arbitrage",
            "capital_required": 0,  # Flash loans = infinite capital
            
            # Current market snapshot
            "current_snapshot": {
                "executable_opportunities": len(executable_spreads),
                "avg_profit_per_opp": round(avg_profit_per_opp, 2),
                "median_profit_per_opp": round(median_profit_per_opp, 2) if 'median_profit_per_opp' in locals() else 0,
                "max_profit_per_opp": round(max_profit_per_opp, 2) if 'max_profit_per_opp' in locals() else 0,
            },
            
            # Assumptions
            "assumptions": {
                "daily_opportunities": round(daily_opportunities, 1),
                "capture_rate": f"{self.capture_rate * 100:.0f}%",
                "success_rate": f"{self.success_rate * 100:.0f}%",
                "avg_gas_cost_usd": self.avg_gas_cost_usd,
                "aave_flash_fee": f"{self.aave_flash_fee_bps / 100:.2f}%",
                "balancer_flash_fee": "0% (FREE)",
                "operating_hours": "24/7"
            },
            
            # Three scenarios
            "scenarios": {
                "conservative": {
                    "daily_profit_usd": round(conservative_daily_profit, 2),
                    "weekly_profit_usd": round(conservative_daily_profit * 7, 2),
                    "monthly_profit_usd": round(conservative_daily_profit * 30, 2),
                    "90day_total_usd": round(conservative_90day_profit, 2),
                    "assumptions": "Lower capture (30%), success (75%), worse pricing"
                },
                "expected": {
                    "daily_profit_usd": round(expected_daily_profit, 2),
                    "weekly_profit_usd": round(expected_daily_profit * 7, 2),
                    "monthly_profit_usd": round(expected_daily_profit * 30, 2),
                    "90day_total_usd": round(expected_90day_profit, 2),
                    "assumptions": "Base case: Current market conditions maintained"
                },
                "optimistic": {
                    "daily_profit_usd": round(optimistic_daily_profit, 2),
                    "weekly_profit_usd": round(optimistic_daily_profit * 7, 2),
                    "monthly_profit_usd": round(optimistic_daily_profit * 30, 2),
                    "90day_total_usd": round(optimistic_90day_profit, 2),
                    "assumptions": "Higher capture (60%), success (95%), more volatility"
                }
            },
            
            # Confidence & risk factors
            "confidence": {
                "level": "MEDIUM",
                "reasoning": [
                    "Based on current live market data" if executable_spreads else "Limited current opportunities - using conservative estimates",
                    "Flash loan model eliminates capital risk",
                    "Polygon gas costs are low and predictable",
                    "MEV competition and frontrunning create uncertainty",
                    "Market volatility can increase opportunities significantly"
                ]
            },
            
            # Risk factors
            "risks": [
                "Mempool competition (frontrunning bots)",
                "Gas price spikes during network congestion",
                "Smart contract bugs or exploits",
                "Pool liquidity changes",
                "RPC endpoint failures",
                "Market volatility reduction (fewer opportunities)"
            ],
            
            # Break-even analysis (not applicable for flash loans, but useful for gas budget)
            "monthly_gas_budget": {
                "expected_trades_per_month": round(daily_opportunities * 30 * self.success_rate, 0),
                "total_gas_cost_usd": round(daily_opportunities * 30 * self.success_rate * self.avg_gas_cost_usd, 2),
                "note": "Only operating cost - no capital lock-up"
            }
        }
        
        logger.info(f"✅ 90-day ROI Forecast Generated")
        logger.info(f"   Expected: ${expected_90day_profit:,.2f}")
        logger.info(f"   Range: ${conservative_90day_profit:,.2f} - ${optimistic_90day_profit:,.2f}")
        
        return forecast
    
    def generate_daily_breakdown(self, forecast: Dict) -> List[Dict]:
        """
        Generate day-by-day profit projection for visualization.
        """
        expected_daily = forecast['scenarios']['expected']['daily_profit_usd']
        
        # Add some realistic variance (±15%)
        import random
        random.seed(42)  # Reproducible
        
        daily_projections = []
        cumulative = 0
        
        for day in range(1, 91):
            # Add daily variance
            variance = random.uniform(-0.15, 0.15)
            daily_profit = expected_daily * (1 + variance)
            cumulative += daily_profit
            
            daily_projections.append({
                "day": day,
                "date": (datetime.now() + timedelta(days=day)).strftime("%Y-%m-%d"),
                "daily_profit_usd": round(daily_profit, 2),
                "cumulative_profit_usd": round(cumulative, 2)
            })
        
        return daily_projections


# Singleton instance
predictor = FlashLoanROIPredictor()


def get_roi_forecast(current_spreads: List[Dict]) -> Dict:
    """
    Convenience function to get ROI forecast.
    """
    return predictor.predict_90_day_roi(current_spreads)
