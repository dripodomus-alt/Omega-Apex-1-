"""
APEX_OMEGA Real Market Profitability Engine
Filters price discovery for ACTUAL executable profitable trades
"""

import logging
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from price_discovery_engine import get_price_discovery_engine, PriceQuote
from arbitrage_engine import get_arbitrage_engine
from swap_simulator import swap_simulator

logger = logging.getLogger(__name__)


@dataclass
class RealProfitOpportunity:
    """Validated profitable arbitrage opportunity"""
    # Basic info
    token_pair: str
    buy_pool_address: str
    sell_pool_address: str
    buy_dex: str
    sell_dex: str
    
    # Raw spread
    raw_spread_bps: float
    ask_price: float
    bid_price: float
    
    # Optimal execution
    optimal_loan_usd: float
    optimal_loan_token_amount: float
    
    # Detailed P&L breakdown
    leg1_input_usd: float
    leg1_output_usd: float
    leg1_fee_usd: float
    leg1_slippage_usd: float
    
    leg2_input_usd: float
    leg2_output_usd: float
    leg2_fee_usd: float
    leg2_slippage_usd: float
    
    flash_loan_fee_usd: float
    gas_cost_usd: float
    
    # Net results
    gross_profit_usd: float
    net_profit_usd: float
    roi_percent: float
    
    # Execution readiness
    is_executable: bool
    execution_confidence: str  # "HIGH", "MEDIUM", "LOW"
    risk_factors: List[str]


class RealMarketProfitabilityEngine:
    """
    Validates price discovery opportunities for REAL market profitability
    Only returns trades that will ACTUALLY make money after ALL costs
    """
    
    def __init__(self):
        self.min_net_profit_usd = 5.0  # Minimum $5 profit
        self.max_slippage_pct = 3.0    # Maximum 3% slippage per leg
        self.max_tvl_fraction = 0.10   # Max 10% of pool TVL per trade
        logger.info("💰 Real Market Profitability Engine initialized")
    
    def validate_opportunity(
        self,
        buy_quote: PriceQuote,
        sell_quote: PriceQuote,
        raw_spread_bps: float,
        loan_amount_usd: float = None
    ) -> Optional[RealProfitOpportunity]:
        """
        Validate if a price discovery opportunity is ACTUALLY profitable
        
        Uses EXACT swap math with real pool data to calculate TRUE profit
        
        Args:
            buy_quote: Pool to buy from (lowest ask)
            sell_quote: Pool to sell at (highest bid)
            raw_spread_bps: Raw spread before costs
            loan_amount_usd: Optional fixed loan amount (default: auto-optimize)
            
        Returns:
            RealProfitOpportunity if profitable, None if not
        """
        engine = get_arbitrage_engine()
        
        # Get full pool data from arbitrage engine
        buy_pool = engine.pools.get(buy_quote.pool_address)
        sell_pool = engine.pools.get(sell_quote.pool_address)
        
        if not buy_pool or not sell_pool:
            logger.debug(f"Pools not found in engine: {buy_quote.pool_address[:10]}, {sell_quote.pool_address[:10]}")
            return None
        
        # Risk checks
        risk_factors = []
        
        # Check 1: Minimum TVL
        if buy_pool.reserve_usd < 10000:
            risk_factors.append(f"Low buy pool TVL: ${buy_pool.reserve_usd:,.0f}")
        if sell_pool.reserve_usd < 10000:
            risk_factors.append(f"Low sell pool TVL: ${sell_pool.reserve_usd:,.0f}")
        
        # Check 2: Reserve balance (avoid extreme imbalances)
        buy_balance = buy_pool.reserve0 / buy_pool.reserve1 if buy_pool.reserve1 > 0 else 0
        sell_balance = sell_pool.reserve0 / sell_pool.reserve1 if sell_pool.reserve1 > 0 else 0
        
        if buy_balance > 1000 or buy_balance < 0.001:
            risk_factors.append(f"Buy pool imbalanced: {buy_balance:.2f}")
        if sell_balance > 1000 or sell_balance < 0.001:
            risk_factors.append(f"Sell pool imbalanced: {sell_balance:.2f}")
        
        # Determine optimal loan amount if not provided
        if loan_amount_usd is None:
            # Start with 1% of smaller pool's TVL
            loan_amount_usd = min(buy_pool.reserve_usd, sell_pool.reserve_usd) * 0.01
            loan_amount_usd = max(1000, min(loan_amount_usd, 50000))  # Between $1k - $50k
        
        # Check 3: Loan size vs pool TVL
        if loan_amount_usd > buy_pool.reserve_usd * self.max_tvl_fraction:
            risk_factors.append(f"Loan too large for buy pool: {loan_amount_usd/buy_pool.reserve_usd*100:.1f}% of TVL")
            return None  # This will cause excessive slippage
        
        if loan_amount_usd > sell_pool.reserve_usd * self.max_tvl_fraction:
            risk_factors.append(f"Loan too large for sell pool: {loan_amount_usd/sell_pool.reserve_usd*100:.1f}% of TVL")
            return None
        
        # Calculate token prices
        token0_price_usd = engine.calculate_token_price_usd(buy_pool, buy_pool.token0)
        token1_price_usd = engine.calculate_token_price_usd(buy_pool, buy_pool.token1)
        
        if token0_price_usd == 0 or token1_price_usd == 0:
            logger.debug(f"Cannot calculate USD prices for {buy_quote.token_pair}")
            return None
        
        # Convert loan amount to token units (normalized)
        loan_amount_token0 = loan_amount_usd / token0_price_usd
        
        # LEG 1: BUY on cheaper pool (EXACT SIMULATION)
        try:
            leg1_result = swap_simulator.simulate_swap(
                amount_in=loan_amount_token0,
                reserve_in=buy_pool.reserve0,
                reserve_out=buy_pool.reserve1,
                fee_bps=buy_pool.fee // 100,
                protocol=buy_pool.protocol,
                weight_in=buy_pool.weight0,
                weight_out=buy_pool.weight1,
                sqrt_price_x96=buy_pool.sqrt_price_x96,
                liquidity=buy_pool.liquidity,
                tick=buy_pool.tick,
                token_in_decimals=buy_pool.token0_decimals,
                token_out_decimals=buy_pool.token1_decimals
            )
        except Exception as e:
            logger.warning(f"Leg 1 simulation failed: {e}")
            return None
        
        # Check leg 1 slippage
        leg1_slippage_pct = leg1_result.slippage_pct
        if leg1_slippage_pct > self.max_slippage_pct:
            risk_factors.append(f"Leg 1 slippage too high: {leg1_slippage_pct:.2f}%")
            return None
        
        amount_token1 = leg1_result.amount_out
        
        # LEG 2: SELL on expensive pool (EXACT SIMULATION)
        # Handle token order reversal
        tokens_reversed = (
            buy_pool.token0.lower() == sell_pool.token1.lower() and
            buy_pool.token1.lower() == sell_pool.token0.lower()
        )
        
        try:
            if tokens_reversed:
                leg2_result = swap_simulator.simulate_swap(
                    amount_in=amount_token1,
                    reserve_in=sell_pool.reserve0,
                    reserve_out=sell_pool.reserve1,
                    fee_bps=sell_pool.fee // 100,
                    protocol=sell_pool.protocol,
                    weight_in=sell_pool.weight0,
                    weight_out=sell_pool.weight1,
                    sqrt_price_x96=sell_pool.sqrt_price_x96,
                    liquidity=sell_pool.liquidity,
                    tick=sell_pool.tick,
                    token_in_decimals=sell_pool.token0_decimals,
                    token_out_decimals=sell_pool.token1_decimals
                )
            else:
                leg2_result = swap_simulator.simulate_swap(
                    amount_in=amount_token1,
                    reserve_in=sell_pool.reserve1,
                    reserve_out=sell_pool.reserve0,
                    fee_bps=sell_pool.fee // 100,
                    protocol=sell_pool.protocol,
                    weight_in=sell_pool.weight1,
                    weight_out=sell_pool.weight0,
                    sqrt_price_x96=sell_pool.sqrt_price_x96,
                    liquidity=sell_pool.liquidity,
                    tick=sell_pool.tick,
                    token_in_decimals=sell_pool.token1_decimals,
                    token_out_decimals=sell_pool.token0_decimals
                )
        except Exception as e:
            logger.warning(f"Leg 2 simulation failed: {e}")
            return None
        
        # Check leg 2 slippage
        leg2_slippage_pct = leg2_result.slippage_pct
        if leg2_slippage_pct > self.max_slippage_pct:
            risk_factors.append(f"Leg 2 slippage too high: {leg2_slippage_pct:.2f}%")
            return None
        
        final_amount_token0 = leg2_result.amount_out
        
        # Convert everything to USD for P&L
        leg1_input_usd = loan_amount_usd
        leg1_output_usd = amount_token1 * token1_price_usd
        leg1_fee_usd = leg1_result.fee_paid * token0_price_usd
        leg1_slippage_usd = leg1_result.price_impact * loan_amount_usd / 100
        
        leg2_input_usd = leg1_output_usd
        leg2_output_usd = final_amount_token0 * token0_price_usd
        leg2_fee_usd = leg2_result.fee_paid * token1_price_usd
        leg2_slippage_usd = leg2_result.price_impact * leg2_input_usd / 100
        
        # Flash loan fee (Balancer = 0%, Aave = 0.05%)
        flash_loan_fee_bps = 0  # Use Balancer (free)
        flash_loan_fee_usd = loan_amount_usd * flash_loan_fee_bps / 10000
        
        # Gas cost (Polygon)
        gas_cost_usd = engine.calculate_gas_cost_usd()
        
        # Calculate profit
        gross_profit_usd = leg2_output_usd - leg1_input_usd
        net_profit_usd = gross_profit_usd - flash_loan_fee_usd - gas_cost_usd
        roi_percent = (net_profit_usd / loan_amount_usd) * 100
        
        # Profitability check
        is_executable = net_profit_usd >= self.min_net_profit_usd
        
        if not is_executable:
            logger.debug(
                f"{buy_quote.token_pair}: Raw spread {raw_spread_bps:.2f} bps → "
                f"Net profit ${net_profit_usd:.2f} (below ${self.min_net_profit_usd} threshold)"
            )
            return None
        
        # Execution confidence
        if net_profit_usd >= 20 and len(risk_factors) == 0:
            confidence = "HIGH"
        elif net_profit_usd >= 10 and len(risk_factors) <= 1:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"
        
        opportunity = RealProfitOpportunity(
            token_pair=buy_quote.token_pair,
            buy_pool_address=buy_quote.pool_address,
            sell_pool_address=sell_quote.pool_address,
            buy_dex=buy_quote.dex_name,
            sell_dex=sell_quote.dex_name,
            raw_spread_bps=raw_spread_bps,
            ask_price=buy_quote.ask_price,
            bid_price=sell_quote.bid_price,
            optimal_loan_usd=loan_amount_usd,
            optimal_loan_token_amount=loan_amount_token0,
            leg1_input_usd=leg1_input_usd,
            leg1_output_usd=leg1_output_usd,
            leg1_fee_usd=leg1_fee_usd,
            leg1_slippage_usd=leg1_slippage_usd,
            leg2_input_usd=leg2_input_usd,
            leg2_output_usd=leg2_output_usd,
            leg2_fee_usd=leg2_fee_usd,
            leg2_slippage_usd=leg2_slippage_usd,
            flash_loan_fee_usd=flash_loan_fee_usd,
            gas_cost_usd=gas_cost_usd,
            gross_profit_usd=gross_profit_usd,
            net_profit_usd=net_profit_usd,
            roi_percent=roi_percent,
            is_executable=is_executable,
            execution_confidence=confidence,
            risk_factors=risk_factors
        )
        
        logger.info(
            f"💰 PROFITABLE: {buy_quote.token_pair} | "
            f"Buy@{buy_quote.dex_name} → Sell@{sell_quote.dex_name} | "
            f"Loan ${loan_amount_usd:,.0f} → Profit ${net_profit_usd:.2f} ({roi_percent:.3f}% ROI) | "
            f"Confidence: {confidence}"
        )
        
        return opportunity
    
    def scan_for_real_profits(
        self,
        min_spread_bps: int = 20,
        min_tvl_usd: float = 10000,
        top_n: int = 20
    ) -> List[RealProfitOpportunity]:
        """
        Scan for REAL profitable opportunities (not just raw spreads)
        
        This is the production-ready function that returns ONLY trades
        that will ACTUALLY make money in the real market
        
        Args:
            min_spread_bps: Minimum raw spread to consider (default 20 = 0.20%)
            min_tvl_usd: Minimum TVL per pool (default $10k)
            top_n: Return top N opportunities by profit
            
        Returns:
            List of RealProfitOpportunity sorted by net_profit_usd
        """
        discovery = get_price_discovery_engine()
        engine = get_arbitrage_engine()
        
        # Build price matrix
        discovery.build_price_matrix(engine.pools)
        
        # Find raw spreads using price discovery
        raw_opportunities = discovery.find_arbitrage_opportunities(
            min_spread_bps=min_spread_bps,
            min_tvl_usd=min_tvl_usd
        )
        
        logger.info(f"🔍 Price Discovery found {len(raw_opportunities)} raw spreads (>{min_spread_bps} bps)")
        
        # Validate each opportunity for REAL profitability
        real_profits: List[RealProfitOpportunity] = []
        
        for buy_quote, sell_quote, spread_bps in raw_opportunities:
            validated = self.validate_opportunity(
                buy_quote=buy_quote,
                sell_quote=sell_quote,
                raw_spread_bps=spread_bps
            )
            
            if validated:
                real_profits.append(validated)
        
        # Sort by net profit (highest first)
        real_profits.sort(key=lambda x: x.net_profit_usd, reverse=True)
        
        # Return top N
        top_profits = real_profits[:top_n]
        
        logger.info(
            f"💎 REAL PROFITS: {len(top_profits)} executable opportunities "
            f"(filtered from {len(raw_opportunities)} raw spreads) | "
            f"Total potential: ${sum(o.net_profit_usd for o in top_profits):.2f}"
        )
        
        return top_profits


# Global instance
_profit_engine: Optional[RealMarketProfitabilityEngine] = None


def get_profit_engine() -> RealMarketProfitabilityEngine:
    """Get or create real market profitability engine"""
    global _profit_engine
    if _profit_engine is None:
        _profit_engine = RealMarketProfitabilityEngine()
    return _profit_engine
