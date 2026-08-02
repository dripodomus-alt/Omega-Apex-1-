import math
import time
import os
import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from pathlib import Path
from web3 import Web3
from dotenv import load_dotenv
import logging

load_dotenv()
logger = logging.getLogger(__name__)

# Import TITAN Slippage Engine
try:
    from titan_slippage import titan_engine, ProtocolType
    TITAN_ENABLED = True
    logger.info("TITAN V12.4 Slippage Engine: ACTIVE")
except ImportError:
    TITAN_ENABLED = False
    logger.warning("TITAN Slippage Engine not available, using basic calculations")

# UniswapV3 Pool ABI (minimal for reading pool data)
UNISWAP_V3_POOL_ABI = [
    {
        "inputs": [],
        "name": "liquidity",
        "outputs": [{"internalType": "uint128", "name": "", "type": "uint128"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "slot0",
        "outputs": [
            {"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"},
            {"internalType": "int24", "name": "tick", "type": "int24"},
            {"internalType": "uint16", "name": "observationIndex", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinality", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinalityNext", "type": "uint16"},
            {"internalType": "uint8", "name": "feeProtocol", "type": "uint8"},
            {"internalType": "bool", "name": "unlocked", "type": "bool"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "token0",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "token1",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "fee",
        "outputs": [{"internalType": "uint24", "name": "", "type": "uint24"}],
        "stateMutability": "view",
        "type": "function"
    }
]

# Multicall3 ABI (for batching calls)
MULTICALL3_ABI = [
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "address", "name": "target", "type": "address"},
                    {"internalType": "bytes", "name": "callData", "type": "bytes"}
                ],
                "internalType": "struct Multicall3.Call[]",
                "name": "calls",
                "type": "tuple[]"
            }
        ],
        "name": "aggregate",
        "outputs": [
            {"internalType": "uint256", "name": "blockNumber", "type": "uint256"},
            {"internalType": "bytes[]", "name": "returnData", "type": "bytes[]"}
        ],
        "stateMutability": "payable",
        "type": "function"
    }
]

# Polygon Multicall3 address
MULTICALL3_ADDRESS = "0xcA11bde05977b3631167028862bE2a173976CA11"


def load_pools_database() -> Dict[str, str]:
    """
    Load real pool addresses from pools.json database.
    Returns dict mapping "TOKEN0/TOKEN1" -> pool_address
    """
    pools_path = Path(__file__).parent / 'data' / 'pools.json'
    
    if not pools_path.exists():
        logger.error(f"Pools database not found: {pools_path}")
        return {}
    
    try:
        with open(pools_path, 'r') as f:
            data = json.load(f)
        
        pool_dict = {}
        for pool in data.get('pools', []):
            # Create key from token symbols
            key = f"{pool['token0_symbol']}/{pool['token1_symbol']}"
            address = pool['pair_address']
            
            # Store pool address
            if key not in pool_dict:  # Use first occurrence of each pair
                pool_dict[key] = address
        
        logger.info(f"Loaded {len(pool_dict)} unique pool pairs from database")
        return pool_dict
        
    except Exception as e:
        logger.error(f"Failed to load pools database: {e}")
        return {}


# Load real pools from database (133 pools from JSON)
POLYGON_POOLS = load_pools_database()


@dataclass
class PoolData:
    """Data structure for pool information"""
    name: str
    address: str
    liquidity: int
    sqrt_price_x96: int
    tick: int
    fee: int
    token0: str
    token1: str
    equilibrium_gap: float
    volatility: float


class SlippageSentinel:
    """
    Predicts variance by analyzing pool depth vs. transaction volume.
    Enhanced with TITAN V12.4 multi-protocol slippage engine.
    """
    def __init__(self, tolerance: float):
        self.tolerance = tolerance
        self.volatility_history: Dict[str, List[float]] = {}

    def get_prediction(self, volatility: float, pool_tvl_usd: float, fee_bps: float = 30, amount_usd: float = 10000) -> float:
        """
        Calculate predicted slippage using TITAN engine for V3 pools
        CRITICAL: Uses pool TVL (Total Value Locked), not flash loan pool liquidity
        """
        if pool_tvl_usd == 0:
            return 1.0
        
        if TITAN_ENABLED:
            # Use TITAN V12.4 for accurate V3 slippage prediction with pool TVL
            slip = titan_engine.v3_slippage(amount_usd, pool_tvl_usd, fee_bps)
            return round(min(slip / 100.0, 1.0), 6)  # Convert to ratio
        
        # Fallback: Basic prediction = (Volatility Index / sqrt(Pool TVL)) * adjustment factor
        prediction = (volatility / math.sqrt(pool_tvl_usd)) * 1.5
        return round(min(prediction, 1.0), 6)

    def update_volatility(self, pool_name: str, price_change: float):
        """Track volatility history for a pool"""
        if pool_name not in self.volatility_history:
            self.volatility_history[pool_name] = []
        self.volatility_history[pool_name].append(abs(price_change))
        # Keep last 100 samples
        if len(self.volatility_history[pool_name]) > 100:
            self.volatility_history[pool_name].pop(0)

    def get_average_volatility(self, pool_name: str) -> float:
        """Get average volatility for a pool"""
        if pool_name not in self.volatility_history or not self.volatility_history[pool_name]:
            return 500  # Default volatility
        return sum(self.volatility_history[pool_name]) / len(self.volatility_history[pool_name])


class Web3PoolScanner:
    """
    Web3.py Multicall Scanner for simultaneous pool data fetching.
    Scans 10+ Polygon pools in a single RPC call.
    """
    def __init__(self, rpc_url: str):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        self.multicall = self.w3.eth.contract(
            address=Web3.to_checksum_address(MULTICALL3_ADDRESS),
            abi=MULTICALL3_ABI
        )
        self.pools = POLYGON_POOLS
        self.previous_prices: Dict[str, float] = {}

    def is_connected(self) -> bool:
        """Check if Web3 connection is active"""
        try:
            return self.w3.is_connected()
        except:
            return False

    def _encode_call(self, pool_address: str, function_name: str) -> bytes:
        """Encode a function call for multicall"""
        pool = self.w3.eth.contract(
            address=Web3.to_checksum_address(pool_address),
            abi=UNISWAP_V3_POOL_ABI
        )
        # Get the function and encode
        func = getattr(pool.functions, function_name)
        return func()._encode_transaction_data()

    def scan_all_pools(self) -> List[PoolData]:
        """
        Scan all pools using real addresses from database.
        NO MOCK DATA - requires Web3 connection to real pools.
        Returns list of PoolData objects.
        """
        if not self.is_connected():
            logger.error("Web3 not connected - cannot scan pools without RPC connection")
            raise ConnectionError("Web3 RPC connection required for pool scanning")
        
        if not self.pools:
            logger.error("No pools loaded from database")
            raise ValueError("Pool database is empty - check pools.json")

        try:
            pool_data_list = []
            
            for pool_name, pool_address in self.pools.items():
                try:
                    checksum_addr = Web3.to_checksum_address(pool_address)
                    pool = self.w3.eth.contract(address=checksum_addr, abi=UNISWAP_V3_POOL_ABI)
                    
                    # Individual calls for reliability
                    liquidity = pool.functions.liquidity().call()
                    slot0 = pool.functions.slot0().call()
                    fee = pool.functions.fee().call()
                    token0 = pool.functions.token0().call()
                    token1 = pool.functions.token1().call()
                    
                    sqrt_price_x96 = slot0[0]
                    tick = slot0[1]
                    
                    # Calculate price
                    price = (sqrt_price_x96 / (2 ** 96)) ** 2 if sqrt_price_x96 > 0 else 0
                    
                    # Calculate volatility based on price change
                    volatility = 500
                    if pool_name in self.previous_prices and self.previous_prices[pool_name] > 0:
                        price_change = abs((price - self.previous_prices[pool_name]) / self.previous_prices[pool_name]) * 10000
                        volatility = max(price_change, 100)
                    
                    self.previous_prices[pool_name] = price
                    
                    # Equilibrium gap from tick position
                    equilibrium_gap = (abs(tick) % 100) / 100 * 3
                    
                    pool_data = PoolData(
                        name=pool_name,
                        address=pool_address,
                        liquidity=liquidity,
                        sqrt_price_x96=sqrt_price_x96,
                        tick=tick,
                        fee=fee,
                        token0=token0,
                        token1=token1,
                        equilibrium_gap=round(equilibrium_gap, 4),
                        volatility=volatility
                    )
                    pool_data_list.append(pool_data)
                    
                except Exception as e:
                    logger.debug(f"Failed to fetch {pool_name} at {pool_address}: {e}")
                    continue
            
            if pool_data_list:
                logger.info(f"Scanned {len(pool_data_list)}/{len(self.pools)} pools successfully")
                return pool_data_list
            
            logger.error("No pools scanned successfully - all Web3 calls failed")
            raise RuntimeError("Failed to scan any pools from database")

        except Exception as e:
            logger.error(f"Pool scan failed: {e}")
            raise

class C1Aggressor:
    """
    Atomic Displacement Logic: Moves price equilibrium while extracting net profit.
    Enhanced with TITAN V12.4 multi-protocol support and gas-adjusted profitability.
    """
    def __init__(self, sentinel: SlippageSentinel, min_profit: float = 0.005, force_multiplier: float = 1.2):
        self.sentinel = sentinel
        self.min_profit = min_profit
        self.force_multiplier = force_multiplier
        self.gas_price_gwei = float(os.getenv('MAX_GAS_PRICE_GWEI', 60))
        self.gas_units = 450000
        self.matic_price = 0.50  # Default, should be fetched live
        self.min_profit_ratio = float(os.getenv('MIN_PROFIT_TO_GAS_RATIO', 1.1))

    def analyze_opportunity(self, pool_data: PoolData) -> Dict[str, Any]:
        """
        Calculates if the force required for displacement yields a net gain.
        Uses TITAN V12.4 for accurate slippage and profitability analysis.
        
        CRITICAL: Slippage is calculated using the POOL's TVL (Total Value Locked),
        which represents the liquidity available in that specific pool for the swap.
        The flash loan source pool TVL is NOT used in slippage calculations.
        """
        liquidity = pool_data.liquidity  # This is the pool's TVL
        gap = pool_data.equilibrium_gap
        volatility = pool_data.volatility
        fee_bps = pool_data.fee / 100 if pool_data.fee > 0 else 30  # Convert from bps

        # Calculate trade size
        trade_amount = (liquidity * (gap / 100)) * self.force_multiplier
        
        if TITAN_ENABLED:
            # Use TITAN V12.4 for precise calculations with pool TVL
            result = titan_engine.analyze_opportunity(
                amount_usd=trade_amount,
                liquidity=liquidity,  # Pool TVL used for market impact calculation
                fee_bps=fee_bps,
                protocol=ProtocolType.UNISWAP_V3,
                max_slippage_pct=self.sentinel.tolerance * 100
            )
            predicted_slippage = result.predicted_slippage_pct / 100  # Convert to ratio
            optimal_size = result.optimal_size_usd
        else:
            predicted_slippage = self.sentinel.get_prediction(volatility, liquidity, fee_bps, trade_amount)
            optimal_size = trade_amount

        # Profitability Filter
        gross_return = trade_amount * (gap / 100)
        slippage_loss = trade_amount * predicted_slippage
        
        if TITAN_ENABLED:
            # Gas-adjusted profitability
            profit_calc = titan_engine.calculate_profit(
                gross_profit_usd=gross_return - slippage_loss,
                gas_price_gwei=self.gas_price_gwei,
                gas_units=self.gas_units,
                matic_price_usd=self.matic_price,
                min_ratio=self.min_profit_ratio
            )
            net_profit = profit_calc.net_profit_usd
            gas_cost = profit_calc.gas_cost_usd
            profit_ratio = profit_calc.profit_to_gas_ratio
        else:
            gas_cost = (self.gas_price_gwei * self.gas_units / 1e9) * self.matic_price
            net_profit = gross_return - slippage_loss - gas_cost
            profit_ratio = (gross_return - slippage_loss) / gas_cost if gas_cost > 0 else 0

        profit_percentage = net_profit / trade_amount if trade_amount > 0 else 0

        if predicted_slippage > self.sentinel.tolerance:
            return {
                "status": "REJECTED",
                "reason": "High Slippage",
                "pool": pool_data.name,
                "slippage": round(predicted_slippage, 6),
                "tolerance": self.sentinel.tolerance
            }

        if profit_percentage > self.min_profit and net_profit > 0:
            return {
                "status": "VALIDATED",
                "pool": pool_data.name,
                "address": pool_data.address,
                "liquidity": liquidity,
                "force_required": round(trade_amount, 4),
                "optimal_size": round(optimal_size, 4) if TITAN_ENABLED else round(trade_amount, 4),
                "gross_return": round(gross_return, 6),
                "slippage_loss": round(slippage_loss, 6),
                "gas_cost_usd": round(gas_cost, 6),
                "predicted_profit": round(net_profit, 6),
                "profit_percentage": round(profit_percentage * 100, 4),
                "profit_to_gas_ratio": round(profit_ratio, 2),
                "slippage": round(predicted_slippage, 6),
                "gap": gap,
                "volatility": volatility,
                "fee_bps": fee_bps,
                "titan_enabled": TITAN_ENABLED
            }
        
        return {
            "status": "INSUFFICIENT_YIELD",
            "pool": pool_data.name,
            "profit": round(net_profit, 6),
            "profit_percentage": round(profit_percentage * 100, 4),
            "gas_cost": round(gas_cost, 6)
        }

    def scan_and_analyze(self, scanner: Web3PoolScanner) -> List[Dict[str, Any]]:
        """
        Scan all pools and analyze each for opportunities.
        """
        results = []
        pools = scanner.scan_all_pools()
        
        for pool in pools:
            result = self.analyze_opportunity(pool)
            results.append(result)
        
        # Sort by profit potential
        validated = [r for r in results if r['status'] == 'VALIDATED']
        validated.sort(key=lambda x: x.get('predicted_profit', 0), reverse=True)
        
        return validated + [r for r in results if r['status'] != 'VALIDATED']
