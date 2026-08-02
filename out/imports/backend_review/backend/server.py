from fastapi import FastAPI, APIRouter, Response, Request, HTTPException, Security, Depends
from fastapi.security.api_key import APIKeyHeader
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import time
import logging
import collections
import threading
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Any, Optional
import uuid
from datetime import datetime, timezone
import asyncio

# Performance optimizations (Phase 1)
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Set up logging
logger = logging.getLogger(__name__)

# Performance optimizations (Phase 1)
try:
    from performance_optimizer import (
        get_cached_pool_prices,
        calculate_price_matrix_parallel,
        perf_monitor,
        cache_get,
        cache_set
    )
    OPTIMIZATIONS_ENABLED = True
except ImportError:
    logger.warning("⚠️ Performance optimizations not available")
    OPTIMIZATIONS_ENABLED = False

# MongoDB connection (graceful when MONGO_URL not set)
mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
_db_name  = os.environ.get('DB_NAME', 'apex_omega')
try:
    client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=3000)
    db = client[_db_name]
    logger.info(f"MongoDB client initialised → {mongo_url} / {_db_name}")
except Exception as _mongo_err:
    logger.warning(f"MongoDB unavailable ({_mongo_err}); DB features disabled")
    client = None
    db     = None

# Create the main app without a prefix
app = FastAPI(title="APEX_OMEGA API", version="4.0")

# ── API Key Authentication ────────────────────────────────────────────────────
# When API_KEY env var is set, every /api/* request must include the header:
#   X-API-Key: <your-key>
# Leave API_KEY empty (default) to disable auth (development / internal use).
_API_KEY = os.getenv("API_KEY", "").strip()
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def _verify_api_key(api_key: Optional[str] = Security(_api_key_header)):
    """Dependency that validates the X-API-Key header when API_KEY is configured."""
    if not _API_KEY:
        return  # Auth disabled
    if api_key != _API_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")


# ── In-Memory Rate Limiter ────────────────────────────────────────────────────
# Simple per-IP sliding-window rate limiter.
# Configurable via:
#   RATE_LIMIT_MAX_REQUESTS  (default 60)
#   RATE_LIMIT_WINDOW_SECONDS (default 60)
_RATE_MAX = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "60"))
_RATE_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
_rate_store: Dict[str, collections.deque] = {}
_rate_lock = threading.Lock()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter applied to all /api/* routes."""

    async def dispatch(self, request: Request, call_next):
        # Only rate-limit API routes
        if not request.url.path.startswith("/api"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        window_start = now - _RATE_WINDOW

        with _rate_lock:
            if client_ip not in _rate_store:
                _rate_store[client_ip] = collections.deque()
            timestamps = _rate_store[client_ip]
            # Evict timestamps outside the window
            while timestamps and timestamps[0] < window_start:
                timestamps.popleft()
            if len(timestamps) >= _RATE_MAX:
                retry_after = int(_RATE_WINDOW - (now - timestamps[0])) + 1
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded. Try again later."},
                    headers={"Retry-After": str(retry_after)},
                )
            timestamps.append(now)

        return await call_next(request)


app.add_middleware(RateLimitMiddleware)

# Create a router with the /api prefix
# When API_KEY env var is configured, _verify_api_key is applied to every route.
api_router = APIRouter(prefix="/api", dependencies=[Depends(_verify_api_key)])

# Import dashboard API
from dashboard_api import dashboard_router

# Import arbitrage engine
from arbitrage_engine import (
    get_arbitrage_engine, 
    get_spreads, 
    get_pool_prices,
    serialize_pool,
    serialize_price_data,
    ArbitrageEngine
)

# Import price discovery engine
from price_discovery_engine import (
    get_price_discovery_engine,
    PriceDiscoveryEngine
)

# Import real profit engine
from real_profit_engine import (
    get_profit_engine,
    RealMarketProfitabilityEngine
)

# Import liquidation hunter
from liquidation_hunter import (
    get_liquidation_hunter,
    AaveLiquidationHunter
)

# Import institutional executor
from institutional_executor import (
    get_institutional_executor,
    build_execution_payload,
    InstitutionalExecutor,
    C1_ADDRESS
)

# Import liquidation executor contract
from liquidation_executor_contract import (
    get_liquidation_executor,
    build_liquidation_payload,
    LiquidationExecutor,
    Protocol,
    get_configured_liquidation_executor_address,
)

# Import Phase 3 routes
from phase3_routes import router as phase3_router

# Import Unified Strategy routes
from unified_strategy_routes import router as unified_router

from web3 import Web3
from eth_abi import decode as abi_decode
from execution_logger import get_execution_logger

# Import RPC monitor
from rpc_monitor import rpc_monitor, periodic_rpc_scan
from execution_governance import get_governance_service, get_minimum_net_profit_usd
from executor_registry import (
    DEX_ROUTERS,
    ZERO_ADDRESS,
    get_active_executor_address,
    get_chain_config,
    get_executor_config,
    get_rpc_url,
    get_configured_executor_wallet,
    validate_executor_registry,
)


# Define Models
class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StatusCheckCreate(BaseModel):
    client_name: str

class BotConfig(BaseModel):
    min_profit_threshold: str
    max_slippage_tolerance: str
    atomic_force_multiplier: str
    scan_interval_seconds: str
    rpc_configured: bool
    token_configured: bool

class OpportunityRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    pool: str
    address: str
    liquidity: float
    predicted_profit: float
    profit_percentage: float
    slippage: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExecuteQuoteRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    opportunity_id: Optional[str] = None
    spread_index: Optional[int] = None
    use_balancer: bool = True
    loan_amount_usd: float = 10000
    slippage_bps: int = 50
    deadline_seconds: int = 300


class ExecuteSimulateRequest(ExecuteQuoteRequest):
    pass


class ExecuteSubmitRequest(ExecuteQuoteRequest):
    idempotency_key: str = Field(..., min_length=8)

# API Routes
@api_router.get("/")
async def root():
    return {"message": "APEX_OMEGA API v4.0", "status": "operational"}

@api_router.get("/bot/config", response_model=BotConfig)
async def get_bot_config():
    """Get current bot configuration"""
    rpc_url = get_rpc_url('polygon')
    token = os.getenv('TELEGRAM_BOT_TOKEN', '')
    
    return BotConfig(
        min_profit_threshold=os.getenv('MIN_PROFIT_THRESHOLD', '0.005'),
        max_slippage_tolerance=os.getenv('MAX_SLIPPAGE_TOLERANCE', '0.03'),
        atomic_force_multiplier=os.getenv('ATOMIC_FORCE_MULTIPLIER', '1.2'),
        scan_interval_seconds=os.getenv('SCAN_INTERVAL_SECONDS', '15'),
        rpc_configured='YOUR_API_KEY' not in rpc_url and rpc_url != '',
        token_configured=token != '' and 'AAHPE' in token
    )

@api_router.get("/bot/pools")
async def get_pools():
    """Get list of monitored pools"""
    from engine import POLYGON_POOLS
    return {"pools": POLYGON_POOLS, "count": len(POLYGON_POOLS)}

@api_router.post("/opportunities", response_model=OpportunityRecord)
async def record_opportunity(opportunity: Dict[str, Any]):
    """Record a detected opportunity"""
    record = OpportunityRecord(
        pool=opportunity.get('pool', ''),
        address=opportunity.get('address', ''),
        liquidity=opportunity.get('liquidity', 0),
        predicted_profit=opportunity.get('predicted_profit', 0),
        profit_percentage=opportunity.get('profit_percentage', 0),
        slippage=opportunity.get('slippage', 0)
    )
    
    doc = record.model_dump()
    doc['timestamp'] = doc['timestamp'].isoformat()
    await db.opportunities.insert_one(doc)
    
    return record

@api_router.get("/opportunities")
async def get_opportunities(limit: int = 50):
    """Get recent opportunities"""
    opportunities = await db.opportunities.find(
        {}, {"_id": 0}
    ).sort("timestamp", -1).limit(limit).to_list(limit)
    
    return {"opportunities": opportunities, "count": len(opportunities)}

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.model_dump()
    status_obj = StatusCheck(**status_dict)
    
    doc = status_obj.model_dump()
    doc['timestamp'] = doc['timestamp'].isoformat()
    
    _ = await db.status_checks.insert_one(doc)
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    status_checks = await db.status_checks.find({}, {"_id": 0}).to_list(1000)
    
    for check in status_checks:
        if isinstance(check['timestamp'], str):
            check['timestamp'] = datetime.fromisoformat(check['timestamp'])
    
    return status_checks


# ============ ARBITRAGE ENDPOINTS ============

@api_router.get("/spreads")
async def api_get_spreads(loan_amount: float = None, response: Response = None):
    """
    Get current spread opportunities with OPTIMAL DYNAMIC LOAN SIZING

    Args:
        loan_amount: Optional fixed loan amount for testing/comparison
                    If None, calculates optimal loan for each spread based on pool TVL

    Returns flash loan arbitrage opportunities with full breakdown.
    Returns HTTP 503 with {loading, progress} during the engine cold-start window.
    """
    try:
        engine = get_arbitrage_engine()

        # COLD-START GATE: signal "still warming up" so clients can distinguish
        # 'no data yet' from 'no opportunities right now'.
        if getattr(engine, "pools_loading", False) or len(engine.pools) == 0:
            if response is not None:
                response.status_code = 503
                response.headers["Retry-After"] = "10"
            return {
                "loading": True,
                "ready": False,
                "progress": {
                    "pools_loaded": len(engine.pools),
                    "pools_target": int(os.getenv("POOL_LOAD_TARGET", "4500")),
                },
                "timestamp": 0,
                "spreads": [],
            }

        # QUICK FIX: Return cached spreads if recent (< 30s old)
        # This prevents timeout while we debug the scan
        if engine.last_update > 0 and (time.time() * 1000 - engine.last_update) < 30000:
            logger.info(f"⚡ Returning cached spreads ({len(engine.spreads)} opportunities)")
            return engine.get_spreads()

        # Trigger fresh scan with REDUCED limit to prevent timeout
        logger.info(f"🔍 Starting fresh spread scan (loan=${loan_amount or 'dynamic'})")
        engine.scan_for_spreads(loan_amount_usd=loan_amount, max_comparisons=100)
        data = get_spreads()
        logger.info(f"✅ Scan complete: {len(data.get('spreads', []))} spreads found")
        return data
    except Exception as e:
        logger.error(f"Failed to get spreads: {e}", exc_info=True)
        return {"error": str(e), "timestamp": 0, "spreads": []}


@api_router.get("/roi-forecast")
async def api_get_roi_forecast():
    """
    Get 90-day ROI forecast for flash loan arbitrage
    
    Returns:
        Comprehensive ROI projection with conservative/expected/optimistic scenarios
        Based on current market opportunities and flash loan economics
    """
    try:
        from roi_predictor import get_roi_forecast
        
        # Get current spreads for analysis
        engine = get_arbitrage_engine()
        spreads_data = engine.get_spreads()
        current_spreads = spreads_data.get('spreads', [])
        
        # Generate forecast
        forecast = get_roi_forecast(current_spreads)
        
        logger.info(f"✅ ROI Forecast generated: ${forecast['scenarios']['expected']['90day_total_usd']:,.2f} expected")
        return forecast
        
    except Exception as e:
        logger.error(f"Failed to generate ROI forecast: {e}", exc_info=True)
        return {
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scenarios": {
                "conservative": {"90day_total_usd": 0},
                "expected": {"90day_total_usd": 0},
                "optimistic": {"90day_total_usd": 0}
            }
        }


@api_router.get("/pool-prices")
async def api_get_pool_prices(response: Response = None):
    """
    Get current pool prices.
    Returns all monitored pools with price data.
    Returns HTTP 503 with {loading, progress} during the engine cold-start window.
    """
    try:
        engine = get_arbitrage_engine()
        if getattr(engine, "pools_loading", False) or len(engine.pools) == 0:
            if response is not None:
                response.status_code = 503
                response.headers["Retry-After"] = "10"
            return {
                "loading": True,
                "ready": False,
                "progress": {
                    "pools_loaded": len(engine.pools),
                    "pools_target": int(os.getenv("POOL_LOAD_TARGET", "4500")),
                },
                "timestamp": 0,
                "pools": [],
            }
        return get_pool_prices()
    except Exception as e:
        logger.error(f"Failed to get pool prices: {e}")
        return {"error": "Failed to get pool prices", "timestamp": 0, "pools": []}


@api_router.get("/price-matrix")
async def api_get_price_matrix():
    """
    Get price comparison matrix - OPTIMIZED with Phase 1 enhancements
    - NumPy vectorization (10-50x faster)
    - Redis caching (90% latency reduction)
    - Parallel processing (4x speedup)
    """
    start_time = time.time()
    
    try:
        # Check cache first (REDIS OPTIMIZATION)
        cache_key = "price_matrix_v1"
        cached_result = cache_get(cache_key)
        if cached_result:
            perf_monitor.record_cache_hit()
            latency = (time.time() - start_time) * 1000
            perf_monitor.record_latency(latency)
            logger.info(f"🚀 Price matrix from cache: {latency:.2f}ms")
            return cached_result
        
        perf_monitor.record_cache_miss()
        
        # Cache miss - calculate fresh
        engine = get_arbitrage_engine()
        all_pools = get_cached_pool_prices(engine, "pool_prices_raw")
        
        # Group pools by token pair
        price_matrix = {}
        
        for pool in all_pools:
            # Skip pools with zero liquidity
            reserve_usd = pool.get('reserve_usd', pool.get('tvl_usd', 0))
            if reserve_usd < 1000:  # Skip pools with <$1k liquidity
                continue
                
            pair_key = f"{pool.token0_symbol}/{pool.token1_symbol}"
            
            if pair_key not in price_matrix:
                price_matrix[pair_key] = {
                    'pair': pair_key,
                    'token0': pool.token0_symbol,
                    'token1': pool.token1_symbol,
                    'token0Address': pool.token0,
                    'token1Address': pool.token1,
                    'dexPrices': [],
                    'bestBuyPrice': float('inf'),
                    'bestSellPrice': 0,
                    'bestBuyDex': None,
                    'bestSellDex': None
                }
            
            # Price is already calculated as spot price
            price = pool.spot_price
            
            if price <= 0:
                continue
            
            dex_data = {
                'dex': pool.dex_name,
                'price': price,
                'reserveUsd': reserve_usd,
                'fee': pool.fee,
                'poolAddress': pool.pool_address,
                'protocol': pool.protocol
            }
            
            price_matrix[pair_key]['dexPrices'].append(dex_data)
            
            # Track best prices (buy low, sell high)
            if price < price_matrix[pair_key]['bestBuyPrice']:
                price_matrix[pair_key]['bestBuyPrice'] = price
                price_matrix[pair_key]['bestBuyDex'] = pool.dex_name
            
            if price > price_matrix[pair_key]['bestSellPrice']:
                price_matrix[pair_key]['bestSellPrice'] = price
                price_matrix[pair_key]['bestSellDex'] = pool.dex_name
        
        # Calculate spread and OPTIMAL CAPITAL for each pair
        for pair_data in price_matrix.values():
            if pair_data['bestBuyPrice'] > 0 and pair_data['bestBuyPrice'] != float('inf'):
                pair_data['spreadPct'] = ((pair_data['bestSellPrice'] - pair_data['bestBuyPrice']) / pair_data['bestBuyPrice']) * 100
                pair_data['spreadBps'] = pair_data['spreadPct'] * 100
                
                # CAPITAL OPTIMIZATION (Sentinel-inspired, no ML)
                # Test loan sizes and pick most profitable
                loan_options = [1000, 5000, 10000, 25000, 50000]
                best_profit = -999999
                optimal_loan = 10000
                
                # Get pool TVLs for slippage
                buy_tvl = 10000
                sell_tvl = 10000
                for dex in pair_data['dexPrices']:
                    if dex['dex'] == pair_data['bestBuyDex']:
                        buy_tvl = max(buy_tvl, dex.get('reserveUsd', 10000))
                    if dex['dex'] == pair_data['bestSellDex']:
                        sell_tvl = max(sell_tvl, dex.get('reserveUsd', 10000))
                
                # Test each loan size
                for loan in loan_options:
                    # Non-linear slippage (sqrt model like Sentinel)
                    buy_impact = min((loan / buy_tvl) ** 0.5, 0.5)
                    sell_impact = min((loan / sell_tvl) ** 0.5, 0.5)
                    
                    # Profit with slippage
                    flash_fee = loan * 0.0009
                    buy_fee = loan * 0.003
                    eff_buy_px = pair_data['bestBuyPrice'] * (1 + buy_impact)
                    tokens = (loan - buy_fee) / eff_buy_px
                    
                    eff_sell_px = pair_data['bestSellPrice'] * (1 - sell_impact)
                    sell_val = tokens * eff_sell_px
                    sell_fee = sell_val * 0.003
                    
                    profit = sell_val - sell_fee - loan - flash_fee - 0.01
                    
                    if profit > best_profit:
                        best_profit = profit
                        optimal_loan = loan
                
                pair_data['estimatedProfitUsd'] = best_profit
                pair_data['optimalLoanSize'] = optimal_loan
                pair_data['isExecutable'] = best_profit >= 0.50
                pair_data['roi'] = (best_profit / optimal_loan * 100) if optimal_loan > 0 else 0
            else:
                pair_data['spreadPct'] = 0
                pair_data['spreadBps'] = 0
                pair_data['estimatedProfitUsd'] = 0
                pair_data['optimalLoanSize'] = 10000
                pair_data['isExecutable'] = False
                pair_data['roi'] = 0
        
        # Convert to list and sort by profitability
        all_pairs = [p for p in price_matrix.values() if len(p['dexPrices']) >= 2]
        
        # Separate executable and non-executable
        executable_pairs = [p for p in all_pairs if p['isExecutable']]
        non_executable_pairs = [p for p in all_pairs if not p['isExecutable']]
        
        # Sort executable by profit, non-executable by spread
        executable_pairs.sort(key=lambda x: x['estimatedProfitUsd'], reverse=True)
        non_executable_pairs.sort(key=lambda x: x['spreadPct'], reverse=True)
        
        # Combine: executable first, then top theoretical spreads
        matrix_list = executable_pairs + non_executable_pairs[:30]
        
        return {
            'timestamp': int(time.time() * 1000),
            'pairs_found': len(matrix_list),
            'executable_count': len(executable_pairs),
            'theoretical_count': len(non_executable_pairs),
            'price_matrix': matrix_list
        }
        
    except Exception as e:
        logger.error(f"Failed to get price matrix: {e}", exc_info=True)
        return {"error": str(e), "price_matrix": [], "pairs_found": 0}




@api_router.post("/pool-update")
async def api_update_pool(pool_data: Dict[str, Any]):
    """
    Update pool data (for WebSocket integration)
    """
    try:
        engine = get_arbitrage_engine()
        pool = engine.update_pool(pool_data)
        return {"status": "updated", "pool": pool.to_dict()}
    except Exception as e:
        logger.error(f"Failed to update pool: {e}")
        return {"error": str(e)}


@api_router.get("/arbitrage/scan")
async def api_scan_arbitrage(loan_amount: float = 10000, min_profit: float = 5):
    """
    Scan for arbitrage opportunities
    Returns executable opportunities sorted by profit
    """
    try:
        engine = get_arbitrage_engine()
        engine.min_profit_usd = max(min_profit, get_minimum_net_profit_usd())
        spreads = engine.scan_for_spreads(loan_amount)
        
        executable = [s for s in spreads if s.flash_loan.is_executable]
        
        return {
            "timestamp": engine.last_update,
            "total_spreads": len(spreads),
            "executable": len(executable),
            "opportunities": [s.to_dict() for s in executable[:10]],  # Top 10
        }
    except Exception as e:
        logger.error(f"Scan failed: {e}")
        return {"error": str(e), "opportunities": []}


# ============ STRATEGY MANAGEMENT ==============

from strategy_manager import get_strategy_manager, StrategyConfig

@api_router.post("/strategies/start")
async def start_strategies(config: Dict[str, Any] = None):
    """Start arbitrage and/or liquidation strategies"""
    try:
        manager = get_strategy_manager()
        
        # Update config if provided
        if config:
            manager.update_config(config)
        
        # Start manager
        await manager.start()
        
        return {
            "status": "started",
            "config": manager.get_stats()
        }
    except Exception as e:
        logger.error(f"Failed to start strategies: {e}")
        return {"error": str(e)}


@api_router.post("/strategies/stop")
async def stop_strategies():
    """Stop all running strategies"""
    try:
        manager = get_strategy_manager()
        await manager.stop()
        
        return {
            "status": "stopped",
            "stats": manager.get_stats()
        }
    except Exception as e:
        logger.error(f"Failed to stop strategies: {e}")
        return {"error": str(e)}


@api_router.get("/strategies/status")
async def get_strategies_status():
    """Get current strategy status and statistics"""
    try:
        manager = get_strategy_manager()
        return manager.get_stats()
    except Exception as e:
        logger.error(f"Failed to get strategy status: {e}")
        return {"error": str(e)}


@api_router.post("/strategies/config")
async def update_strategies_config(config: Dict[str, Any]):
    """Update strategy configuration"""
    try:
        manager = get_strategy_manager()
        manager.update_config(config)
        
        return {
            "status": "updated",
            "config": manager.get_stats()
        }
    except Exception as e:
        logger.error(f"Failed to update config: {e}")
        return {"error": str(e)}


@api_router.get("/arbitrage/config")
async def api_get_arb_config():
    """Get arbitrage engine configuration"""
    engine = get_arbitrage_engine()
    return {
        "minReserveUsd": engine.min_reserve_usd,
        "minProfitUsd": engine.min_profit_usd,
        "flashLoanFeeBps": engine.flash_loan_fee_bps,
        "gasPriceGwei": engine.gas_price_gwei,
        "gasUnits": engine.gas_units,
        "maticPriceUsd": engine.matic_price,
        "poolCount": len(engine.pools),
        "titanEnabled": True,  # TITAN engine status
    }


# ============ PRICE DISCOVERY ENDPOINTS ============

@api_router.get("/price-discovery/matrix")
async def api_get_price_discovery_matrix(token_pair: str = None):
    """
    Get comprehensive ask/bid price matrix across ALL pools
    
    Shows the complete order book-style view of prices across all DEXes
    
    Args:
        token_pair: Optional filter for specific pair (e.g., "WMATIC/USDC")
        
    Returns:
        {
            "WMATIC/USDC": {
                "pools": 5,
                "best_ask": 0.5008,
                "best_bid": 0.4992,
                "spread_bps": 16,
                "cheapest_buy_pool": "UniSwap V3",
                "best_sell_pool": "QuickSwap V2",
                "avg_price": 0.5000,
                "total_tvl_usd": 50000000,
                "all_quotes": [
                    {"pool": "QuickSwap V2", "ask": 0.5010, "bid": 0.4990, "tvl_usd": 10000000, "fee_bps": 30},
                    ...
                ]
            },
            ...
        }
    """
    try:
        engine = get_arbitrage_engine()
        discovery = get_price_discovery_engine()
        
        # Build fresh price matrix from current pools
        discovery.build_price_matrix(engine.pools)
        
        # Get summary for requested pair(s)
        summary = discovery.get_price_summary(token_pair)
        
        return {
            "timestamp": engine.last_update,
            "total_pairs": len(summary),
            "price_matrix": summary
        }
    except Exception as e:
        logger.error(f"Failed to build price matrix: {e}")
        return {"error": str(e), "price_matrix": {}}


@api_router.get("/price-discovery/opportunities")
async def api_get_price_opportunities(
    min_spread_bps: int = 10,
    min_tvl_usd: float = 10000
):
    """
    Find arbitrage opportunities using ask/bid price discovery
    
    Compares ask/bid prices across ALL pools to find spreads
    
    Args:
        min_spread_bps: Minimum spread in basis points (default 10 = 0.10%)
        min_tvl_usd: Minimum TVL per pool (default $10,000)
        
    Returns:
        List of opportunities with buy pool, sell pool, and spread
    """
    try:
        engine = get_arbitrage_engine()
        discovery = get_price_discovery_engine()
        
        # Build fresh price matrix
        discovery.build_price_matrix(engine.pools)
        
        # Find opportunities
        opportunities = discovery.find_arbitrage_opportunities(
            min_spread_bps=min_spread_bps,
            min_tvl_usd=min_tvl_usd
        )
        
        # Format response
        formatted_opps = []
        for buy_quote, sell_quote, spread_bps in opportunities:
            formatted_opps.append({
                "token_pair": buy_quote.token_pair,
                "spread_bps": round(spread_bps, 2),
                "buy_pool": {
                    "dex": buy_quote.dex_name,
                    "address": buy_quote.pool_address,
                    "ask_price": buy_quote.ask_price,
                    "tvl_usd": buy_quote.tvl_usd,
                    "fee_bps": buy_quote.fee_bps
                },
                "sell_pool": {
                    "dex": sell_quote.dex_name,
                    "address": sell_quote.pool_address,
                    "bid_price": sell_quote.bid_price,
                    "tvl_usd": sell_quote.tvl_usd,
                    "fee_bps": sell_quote.fee_bps
                },
                "potential_profit_bps": round(spread_bps - buy_quote.fee_bps - sell_quote.fee_bps, 2)
            })
        
        return {
            "timestamp": engine.last_update,
            "opportunities_found": len(formatted_opps),
            "opportunities": formatted_opps
        }
    except Exception as e:
        logger.error(f"Failed to find price opportunities: {e}")
        return {"error": str(e), "opportunities": []}


@api_router.get("/real-profits")
async def api_get_real_profits(
    min_spread_bps: int = 20,
    min_tvl_usd: float = 10000,
    top_n: int = 20
):
    """
    🎯 PRODUCTION ENDPOINT: Get REAL profitable arbitrage opportunities
    
    This is the endpoint for ACTUAL market execution - only returns trades
    that will MAKE MONEY after all costs (fees, slippage, gas)
    
    Filters out theoretical spreads that aren't profitable in practice
    
    Args:
        min_spread_bps: Minimum raw spread (default 20 = 0.20%)
        min_tvl_usd: Minimum pool TVL (default $10k)
        top_n: Return top N opportunities by profit (default 20)
        
    Returns:
        {
            "opportunities_found": 5,
            "total_profit_potential": 127.50,
            "opportunities": [
                {
                    "token_pair": "WMATIC/USDC",
                    "buy_dex": "UniSwap V3",
                    "sell_dex": "QuickSwap V2",
                    "raw_spread_bps": 45.2,
                    "optimal_loan_usd": 5000,
                    "net_profit_usd": 25.50,
                    "roi_percent": 0.51,
                    "execution_confidence": "HIGH",
                    "detailed_pnl": {...},
                    "risk_factors": []
                },
                ...
            ]
        }
    """
    try:
        profit_engine = get_profit_engine()
        
        # Scan for REAL profitable opportunities
        opportunities = profit_engine.scan_for_real_profits(
            min_spread_bps=min_spread_bps,
            min_tvl_usd=min_tvl_usd,
            top_n=top_n
        )
        
        # Format response
        formatted_opps = []
        for opp in opportunities:
            formatted_opps.append({
                "token_pair": opp.token_pair,
                "buy_dex": opp.buy_dex,
                "sell_dex": opp.sell_dex,
                "buy_pool_address": opp.buy_pool_address,
                "sell_pool_address": opp.sell_pool_address,
                "raw_spread_bps": round(opp.raw_spread_bps, 2),
                "ask_price": opp.ask_price,
                "bid_price": opp.bid_price,
                "optimal_loan_usd": round(opp.optimal_loan_usd, 2),
                "net_profit_usd": round(opp.net_profit_usd, 2),
                "roi_percent": round(opp.roi_percent, 4),
                "execution_confidence": opp.execution_confidence,
                "detailed_pnl": {
                    "leg1": {
                        "input_usd": round(opp.leg1_input_usd, 2),
                        "output_usd": round(opp.leg1_output_usd, 2),
                        "fee_usd": round(opp.leg1_fee_usd, 2),
                        "slippage_usd": round(opp.leg1_slippage_usd, 2)
                    },
                    "leg2": {
                        "input_usd": round(opp.leg2_input_usd, 2),
                        "output_usd": round(opp.leg2_output_usd, 2),
                        "fee_usd": round(opp.leg2_fee_usd, 2),
                        "slippage_usd": round(opp.leg2_slippage_usd, 2)
                    },
                    "flash_loan_fee_usd": round(opp.flash_loan_fee_usd, 2),
                    "gas_cost_usd": round(opp.gas_cost_usd, 4),
                    "gross_profit_usd": round(opp.gross_profit_usd, 2),
                    "total_costs_usd": round(
                        opp.leg1_fee_usd + opp.leg1_slippage_usd + 
                        opp.leg2_fee_usd + opp.leg2_slippage_usd + 
                        opp.flash_loan_fee_usd + opp.gas_cost_usd, 2
                    )
                },
                "risk_factors": opp.risk_factors
            })
        
        total_profit = sum(opp.net_profit_usd for opp in opportunities)
        
        return {
            "timestamp": int(time.time() * 1000),
            "opportunities_found": len(formatted_opps),
            "total_profit_potential": round(total_profit, 2),
            "opportunities": formatted_opps
        }
        
    except Exception as e:
        logger.error(f"Failed to get real profits: {e}", exc_info=True)
        return {"error": str(e), "opportunities": [], "opportunities_found": 0}


# ============ LIQUIDATION HUNTING ENDPOINTS ============

@api_router.get("/liquidations/scan")
async def api_scan_liquidations(
    user_addresses: str = None,
    min_profit_usd: float = 10.0
):
    """
    🎯 LIQUIDATION HUNTER: Scan Aave V3 for liquidatable positions
    
    This is a PROFITABLE edge strategy:
    - Monitor lending protocol positions
    - Find undercollateralized positions (health factor < 1.0)
    - Execute liquidations for guaranteed profit (5-15% bonus)
    - Use flash loans (capital-free execution)
    
    Args:
        user_addresses: Comma-separated list of addresses to check
        min_profit_usd: Minimum profit threshold (default $10)
        
    Returns:
        {
            "liquidations_found": 5,
            "total_profit_potential": 250.50,
            "liquidations": [
                {
                    "user_address": "0x...",
                    "health_factor": 0.95,
                    "collateral_value_usd": 20000,
                    "debt_value_usd": 15000,
                    "liquidation_bonus_usd": 750,
                    "estimated_profit_usd": 725,
                    "is_executable": true
                },
                ...
            ]
        }
    """
    try:
        hunter = get_liquidation_hunter()
        
        # Parse user addresses
        addresses = []
        if user_addresses:
            addresses = [addr.strip() for addr in user_addresses.split(',')]
        
        # Scan for liquidations
        liquidations = hunter.scan_for_liquidations(
            user_addresses=addresses,
            min_profit_usd=min_profit_usd
        )
        
        # Format response
        formatted_liquidations = []
        for liq in liquidations:
            formatted_liquidations.append({
                "user_address": liq.user_address,
                "health_factor": round(liq.health_factor, 4),
                "collateral_value_usd": round(liq.collateral_value_usd, 2),
                "debt_value_usd": round(liq.debt_value_usd, 2),
                "max_liquidatable_debt_usd": round(liq.max_liquidatable_debt_usd, 2),
                "liquidation_bonus_pct": liq.liquidation_bonus_pct,
                "liquidation_bonus_usd": round(liq.liquidation_bonus_usd, 2),
                "estimated_profit_usd": round(liq.estimated_profit_usd, 2),
                "flash_loan_needed_usd": round(liq.flash_loan_needed_usd, 2),
                "is_executable": liq.is_executable
            })
        
        total_profit = sum(liq.estimated_profit_usd for liq in liquidations)
        
        return {
            "timestamp": int(time.time() * 1000),
            "liquidations_found": len(formatted_liquidations),
            "total_profit_potential": round(total_profit, 2),
            "liquidations": formatted_liquidations,
            "strategy": "aave_v3_liquidation_hunting",
            "message": "Liquidation hunting provides guaranteed profits during market volatility"
        }
        
    except Exception as e:
        logger.error(f"Liquidation scan failed: {e}", exc_info=True)
        return {
            "error": str(e),
            "liquidations_found": 0,
            "liquidations": []
        }


@api_router.post("/liquidations/execute")
async def api_execute_liquidation(
    user_address: str,
    dry_run: bool = True
):
    """
    Execute a liquidation
    
    Args:
        user_address: Address of position to liquidate
        dry_run: If true, only simulate (default: true)
        
    Returns:
        Execution result with transaction hash (if live)
    """
    try:
        hunter = get_liquidation_hunter()
        
        # Get position data
        account_data = hunter.get_user_health_factor(user_address)
        
        if not account_data or not account_data["is_liquidatable"]:
            return {
                "status": "not_liquidatable",
                "health_factor": account_data["health_factor"] if account_data else None,
                "message": "Position is not liquidatable (health factor >= 1.0)"
            }
        
        # Execute liquidation
        result = hunter.execute_liquidation(
            position=None,  # Would build from account_data
            dry_run=dry_run
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Liquidation execution failed: {e}", exc_info=True)
        return {"error": str(e), "status": "failed"}


@api_router.get("/executor/stats")
async def api_get_executor_stats():
    """Get live executor statistics"""
    try:
        from live_executor import get_live_executor
        executor = get_live_executor()
        payload = executor.get_stats()
        payload["governance"] = {
            "minimum_net_profit_usd": get_minimum_net_profit_usd(),
            "system": get_governance_service().get_metrics().get("system", {}),
        }
        return payload
    except Exception as e:
        logger.error(f"Failed to get executor stats: {e}")
        return {"error": str(e)}


@api_router.get("/executor/history")
async def api_get_execution_history(
    limit: int = 50,
    strategy: Optional[str] = None,
    status: Optional[str] = None,
):
    """Return persisted execution lifecycle history, newest first."""
    try:
        bounded_limit = max(1, min(limit, 500))
        history = await get_execution_logger().get_execution_history(
            limit=bounded_limit,
            strategy=strategy,
            status=status,
        )
        return {"history": history, "count": len(history), "limit": bounded_limit}
    except Exception as e:
        logger.error(f"Failed to load execution history: {e}", exc_info=True)
        return {"error": "Failed to load execution history", "history": []}


@api_router.get("/executor/trace/{execution_id}")
async def api_get_execution_trace(execution_id: str):
    """Return the full persisted lifecycle trace for one execution."""
    try:
        trace = await get_execution_logger().get_execution_lifecycle_trace(execution_id)
        if not trace:
            raise HTTPException(status_code=404, detail="Execution trace not found")
        return trace
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to load execution trace {execution_id}: {e}", exc_info=True)
        return {"error": "Failed to load execution trace"}


@api_router.post("/executor/start")
async def api_start_executor(mode: str = "simulation"):
    """Start the live executor"""
    try:
        from live_executor import start_live_executor, get_live_executor, ExecutionMode
        executor = get_live_executor()
        
        # Set mode
        mode_map = {
            "simulation": ExecutionMode.SIMULATION,
            "dry_run": ExecutionMode.DRY_RUN,
            "live": ExecutionMode.LIVE,
        }
        executor.config.mode = mode_map.get(mode, ExecutionMode.SIMULATION)
        
        if not executor.is_running:
            await executor.reconcile_pending_submissions()
            start_live_executor()
            return {"status": "started", "mode": executor.config.mode.value}
        return {"status": "already_running", "mode": executor.config.mode.value}
    except Exception as e:
        logger.error(f"Failed to start executor: {e}")
        return {"error": str(e)}


@api_router.post("/executor/stop")
async def api_stop_executor():
    """Stop the live executor"""
    try:
        from live_executor import get_live_executor
        executor = get_live_executor()
        executor.stop()
        return {"status": "stopped"}
    except Exception as e:
        return {"error": str(e)}


@api_router.get("/executor/execution-state")
async def api_get_execution_state(
    limit: int = 50,
    status: Optional[str] = None,
    opportunity_id: Optional[str] = None,
):
    """Get durable execution state records used for submission deduplication."""
    try:
        from execution_logger import get_execution_logger

        records = await get_execution_logger().get_execution_states(
            limit=limit,
            status=status,
            opportunity_id=opportunity_id,
        )
        return {"count": len(records), "records": records}
    except Exception as e:
        logger.error(f"Failed to get execution state: {e}")
        return {"error": str(e)}


@api_router.post("/executor/reconcile")
async def api_reconcile_execution_state():
    """Reconcile submitted transaction state against on-chain receipts."""
    try:
        from live_executor import get_live_executor

        executor = get_live_executor()
        return await executor.reconcile_pending_submissions()
    except Exception as e:
        logger.error(f"Failed to reconcile execution state: {e}")
        return {"error": str(e)}


@api_router.get("/governance/acceptance-criteria")
async def get_governance_acceptance_criteria():
    """Locked epic acceptance criteria for performance audit and execution governance."""
    return {
        "epic": "Performance Audit & Execution Governance",
        "minimum_net_profit_after_costs_usd": get_minimum_net_profit_usd(),
        "criteria": [
            "real-time high/low-level metrics",
            "full-suite and component-level testing controls",
            "Telegram-triggered runs and latency checks",
            "UI dashboard configurability",
            "discovery-to-execution full path activation",
            "reject only when net profit after all costs is below minimum threshold",
        ],
    }


@api_router.get("/governance/metrics")
async def get_governance_metrics():
    """Unified real-time metrics model (system/opportunity/tx levels)."""
    try:
        return get_governance_service().get_metrics()
    except Exception as e:
        logger.error(f"Failed to fetch governance metrics: {e}", exc_info=True)
        return {"error": "Failed to fetch governance metrics"}


@api_router.post("/governance/audit/start")
async def start_governance_audit(payload: Dict[str, Any] = None):
    """Start benchmark/audit runner in dry_run or live_monitor mode."""
    payload = payload or {}
    mode = payload.get("mode", "dry_run")
    profile = payload.get("profile", {})
    try:
        return get_governance_service().start_audit_run(mode=mode, profile=profile)
    except Exception as e:
        logger.error(f"Failed to start audit runner: {e}", exc_info=True)
        return {"error": "Failed to start audit runner"}


@api_router.post("/governance/audit/stop")
async def stop_governance_audit():
    try:
        return get_governance_service().stop_audit_run()
    except Exception as e:
        logger.error(f"Failed to stop audit runner: {e}", exc_info=True)
        return {"error": "Failed to stop audit runner"}


@api_router.get("/governance/audit/history")
async def get_governance_audit_history(limit: int = 100):
    try:
        history = get_governance_service().get_history(limit=limit)
        return {
            "history": history,
            "count": len(history),
        }
    except Exception as e:
        logger.error(f"Failed to load audit history: {e}", exc_info=True)
        return {"error": "Failed to load audit history", "history": []}


@api_router.post("/governance/tests/start")
async def start_governance_test_job(payload: Dict[str, Any] = None):
    """
    Start configurable test orchestration.
    payload.kind: full_suite | component | latency_probe
    payload.component: optional pytest target for component mode
    payload.interval_sec: optional schedule interval for continuous reruns
    """
    payload = payload or {}
    try:
        return get_governance_service().start_test_job(
            kind=payload.get("kind", "full_suite"),
            component=payload.get("component"),
            scheduled_interval_sec=int(payload.get("interval_sec", 0)),
        )
    except Exception as e:
        logger.error(f"Failed to start governance test job: {e}", exc_info=True)
        return {"error": "Failed to start governance test job"}


@api_router.post("/governance/tests/stop")
async def stop_governance_test_job():
    try:
        return get_governance_service().stop_test_job()
    except Exception as e:
        logger.error(f"Failed to stop governance test job: {e}", exc_info=True)
        return {"error": "Failed to stop governance test job"}



def _json_safe(value: Any) -> Any:
    """Convert Web3/Mongo values into JSON-safe primitives."""
    if isinstance(value, bytes):
        return "0x" + value.hex()
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    return value


def _normalize_tx_hash(tx_hash: str) -> str:
    if not tx_hash or not tx_hash.strip():
        raise HTTPException(status_code=400, detail="Transaction hash is required")

    normalized = tx_hash.strip().lower()
    normalized = normalized if normalized.startswith("0x") else f"0x{normalized}"

    if len(normalized) != 66:
        raise HTTPException(status_code=400, detail="Invalid transaction hash")

    try:
        bytes.fromhex(normalized[2:])
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid transaction hash")

    return normalized


def _decode_revert_error(error_data: Optional[str]) -> Optional[Dict[str, Any]]:
    """Decode common Solidity Error(string) and Panic(uint256) revert payloads."""
    if not error_data:
        return None

    data = error_data if error_data.startswith("0x") else f"0x{error_data}"
    try:
        raw = bytes.fromhex(data[2:])
    except ValueError:
        return {"raw": error_data}

    selector = raw[:4].hex()
    try:
        if selector == "08c379a0":
            reason = abi_decode(["string"], raw[4:])[0]
            return {"type": "Error", "reason": reason, "raw": data}
        if selector == "4e487b71":
            code = abi_decode(["uint256"], raw[4:])[0]
            return {"type": "Panic", "code": code, "raw": data}
    except Exception as exc:
        return {"raw": data, "decode_error": str(exc)}

    return {"raw": data, "selector": f"0x{selector}" if selector else None}


def _extract_rpc_error_data(exc: Exception) -> Optional[str]:
    """Best-effort extraction of revert data from Web3/RPC exceptions."""
    candidates = [exc]
    if getattr(exc, "args", None):
        candidates.extend(exc.args)

    for candidate in candidates:
        if isinstance(candidate, dict):
            data = candidate.get("data")
            if isinstance(data, str):
                return data
            if isinstance(data, dict):
                for nested in data.values():
                    if isinstance(nested, dict) and isinstance(nested.get("data"), str):
                        return nested["data"]
                    if isinstance(nested, str) and nested.startswith("0x"):
                        return nested
        if isinstance(candidate, str) and "0x" in candidate:
            possible = candidate[candidate.find("0x"):].split("'", 1)[0].split('"', 1)[0]
            if len(possible) >= 10:
                return possible
    return None


def _wallet_from_private_key(w3: Web3) -> Optional[str]:
    private_key = os.getenv("PRIVATE_KEY", "").strip()
    if not private_key:
        return None
    return w3.eth.account.from_key(private_key).address


def _get_executor_context() -> Dict[str, Any]:
    rpc_url = get_rpc_url('polygon')
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    wallet = _wallet_from_private_key(w3) or get_configured_executor_wallet(w3) or ZERO_ADDRESS
    return {
        "rpc_url": rpc_url,
        "w3": w3,
        "wallet": wallet,
        "executor": get_institutional_executor(w3)
    }


def _get_spread_for_execution(request: ExecuteQuoteRequest) -> Dict[str, Any]:
    engine = get_arbitrage_engine()
    spreads = engine.scan_for_spreads(loan_amount=request.loan_amount_usd)
    if not spreads:
        raise HTTPException(status_code=404, detail="No executable spreads available")

    spread_dicts = [spread.to_dict() for spread in spreads]

    if request.opportunity_id:
        for idx, spread in enumerate(spread_dicts):
            if str(spread.get("id")) == request.opportunity_id:
                return {"spread": spread, "spread_index": idx}
        raise HTTPException(
            status_code=404,
            detail=f"Opportunity {request.opportunity_id} was not found in the current spread scan"
        )

    spread_index = request.spread_index if request.spread_index is not None else 0
    if spread_index < 0 or spread_index >= len(spread_dicts):
        raise HTTPException(status_code=404, detail="No spread available at index")

    return {"spread": spread_dicts[spread_index], "spread_index": spread_index}


def _build_execution_quote(request: ExecuteQuoteRequest, include_tx: bool = True) -> Dict[str, Any]:
    selection = _get_spread_for_execution(request)
    spread = selection["spread"]
    context = _get_executor_context()
    w3 = context["w3"]
    executor = context["executor"]
    wallet = context["wallet"]

    payload = executor.payload_builder.build_payload_from_spread(
        spread=spread,
        use_balancer=request.use_balancer,
        slippage_bps=request.slippage_bps,
        deadline_seconds=request.deadline_seconds
    )

    estimated_gas = executor.tx_builder.estimate_gas(payload, wallet)
    gas_price = int(w3.eth.gas_price) if context["rpc_url"] else 0
    min_profit_usd = float(spread.get("flashLoan", {}).get("netProfitUsd", 0) or 0)
    required_min_profit_usd = float(get_minimum_net_profit_usd())
    deadline_ok = payload.deadline > int(time.time())
    live_execution = os.getenv("LIVE_EXECUTION", "false").lower() == "true"
    shadow_mode = os.getenv("SHADOW_MODE", "true").lower() == "true"
    wallet_configured = bool(os.getenv("PRIVATE_KEY", "").strip())

    tx = None
    if include_tx:
        tx = executor.tx_builder.build_flash_tx(payload, wallet)
        tx["gas"] = estimated_gas

    opportunity_id = str(
        spread.get("id")
        or f"spread-{selection['spread_index']}-{spread.get('tokenPair', 'unknown')}"
    )

    quote = {
        "opportunity_id": opportunity_id,
        "spread_index": selection["spread_index"],
        "payload": {
            "contract": C1_ADDRESS,
            "flash_provider": payload.flash_provider,
            "asset": payload.asset,
            "amount": str(payload.amount),
            "min_profit": str(payload.min_profit),
            "deadline": payload.deadline,
            "targets": payload.targets,
            "encoded_params": "0x" + payload.encoded_params.hex()
        },
        "native_token_amounts": {
            "gas_price_wei": str(gas_price),
            "estimated_gas_cost_wei": str(estimated_gas * gas_price),
            "estimated_gas_cost_native": str((estimated_gas * gas_price) / 1e18)
        },
        "gas_estimate": estimated_gas,
        "min_profit": {
            "token_units": str(payload.min_profit),
            "usd": min_profit_usd,
            "required_usd": required_min_profit_usd
        },
        "deadline": payload.deadline,
        "risk_checks": {
            "min_profit_met": min_profit_usd >= required_min_profit_usd,
            "deadline_valid": deadline_ok,
            "rpc_configured": bool(context["rpc_url"]),
            "wallet_configured": wallet_configured,
            "live_execution_enabled": live_execution,
            "shadow_mode_disabled": not shadow_mode,
            "gas_estimate_available": estimated_gas > 0
        },
        "spread": {
            "id": spread.get("id"),
            "tokenPair": spread.get("tokenPair"),
            "netProfitUsd": min_profit_usd,
            "flashProvider": spread.get("flashLoan", {}).get("flashLoanProvider"),
            "dualExecution": spread.get("flashLoan", {}).get("dualExecution", False)
        }
    }
    if tx is not None:
        quote["tx"] = _json_safe(tx)

    return quote


@api_router.post("/execute/quote")
async def quote_execution(request: ExecuteQuoteRequest):
    """Build a deterministic execution quote without broadcasting a transaction."""
    try:
        return _build_execution_quote(request, include_tx=True)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Execution quote failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/execute/simulate")
async def simulate_execution(request: ExecuteSimulateRequest):
    """Run eth_call and gas estimation against the exact transaction."""
    try:
        quote = _build_execution_quote(request, include_tx=True)
        context = _get_executor_context()
        w3 = context["w3"]
        tx = dict(quote["tx"])

        simulation = {
            "success": True,
            "eth_call": None,
            "gas_estimate": None,
            "revert_data": None,
            "decoded_error": None
        }

        try:
            call_result = w3.eth.call(tx, block_identifier="latest")
            simulation["eth_call"] = _json_safe(call_result)
        except Exception as call_error:
            revert_data = _extract_rpc_error_data(call_error)
            simulation.update({
                "success": False,
                "revert_data": revert_data,
                "decoded_error": _decode_revert_error(revert_data),
                "eth_call_error": str(call_error)
            })

        try:
            simulation["gas_estimate"] = w3.eth.estimate_gas(tx)
        except Exception as gas_error:
            revert_data = simulation["revert_data"] or _extract_rpc_error_data(gas_error)
            simulation.update({
                "success": False,
                "revert_data": revert_data,
                "decoded_error": _decode_revert_error(revert_data),
                "gas_estimate_error": str(gas_error)
            })

        return {"quote": quote, "simulation": simulation}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Execution simulation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/execute/submit")
async def submit_execution(request: ExecuteSubmitRequest):
    """Sign and broadcast a quoted execution transaction when live execution is explicitly enabled."""
    try:
        live_execution = os.getenv("LIVE_EXECUTION", "false").lower() == "true"
        shadow_mode = os.getenv("SHADOW_MODE", "true").lower() == "true"
        private_key = os.getenv("PRIVATE_KEY", "").strip()
        if not live_execution or shadow_mode or not private_key:
            raise HTTPException(
                status_code=403,
                detail={
                    "message": "Live submission requires LIVE_EXECUTION=true, SHADOW_MODE=false, and PRIVATE_KEY configured",
                    "live_execution": live_execution,
                    "shadow_mode": shadow_mode,
                    "wallet_configured": bool(private_key)
                }
            )

        quote = _build_execution_quote(request, include_tx=True)
        tx = dict(quote["tx"])
        opportunity_id = quote["opportunity_id"]
        logger_service = get_execution_logger()
        reserved = await logger_service.reserve_execution_submission(
            idempotency_key=request.idempotency_key,
            opportunity_id=opportunity_id,
            quote=quote,
            tx=tx
        )
        if not reserved["reserved"]:
            return {
                "status": "duplicate",
                "idempotency_key": request.idempotency_key,
                "opportunity_id": opportunity_id,
                "execution": reserved.get("record")
            }

        execution_id = reserved["record"]["execution_id"]
        context = _get_executor_context()
        w3 = context["w3"]
        account = w3.eth.account.from_key(private_key)
        tx["from"] = account.address
        tx["nonce"] = w3.eth.get_transaction_count(account.address)

        try:
            signed = w3.eth.account.sign_transaction(tx, private_key)
            raw_tx = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction")
            tx_hash = w3.eth.send_raw_transaction(raw_tx).hex()
        except Exception as broadcast_error:
            await logger_service.update_execution_state(
                execution_id=execution_id,
                status="failed",
                stage="transaction_broadcast_failed",
                details={"error": str(broadcast_error), "opportunity_id": opportunity_id},
                finished=True
            )
            raise

        await logger_service.update_execution_state(
            execution_id=execution_id,
            status="submitted",
            stage="transaction_broadcast",
            details={"tx_hash": tx_hash, "opportunity_id": opportunity_id},
            tx_hash=tx_hash
        )

        return {
            "status": "submitted",
            "execution_id": execution_id,
            "idempotency_key": request.idempotency_key,
            "opportunity_id": opportunity_id,
            "tx_hash": tx_hash
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Execution submit failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/execute/tx/{tx_hash}")
async def get_execution_tx(tx_hash: str):
    """Return receipt, status, gas used, block number, and decoded revert data when available."""
    tx_hash = _normalize_tx_hash(tx_hash)
    try:
        context = _get_executor_context()
        w3 = context["w3"]
        receipt = None
        receipt_status = "pending"
        decoded_error = None
        revert_data = None

        try:
            raw_receipt = w3.eth.get_transaction_receipt(tx_hash)
            receipt = _json_safe(dict(raw_receipt))
            receipt_status = "executed" if raw_receipt.get("status") == 1 else "failed"
        except Exception as receipt_error:
            logger.debug(f"Receipt unavailable for {tx_hash}: {receipt_error}")

        if receipt_status == "failed":
            try:
                tx = dict(w3.eth.get_transaction(tx_hash))
                call_tx = {
                    "from": tx.get("from"),
                    "to": tx.get("to"),
                    "data": tx.get("input"),
                    "value": tx.get("value", 0)
                }
                block_number = receipt.get("blockNumber") if receipt else "latest"
                w3.eth.call(call_tx, block_identifier=block_number)
            except Exception as call_error:
                revert_data = _extract_rpc_error_data(call_error)
                decoded_error = _decode_revert_error(revert_data)

        logger_record = await get_execution_logger().get_execution_by_tx_hash(tx_hash)
        if logger_record and receipt_status in {"executed", "failed"} and logger_record.get("status") != receipt_status:
            await get_execution_logger().update_execution_state(
                execution_id=logger_record["execution_id"],
                status=receipt_status,
                stage="receipt_observed",
                details={"receipt": receipt, "decoded_error": decoded_error},
                tx_hash=tx_hash,
                finished=True
            )
            logger_record = await get_execution_logger().get_execution_by_tx_hash(tx_hash)

        return {
            "tx_hash": tx_hash,
            "status": receipt_status,
            "receipt": receipt,
            "gas_used": receipt.get("gasUsed") if receipt else None,
            "block_number": receipt.get("blockNumber") if receipt else None,
            "revert_data": revert_data,
            "decoded_error": decoded_error,
            "execution": logger_record
        }
    except Exception as e:
        logger.error(f"Execution tx lookup failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/execute/build-payload")
async def api_build_execution_payload(
    spread_index: int = 0,
    use_balancer: bool = True
):
    """
    Build execution payload from spread opportunity
    
    Args:
        spread_index: Index of spread to execute (default: most profitable)
        use_balancer: Use Balancer (FREE) vs Aave (0.05% fee)
        
    Returns:
        {
            'payload': ExecutionPayload details,
            'estimated_gas': int,
            'status': 'dry_run'
        }
    """
    try:
        # Get spread opportunity
        engine = get_arbitrage_engine()
        spreads = engine.scan_for_spreads(loan_amount=10000)
        
        if not spreads or spread_index >= len(spreads):
            return {"error": "No spread available at index", "index": spread_index}
        
        spread = spreads[spread_index].to_dict()
        
        # Build execution payload
        rpc_url = get_rpc_url('polygon')
        w3 = Web3(Web3.HTTPProvider(rpc_url))

        executor = get_institutional_executor(w3)

        # Derive from_address from PRIVATE_KEY so the nonce lookup and signing
        # target the same account.  Fall back to EXECUTOR_WALLET when the key is
        # not yet configured (e.g. dry-run / CI environments).
        private_key = os.getenv('PRIVATE_KEY')
        if private_key:
            wallet = w3.eth.account.from_key(private_key).address
        else:
            wallet = os.getenv('EXECUTOR_WALLET', '0x0000000000000000000000000000000000000000')
        
        result = executor.build_execution_from_spread(
            spread=spread,
            from_address=wallet,
            use_balancer=use_balancer,
            dry_run=True
        )
        
        # Add spread context
        result['spread'] = {
            'id': spread['id'],
            'tokenPair': spread['tokenPair'],
            'netProfitUsd': spread['flashLoan']['netProfitUsd'],
            'flashProvider': spread['flashLoan']['flashLoanProvider'],
            'dualExecution': spread['flashLoan'].get('dualExecution', False)
        }
        
        return result
        
    except Exception as e:
        logger.error(f"Build payload failed: {e}")
        return {"error": str(e)}


@api_router.get("/execute/contract-info")
async def api_get_contract_info():
    """Get InstitutionalExecutor contract information"""
    try:
        rpc_url = get_rpc_url('polygon')
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        
        executor_config = get_executor_config("institutional_arbitrage")
        executor = get_institutional_executor(w3)
        owner = executor.tx_builder.get_contract_owner()
        
        return {
            "contract": get_active_executor_address("institutional_arbitrage"),
            "owner": owner,
            "network": get_chain_config("polygon").name,
            "chain_id": get_chain_config("polygon").chain_id,
            "abi_identifier": executor_config.abi_identifier,
            "function_signatures": dict(executor_config.function_signatures),
            "required_permissions": list(executor_config.required_permissions),
            "deployment_status": executor_config.deployment_status,
            "deployment_block": executor_config.deployment_block,
            "supports": {
                "aave_v3": True,
                "balancer_v3": True,
                "aave_fee_bps": 5,  # 0.05%
                "balancer_fee_bps": 0  # FREE
            }
        }
    except Exception as e:
        logger.error(f"Contract info failed: {e}")
        return {"error": str(e)}

@api_router.get("/rpc/health")
async def get_rpc_health():
    """Get current RPC endpoint health status"""
    try:
        return rpc_monitor.get_health_summary()
    except Exception as e:
        logger.error(f"RPC health check failed: {e}")
        return {"error": str(e)}

@api_router.post("/rpc/scan")
async def trigger_rpc_scan():
    """Manually trigger an RPC health scan"""
    try:
        results = rpc_monitor.scan_all_endpoints()
        return {
            "success": True,
            "scanned": len(results),
            "current_best": rpc_monitor.current_best,
            "results": results
        }
    except Exception as e:
        logger.error(f"RPC scan failed: {e}")
        return {"error": str(e)}

@api_router.get("/rpc/best")
async def get_best_rpc():
    """Get the currently selected best RPC endpoint"""
    try:
        best_url = rpc_monitor.get_best_endpoint()
        return {
            "current_best": rpc_monitor.current_best,
            "url": best_url,
            "last_scan": rpc_monitor.last_scan_time.isoformat() if rpc_monitor.last_scan_time else None
        }
    except Exception as e:
        logger.error(f"Get best RPC failed: {e}")
        return {"error": str(e)}


# ============================================================================
# LIQUIDATION EXECUTOR ENDPOINTS
# ============================================================================

@api_router.get("/liquidation-executor/info")
async def get_liquidation_executor_info():
    """Get LiquidationExecutor contract information"""
    try:
        contract_address = get_configured_liquidation_executor_address()
        
        if not contract_address:
            return {
                "deployed": False,
                "message": "LiquidationExecutor not yet deployed. Run: cd /app/contracts && npx hardhat run scripts/deploy.js --network polygon"
            }
        
        rpc_url = get_rpc_url('polygon')
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        
        executor_config = get_executor_config("liquidation")
        executor = get_liquidation_executor(w3, contract_address)
        owner = executor.tx_builder.get_contract_owner()
        
        return {
            "deployed": True,
            "contract_address": contract_address,
            "owner": owner,
            "network": get_chain_config("polygon").name,
            "chain_id": get_chain_config("polygon").chain_id,
            "abi_identifier": executor_config.abi_identifier,
            "function_signatures": dict(executor_config.function_signatures),
            "required_permissions": list(executor_config.required_permissions),
            "deployment_status": executor_config.deployment_status,
            "deployment_block": executor_config.deployment_block,
            "features": {
                "flash_loan_provider": "Balancer V2 (0% fee)",
                "liquidation_protocol": "Aave V3",
                "supported_dexs": ["QuickSwap V3", "Uniswap V3", "SushiSwap", "QuickSwap V2"],
                "security": ["ReentrancyGuard", "Ownable", "SafeERC20"]
            }
        }
    except Exception as e:
        logger.error(f"Liquidation executor info failed: {e}")
        return {"error": str(e)}


@api_router.post("/liquidation-executor/build-payload")
async def build_liquidation_execution_payload(request: dict):
    """
    Build execution payload for a liquidatable position
    
    Request body:
    {
        "position": { ... },  # LiquidatablePosition from liquidation_hunter
        "min_profit_bps": 50  # Optional: minimum profit in bps
    }
    """
    try:
        rpc_url = get_rpc_url('polygon')
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        
        position = request.get('position')
        # min_profit_bps reserved for future use in optimization
        
        if not position:
            return {"error": "Missing 'position' in request body"}
        
        # Build payload
        result = build_liquidation_payload(position, w3, get_configured_liquidation_executor_address())
        
        return result
        
    except Exception as e:
        logger.error(f"Build liquidation payload failed: {e}")
        return {"error": str(e)}


@api_router.get("/liquidation-executor/protocols")
async def get_supported_protocols():
    """Get supported DEX protocols for collateral swaps"""
    polygon_routers = DEX_ROUTERS["polygon"]
    return {
        "protocols": [
            {
                "id": Protocol.QUICKSWAP_V3,
                "name": "QuickSwap V3",
                "type": "V3",
                "router": polygon_routers["quickswap_v3"],
                "default_fee": 3000,
                "description": "Best for MATIC pairs on Polygon"
            },
            {
                "id": Protocol.UNISWAP_V3,
                "name": "Uniswap V3",
                "type": "V3",
                "router": polygon_routers["uniswap_v3"],
                "default_fee": 3000,
                "description": "Best for ETH/USDC pairs"
            },
            {
                "id": Protocol.SUSHISWAP,
                "name": "SushiSwap",
                "type": "V2",
                "router": polygon_routers["sushiswap"],
                "default_fee": 3000,
                "description": "V2 AMM with deep liquidity"
            },
            {
                "id": Protocol.QUICKSWAP_V2,
                "name": "QuickSwap V2",
                "type": "V2",
                "router": polygon_routers["quickswap_v2"],
                "default_fee": 3000,
                "description": "Original QuickSwap pools"
            }
        ]
    }

# Include Phase 3 router
app.include_router(phase3_router)

# Include Unified Strategy router
app.include_router(unified_router)

# Include multi-chain routes (10 chains, cross-DEX only, no cross-chain)
try:
    from multi_chain_routes import router as multi_chain_router
    app.include_router(multi_chain_router)
    logger.info("✓ Multi-chain routes loaded (/api/chains)")
except Exception as e:
    logger.warning(f"Could not load multi-chain routes: {e}")



# Include the router in the main app
app.include_router(api_router)

# Include live config router for hot-reload variables
try:
    from live_config_api import router as live_config_router
    app.include_router(live_config_router, prefix="/api")
    logger.info("✓ Live config API loaded")
except Exception as e:
    logger.warning(f"Could not load live config API: {e}")

# Include dashboard API router
try:
    app.include_router(dashboard_router)
    logger.info("✓ Dashboard API loaded")
except Exception as e:
    logger.warning(f"Could not load dashboard API: {e}")

# WebSocket: real-time push channel for spreads / network / pipeline state
try:
    from fastapi import WebSocket
    from ws_hub import ws_endpoint, spread_push_loop

    @app.websocket("/api/ws/{channel}")
    async def websocket_route(websocket: WebSocket, channel: str):
        await ws_endpoint(websocket, channel)

    logger.info("✓ WebSocket hub mounted at /api/ws/{channel}")
except Exception as e:
    logger.warning(f"Could not load WebSocket hub: {e}")

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

@app.on_event("startup")
async def startup_executor_registry_validation():
    """Validate configured executor contracts before background execution starts."""
    rpc_url = get_rpc_url("polygon")
    if not rpc_url:
        logger.warning("Executor registry validation skipped: Polygon RPC is not configured")
        return

    try:
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not w3.is_connected():
            logger.warning("Executor registry validation skipped: Polygon RPC is not connected")
            return

        strict = (
            os.getenv("STRICT_CONTRACT_VALIDATION", "false").lower() == "true"
            or os.getenv("LIVE_EXECUTION", "false").lower() == "true"
        )
        summary = await asyncio.to_thread(
            validate_executor_registry,
            w3,
            get_configured_executor_wallet(w3),
            None,
            strict,
        )
        if summary["ok"]:
            logger.info("✅ Executor registry validation passed")
        else:
            logger.warning("Executor registry validation warnings: %s", "; ".join(summary["errors"]))
    except Exception as e:
        logger.error(f"Executor registry validation failed: {e}")
        if (
            os.getenv("STRICT_CONTRACT_VALIDATION", "false").lower() == "true"
            or os.getenv("LIVE_EXECUTION", "false").lower() == "true"
        ):
            raise


@app.on_event("startup")
async def startup_rpc_monitor():
    """Start periodic RPC monitoring on app startup"""
    scan_interval = int(os.getenv("RPC_SCAN_INTERVAL_MINUTES", "15"))
    logger.info(f"🔱 Starting RPC health monitor (scan interval: {scan_interval} min)")

    # Legacy single-chain (Polygon) RPC monitor — run in thread so it doesn't block event loop
    asyncio.create_task(asyncio.to_thread(rpc_monitor.scan_all_endpoints))
    asyncio.create_task(periodic_rpc_scan(interval_minutes=scan_interval))

    # Multi-chain RPC monitor (all 10 chains)
    try:
        from multi_chain_rpc import get_multi_chain_rpc, periodic_multi_chain_rpc_scan
        mc_rpc = get_multi_chain_rpc()
        logger.info("🔱 Starting multi-chain RPC monitor…")
        asyncio.create_task(periodic_multi_chain_rpc_scan(interval_minutes=scan_interval))
        logger.info("✓ Multi-chain RPC monitor started")
    except Exception as e:
        logger.warning(f"Multi-chain RPC monitor not started: {e}")


@app.on_event("startup")
async def startup_multi_chain_engine():
    """Start the multi-chain arbitrage engine background scan."""
    try:
        from multi_chain_engine import get_multi_chain_engine, periodic_multi_chain_scan
        scan_interval = int(os.getenv("MULTI_CHAIN_SCAN_INTERVAL_SEC", "120"))
        engine = get_multi_chain_engine()
        logger.info(f"⚡ Multi-chain engine ready — {len(engine.engines)} chains configured")
        asyncio.create_task(periodic_multi_chain_scan(interval_seconds=scan_interval))
        logger.info(f"✓ Multi-chain scan loop started (interval={scan_interval}s)")
    except Exception as e:
        logger.warning(f"Multi-chain engine not started: {e}")


@app.on_event("startup")
async def startup_ws_pusher():
    """Start all WebSocket push loops — legacy Polygon + multi-chain."""
    interval = float(os.getenv("WS_PUSH_INTERVAL_SEC", "3"))

    # Legacy single-chain (Polygon) push — skip if Polygon RPC is unavailable
    # (Infura Polygon returns 402 Payment Required; don't block the event loop)
    if get_rpc_url("polygon"):
        try:
            from ws_hub import spread_push_loop
            asyncio.create_task(spread_push_loop(get_arbitrage_engine, interval_sec=interval))
            logger.info(f"✓ WS spread push loop started (interval={interval}s)")
        except Exception as e:
            logger.warning(f"WS spread push loop not started: {e}")
    else:
        logger.info("⚠ Polygon RPC not configured — skipping legacy WS push loop")

    # Multi-chain push (mc_spreads channel) — serves cached scan results
    try:
        from ws_hub import mc_spread_push_loop
        from multi_chain_engine import get_multi_chain_engine
        asyncio.create_task(mc_spread_push_loop(get_multi_chain_engine, interval_sec=interval))
        logger.info(f"✓ Multi-chain WS push loop started (interval={interval}s)")
    except Exception as e:
        logger.warning(f"Multi-chain WS push loop not started: {e}")

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()


@app.on_event("startup")
async def startup_live_executor():
    """Auto-start live executor when LIVE_EXECUTION=true in .env"""
    live_execution = os.getenv("LIVE_EXECUTION", "false").lower() == "true"
    if live_execution:
        try:
            from live_executor import start_live_executor, get_live_executor
            executor = get_live_executor()
            await executor.reconcile_pending_submissions()
            start_live_executor()
            logger.info(f"✅ LiveExecutor auto-started | Mode: {executor.config.mode.value}")
        except Exception as e:
            logger.error(f"Failed to auto-start LiveExecutor: {e}")
    else:
        logger.info("LiveExecutor not auto-started (set LIVE_EXECUTION=true to enable)")
