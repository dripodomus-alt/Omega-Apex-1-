#!/usr/bin/env python3
"""
APEX_OMEGA EXECUTION ORCHESTRATOR
Bridges scanning to actual trade execution
"""

import os
import sys
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
os.chdir(str(BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / '.env')

from web3 import Web3
from engine import Web3PoolScanner, C1Aggressor, SlippageSentinel, TITAN_ENABLED, POLYGON_POOLS
from titan_slippage import titan_engine, ProtocolType

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger('EXECUTOR')


class ExecutionMode(Enum):
    DRY_RUN = "dry_run"
    SIMULATION = "simulation"  
    LIVE = "live"


@dataclass
class ExecutionConfig:
    """Execution parameters"""
    mode: ExecutionMode = ExecutionMode.DRY_RUN
    private_key: Optional[str] = None
    max_gas_gwei: float = 60
    max_position_usd: float = 1000
    min_profit_usd: float = 5.0
    slippage_tolerance: float = 0.03
    

class ApexExecutor:
    """
    Trade Executor for APEX_OMEGA
    Handles the bridge from opportunity detection to execution
    """
    
    # QuickSwap V3 Router on Polygon
    QUICKSWAP_ROUTER = "0xf5b509bB0909a69B1c207E495f687a596C168E12"
    
    # Uniswap V3 Router on Polygon  
    UNISWAP_ROUTER = "0xE592427A0AEce92De3Edee1F18E0157C05861564"
    
    def __init__(self, config: ExecutionConfig):
        self.config = config
        self.rpc_url = os.getenv('POLYGON_RPC_URL')
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        
        # Initialize scanner & analyzer
        self.scanner = Web3PoolScanner(self.rpc_url)
        self.sentinel = SlippageSentinel(tolerance=config.slippage_tolerance)
        self.aggressor = C1Aggressor(self.sentinel)
        
        # Execution wallet
        self.wallet = None
        if config.private_key and config.mode == ExecutionMode.LIVE:
            self.wallet = self.w3.eth.account.from_key(config.private_key)
            logger.info(f"Wallet loaded: {self.wallet.address}")
    
    def scan_opportunities(self) -> list:
        """Scan all pools for opportunities"""
        results = self.aggressor.scan_and_analyze(self.scanner)
        validated = [r for r in results if r['status'] == 'VALIDATED']
        return sorted(validated, key=lambda x: x.get('predicted_profit', 0), reverse=True)
    
    def validate_opportunity(self, opp: Dict[str, Any]) -> bool:
        """Pre-execution validation"""
        # Check minimum profit
        if opp.get('predicted_profit', 0) < self.config.min_profit_usd:
            logger.info(f"Skipping {opp['pool']}: profit ${opp['predicted_profit']:.4f} < min ${self.config.min_profit_usd}")
            return False
        
        # Check gas ratio
        if opp.get('profit_to_gas_ratio', 0) < 1.5:
            logger.info(f"Skipping {opp['pool']}: gas ratio {opp['profit_to_gas_ratio']:.1f}x too low")
            return False
        
        # Check position size
        if opp.get('optimal_size', opp.get('force_required', 0)) > self.config.max_position_usd:
            logger.info(f"Skipping {opp['pool']}: size ${opp.get('optimal_size', 0):.2f} > max ${self.config.max_position_usd}")
            return False
        
        return True
    
    def build_swap_params(self, opp: Dict[str, Any]) -> Dict[str, Any]:
        """Build swap transaction parameters"""
        pool_address = opp['address']
        amount_in = int(opp.get('optimal_size', opp['force_required']) * 1e6)  # USDC has 6 decimals
        
        # Deadline: 5 minutes from now
        deadline = int(time.time()) + 300
        
        # Min amount out with slippage protection
        expected_out = amount_in * (1 - opp['slippage'])
        min_amount_out = int(expected_out * (1 - self.config.slippage_tolerance))
        
        return {
            'pool': opp['pool'],
            'pool_address': pool_address,
            'amount_in': amount_in,
            'min_amount_out': min_amount_out,
            'deadline': deadline,
            'gas_limit': 450000,
            'gas_price': int(self.config.max_gas_gwei * 1e9)
        }
    
    def execute_swap(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the swap transaction"""
        if self.config.mode == ExecutionMode.DRY_RUN:
            logger.info(f"[DRY RUN] Would execute: {params['pool']} | Amount: {params['amount_in']/1e6:.2f} USDC")
            return {'status': 'dry_run', 'params': params}
        
        if self.config.mode == ExecutionMode.SIMULATION:
            # Simulate using eth_call
            logger.info(f"[SIMULATION] Simulating: {params['pool']}")
            # Add simulation logic here
            return {'status': 'simulated', 'params': params}
        
        if self.config.mode == ExecutionMode.LIVE:
            if not self.wallet:
                raise ValueError("No wallet configured for live execution")
            
            logger.warning(f"[LIVE] Executing: {params['pool']} | Amount: {params['amount_in']/1e6:.2f} USDC")
            # Build and sign transaction
            # tx = self._build_transaction(params)
            # signed = self.w3.eth.account.sign_transaction(tx, self.wallet.key)
            # tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)
            # return {'status': 'submitted', 'tx_hash': tx_hash.hex()}
            return {'status': 'live_disabled', 'message': 'Live execution requires additional setup'}
        
        return {'status': 'unknown_mode'}
    
    def run_cycle(self) -> Dict[str, Any]:
        """Run one execution cycle"""
        logger.info("=" * 60)
        logger.info(f"APEX_OMEGA Execution Cycle | Mode: {self.config.mode.value}")
        logger.info(f"Block: {self.w3.eth.block_number} | TITAN: {'ON' if TITAN_ENABLED else 'OFF'}")
        
        # Scan for opportunities
        opportunities = self.scan_opportunities()
        logger.info(f"Found {len(opportunities)} validated opportunities")
        
        executed = []
        for opp in opportunities[:3]:  # Process top 3
            if self.validate_opportunity(opp):
                params = self.build_swap_params(opp)
                result = self.execute_swap(params)
                executed.append({
                    'pool': opp['pool'],
                    'profit': opp['predicted_profit'],
                    'result': result
                })
        
        return {
            'opportunities_found': len(opportunities),
            'executed': executed,
            'block': self.w3.eth.block_number
        }


def main():
    """Main execution entry point"""
    config = ExecutionConfig(
        mode=ExecutionMode.DRY_RUN,  # Start with dry run
        max_gas_gwei=float(os.getenv('MAX_GAS_PRICE_GWEI', 60)),
        max_position_usd=1000,
        min_profit_usd=5.0,
        slippage_tolerance=0.03
    )
    
    executor = ApexExecutor(config)
    
    print("\n" + "=" * 60)
    print("APEX_OMEGA EXECUTION SYSTEM")
    print("=" * 60)
    print(f"Mode: {config.mode.value.upper()}")
    print(f"Max Position: ${config.max_position_usd}")
    print(f"Min Profit: ${config.min_profit_usd}")
    print(f"Max Gas: {config.max_gas_gwei} gwei")
    print("=" * 60 + "\n")
    
    # Run one cycle
    result = executor.run_cycle()
    
    print("\n" + "=" * 60)
    print("CYCLE COMPLETE")
    print(f"Opportunities: {result['opportunities_found']}")
    print(f"Executed: {len(result['executed'])}")
    for ex in result['executed']:
        print(f"  - {ex['pool']}: ${ex['profit']:.4f} -> {ex['result']['status']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
