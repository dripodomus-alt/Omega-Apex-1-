"""
APEX_OMEGA Curve On-Chain Integration
Direct calls to Curve pool contracts for exact stable swap calculations

Eliminates approximation errors by using actual pool view functions.
"""

from web3 import Web3
from typing import Dict, Optional
import logging
import os

logger = logging.getLogger(__name__)


# Curve StableSwap ABI (view functions only)
CURVE_POOL_ABI = [
    {
        "name": "get_dy",
        "outputs": [{"type": "uint256", "name": ""}],
        "inputs": [
            {"type": "int128", "name": "i"},
            {"type": "int128", "name": "j"},
            {"type": "uint256", "name": "dx"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "name": "get_dx",
        "outputs": [{"type": "uint256", "name": ""}],
        "inputs": [
            {"type": "int128", "name": "i"},
            {"type": "int128", "name": "j"},
            {"type": "uint256", "name": "dy"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "name": "balances",
        "outputs": [{"type": "uint256", "name": ""}],
        "inputs": [{"type": "uint256", "name": "arg0"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "name": "A",
        "outputs": [{"type": "uint256", "name": ""}],
        "inputs": [],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "name": "fee",
        "outputs": [{"type": "uint256", "name": ""}],
        "inputs": [],
        "stateMutability": "view",
        "type": "function"
    }
]


class CurveOnChainCalculator:
    """
    Production-grade Curve calculations using on-chain view functions.
    
    Eliminates iterative solving errors by calling pool contracts directly.
    """
    
    def __init__(self, web3_provider: Optional[Web3] = None):
        """
        Initialize with Web3 provider.
        
        Args:
            web3_provider: Web3 instance. If None, creates from env POLYGON_RPC_URL
        """
        if web3_provider is None:
            rpc_url = os.environ.get('POLYGON_RPC_URL', 'https://polygon-rpc.com')
            self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        else:
            self.w3 = web3_provider
        
        if not self.w3.is_connected():
            logger.error("⚠️  Web3 not connected. Curve on-chain calls will fail.")
        else:
            logger.info(f"✅ Curve calculator connected to {self.w3.provider.endpoint_uri}")
    
    def get_dy_exact(
        self,
        pool_address: str,
        i: int,
        j: int,
        amount_in: float,
        decimals_in: int = 6,  # USDC default
        decimals_out: int = 6
    ) -> Dict[str, float]:
        """
        Get exact output amount from Curve pool contract.
        
        Args:
            pool_address: Curve pool contract address
            i: Input coin index (0, 1, 2, ...)
            j: Output coin index
            amount_in: Input amount (human-readable, e.g., 1000.0 USDC)
            decimals_in: Input token decimals
            decimals_out: Output token decimals
        
        Returns:
            {
                'amount_out': float,
                'slippage': float,
                'execution_price': float,
                'method': 'on_chain_get_dy'
            }
        """
        try:
            # Convert to Wei/smallest unit
            amount_in_wei = int(amount_in * (10 ** decimals_in))
            
            # Create contract instance
            pool = self.w3.eth.contract(
                address=Web3.to_checksum_address(pool_address),
                abi=CURVE_POOL_ABI
            )
            
            # Call get_dy (exact output for exact input)
            amount_out_wei = pool.functions.get_dy(i, j, amount_in_wei).call()
            
            # Convert back to human-readable
            amount_out = amount_out_wei / (10 ** decimals_out)
            
            # For stable swaps, spot price ≈ 1.0
            spot_price = 1.0
            execution_price = amount_in / amount_out if amount_out > 0 else 0
            slippage = abs(execution_price - spot_price) / spot_price if spot_price > 0 else 0
            
            logger.info(f"✅ Curve on-chain: ${amount_in:.2f} → ${amount_out:.2f} (slippage: {slippage*100:.3f}%)")
            
            return {
                'amount_out': amount_out,
                'slippage': slippage,
                'execution_price': execution_price,
                'method': 'on_chain_get_dy',
                'pool_address': pool_address
            }
        
        except Exception as e:
            logger.error(f"❌ Curve on-chain call failed: {e}")
            raise
    
    def get_dx_exact(
        self,
        pool_address: str,
        i: int,
        j: int,
        amount_out: float,
        decimals_in: int = 6,
        decimals_out: int = 6
    ) -> Dict[str, float]:
        """
        Get exact input amount needed for desired output (exact-output swap).
        
        Args:
            pool_address: Curve pool contract address
            i: Input coin index
            j: Output coin index
            amount_out: Desired output amount
            decimals_in: Input token decimals
            decimals_out: Output token decimals
        
        Returns:
            {
                'amount_in': float,
                'slippage': float,
                'method': 'on_chain_get_dx'
            }
        """
        try:
            # Convert to Wei
            amount_out_wei = int(amount_out * (10 ** decimals_out))
            
            # Create contract instance
            pool = self.w3.eth.contract(
                address=Web3.to_checksum_address(pool_address),
                abi=CURVE_POOL_ABI
            )
            
            # Call get_dx (exact input for exact output)
            amount_in_wei = pool.functions.get_dx(i, j, amount_out_wei).call()
            
            # Convert back
            amount_in = amount_in_wei / (10 ** decimals_in)
            
            # Calculate slippage
            spot_price = 1.0
            execution_price = amount_in / amount_out if amount_out > 0 else 0
            slippage = abs(execution_price - spot_price) / spot_price
            
            return {
                'amount_in': amount_in,
                'slippage': slippage,
                'execution_price': execution_price,
                'method': 'on_chain_get_dx',
                'pool_address': pool_address
            }
        
        except Exception as e:
            logger.error(f"❌ Curve get_dx failed: {e}")
            raise
    
    def get_pool_info(self, pool_address: str, num_coins: int = 2) -> Dict:
        """
        Fetch pool metadata (A coefficient, fee, balances).
        
        Args:
            pool_address: Curve pool address
            num_coins: Number of coins in pool (2, 3, 4, etc.)
        
        Returns:
            {
                'A': int,
                'fee': float,
                'balances': List[float]
            }
        """
        try:
            pool = self.w3.eth.contract(
                address=Web3.to_checksum_address(pool_address),
                abi=CURVE_POOL_ABI
            )
            
            # Get A coefficient
            A = pool.functions.A().call()
            
            # Get fee (in basis points, e.g., 4000000 = 0.04%)
            fee_raw = pool.functions.fee().call()
            fee = fee_raw / 1e10  # Convert to decimal
            
            # Get balances
            balances = []
            for i in range(num_coins):
                try:
                    balance_wei = pool.functions.balances(i).call()
                    balances.append(balance_wei / 1e6)  # Assume 6 decimals (USDC/USDT)
                except:
                    break
            
            logger.info(f"✅ Curve pool {pool_address[:10]}... A={A}, fee={fee*100:.3f}%")
            
            return {
                'A': A,
                'fee': fee,
                'balances': balances,
                'num_coins': len(balances)
            }
        
        except Exception as e:
            logger.error(f"❌ Failed to fetch Curve pool info: {e}")
            return {
                'A': 100,
                'fee': 0.0004,
                'balances': [],
                'num_coins': 0
            }


# ============================================================================
# SINGLETON + CACHE
# ============================================================================

_curve_calculator = None
_pool_info_cache = {}


def get_curve_calculator() -> CurveOnChainCalculator:
    """Get singleton Curve calculator."""
    global _curve_calculator
    if _curve_calculator is None:
        _curve_calculator = CurveOnChainCalculator()
    return _curve_calculator


def calculate_curve_swap_onchain(
    pool_address: str,
    i: int,
    j: int,
    amount_in: float,
    decimals_in: int = 6,
    decimals_out: int = 6
) -> Dict[str, float]:
    """
    Convenience function for on-chain Curve swap calculation.
    
    Caches pool info for performance.
    """
    calculator = get_curve_calculator()
    
    # Get cached pool info
    if pool_address not in _pool_info_cache:
        _pool_info_cache[pool_address] = calculator.get_pool_info(pool_address)
    
    # Calculate swap
    result = calculator.get_dy_exact(pool_address, i, j, amount_in, decimals_in, decimals_out)
    
    # Add pool info to result
    result['pool_info'] = _pool_info_cache[pool_address]
    
    return result
