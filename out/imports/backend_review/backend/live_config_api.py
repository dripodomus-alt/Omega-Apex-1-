"""
Live Configuration API - Hot-Reload System Variables
Changes take effect immediately without restart
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any
import os
import time
import logging
from execution_governance import get_minimum_net_profit_usd

logger = logging.getLogger(__name__)

router = APIRouter()

# Global config cache (hot-reloadable)
_config_cache = {}

class ConfigUpdate(BaseModel):
    """Configuration update model"""
    updates: Dict[str, Any]

@router.get("/config/variables")
async def get_config_variables():
    """Get all current system variables"""
    try:
        variables = {
            # Profit Thresholds
            'MIN_NET_PROFIT_USD': float(os.getenv('MIN_NET_PROFIT_USD', get_minimum_net_profit_usd())),
            'MIN_PROFIT_THRESHOLD': float(os.getenv('MIN_PROFIT_THRESHOLD', 0.015)),
            'MIN_EXECUTION_SPREAD_PCT': float(os.getenv('MIN_EXECUTION_SPREAD_PCT', 1.5)),
            'MIN_FLASH_LOAN_USD': float(os.getenv('MIN_FLASH_LOAN_USD', 5000)),
            
            # Gas Configuration
            'MAX_GAS_PRICE_GWEI': float(os.getenv('MAX_GAS_PRICE_GWEI', 150)),
            'STATIC_PRIORITY_FEE_GWEI': float(os.getenv('STATIC_PRIORITY_FEE_GWEI', 40)),
            'MIN_PROFIT_TO_GAS_RATIO': float(os.getenv('MIN_PROFIT_TO_GAS_RATIO', 5.0)),
            'ESTIMATED_GAS_UNITS': int(os.getenv('ESTIMATED_GAS_UNITS', 450000)),
            
            # Slippage & Risk
            'MAX_SLIPPAGE_TOLERANCE': float(os.getenv('MAX_SLIPPAGE_TOLERANCE', 0.01)),
            'MAX_SLIPPAGE_BPS': int(os.getenv('MAX_SLIPPAGE_BPS', 100)),
            'SLIPPAGE_CASCADE_PER_HOP_PCT': float(os.getenv('SLIPPAGE_CASCADE_PER_HOP_PCT', 0.01)),
            'MAX_LEG_IMPACT_PCT': float(os.getenv('MAX_LEG_IMPACT_PCT', 25.0)),
            
            # Trading Limits
            'MAX_TRADES_PER_DAY': int(os.getenv('MAX_TRADES_PER_DAY', 10)),
            'MAX_TVL_FRACTION': float(os.getenv('MAX_TVL_FRACTION', 0.05)),
            
            # Timing
            'SCAN_INTERVAL_SECONDS': int(os.getenv('SCAN_INTERVAL_SECONDS', 15)),
            'RPC_SCAN_INTERVAL_MINUTES': int(os.getenv('RPC_SCAN_INTERVAL_MINUTES', 15)),
            
            # Math Coefficients
            'KELLY_FRACTION': float(_config_cache.get('KELLY_FRACTION', 0.25)),
            'RISK_ADJUSTMENT_FACTOR': float(_config_cache.get('RISK_ADJUSTMENT_FACTOR', 1.2)),
            'VOLATILITY_MULTIPLIER': float(_config_cache.get('VOLATILITY_MULTIPLIER', 1.5)),
            'IMPACT_DECAY_RATE': float(_config_cache.get('IMPACT_DECAY_RATE', 0.95)),
            'CONFIDENCE_THRESHOLD': float(_config_cache.get('CONFIDENCE_THRESHOLD', 0.75))
        }
        
        return variables
        
    except Exception as e:
        logger.error(f"Error getting config variables: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config/update")
async def update_config_variables(updates: Dict[str, Any]):
    """
    Update system variables - HOT RELOAD (no restart needed)
    
    Changes are stored in memory cache and take effect immediately
    """
    try:
        logger.info(f"🔥 HOT-RELOAD: Updating {len(updates)} variables")
        
        # Update cache
        _config_cache.update(updates)
        
        # Update environment variables (for new reads)
        for key, value in updates.items():
            if key == 'MIN_NET_PROFIT_USD':
                value = max(float(value), get_minimum_net_profit_usd())
            os.environ[key] = str(value)
            logger.info(f"   ✓ {key} = {value}")
        
        # Trigger any necessary reconfigurations
        # (e.g., update arbitrage engine settings)
        try:
            from arbitrage_engine import get_arbitrage_engine
            engine = get_arbitrage_engine()
            
            # Update engine settings on the fly
            if 'MIN_NET_PROFIT_USD' in updates:
                engine.min_profit_usd = max(float(updates['MIN_NET_PROFIT_USD']), get_minimum_net_profit_usd())
            if 'MAX_SLIPPAGE_TOLERANCE' in updates:
                engine.max_slippage = float(updates['MAX_SLIPPAGE_TOLERANCE'])
                
            logger.info("✓ ArbitrageEngine settings updated")
        except Exception as e:
            logger.warning(f"Could not update engine settings: {e}")
        
        return {
            "success": True,
            "updated": list(updates.keys()),
            "message": f"Updated {len(updates)} variables (hot-reload active)"
        }
        
    except Exception as e:
        logger.error(f"Error updating config variables: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cross-dex-orderbook")
async def get_cross_dex_orderbook():
    """
    Get best BID/ASK prices across all DEXes for all tokens
    
    Returns aggregated order book showing:
    - Best bid (lowest buy price) and which DEX
    - Best ask (highest sell price) and which DEX
    - Spread percentage
    - 24h volume
    """
    try:
        from arbitrage_engine import get_arbitrage_engine
        engine = get_arbitrage_engine()
        
        # Get all pools
        pools = list(engine.pools.values())
        
        # Aggregate by token pair
        token_aggregates = {}
        
        for pool in pools:
            token_key = f"{pool.token0_symbol}/{pool.token1_symbol}"
            
            if token_key not in token_aggregates:
                token_aggregates[token_key] = {
                    'bids': [],  # [(price, dex_name)]
                    'asks': [],
                    'volume': 0
                }
            
            # Calculate bid/ask from pool
            # Bid = price to buy token1 with token0
            # Ask = price to sell token1 for token0
            price = pool.spot_price
            
            token_aggregates[token_key]['bids'].append((price, pool.dex_name))
            token_aggregates[token_key]['asks'].append((price, pool.dex_name))
            token_aggregates[token_key]['volume'] += pool.reserve_usd or 0
        
        # Build order book
        order_book = []
        
        for token, data in token_aggregates.items():
            if not data['bids'] or not data['asks']:
                continue
            
            # Best bid = lowest price (cheapest to buy)
            best_bid_price, best_bid_dex = min(data['bids'], key=lambda x: x[0])
            
            # Best ask = highest price (best to sell at)
            best_ask_price, best_ask_dex = max(data['asks'], key=lambda x: x[0])
            
            # Calculate spread
            spread_pct = ((best_ask_price - best_bid_price) / best_bid_price) * 100 if best_bid_price > 0 else 0
            
            order_book.append({
                'token': token,
                'bestBid': best_bid_price,
                'bidDex': best_bid_dex,
                'bestAsk': best_ask_price,
                'askDex': best_ask_dex,
                'spreadPercent': spread_pct,
                'volume24h': data['volume']  # Using TVL as proxy
            })
        
        # Sort by spread (highest first)
        order_book.sort(key=lambda x: x['spreadPercent'], reverse=True)
        
        logger.info(f"📊 Generated cross-DEX order book: {len(order_book)} pairs")
        
        return {
            "orderBook": order_book,
            "totalPairs": len(order_book),
            "timestamp": int(time.time())
        }
        
    except Exception as e:
        logger.error(f"Error generating cross-DEX order book: {e}", exc_info=True)
        return {
            "orderBook": [],
            "totalPairs": 0,
            "error": str(e)
        }


import time
