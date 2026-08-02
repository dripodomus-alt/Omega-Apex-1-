#!/usr/bin/env python3
"""
APEX_OMEGA Full Execution Test
Tests integration with deployed C1/C2 contracts
"""

import os
import sys
sys.path.insert(0, '/app/backend')
os.chdir('/app/backend')

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path('/app/backend/.env'))

from web3 import Web3
from contract_interface import (
    ApexContractExecutor,
    RouteBuilder,
    RouteEnvelope,
    RouteStep,
    Protocol,
    ROUTE_VERSION_1
)
from engine import Web3PoolScanner, C1Aggressor, SlippageSentinel, TITAN_ENABLED
from titan_slippage import titan_engine


def main():
    print("=" * 60)
    print("APEX_OMEGA CONTRACT INTEGRATION TEST")
    print("=" * 60)
    
    rpc_url = os.getenv('POLYGON_RPC_URL')
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    
    print(f"Chain: {w3.eth.chain_id}")
    print(f"Block: {w3.eth.block_number}")
    print(f"TITAN: {'ACTIVE' if TITAN_ENABLED else 'OFF'}")
    print()
    
    # Contract addresses (replace with your deployed addresses)
    C1_ADDRESS = os.getenv('C1_CONTRACT_ADDRESS', '')
    C2_ADDRESS = os.getenv('C2_CONTRACT_ADDRESS', '')
    
    if not C1_ADDRESS and not C2_ADDRESS:
        print("NOTE: No contract addresses configured in .env")
        print("Add C1_CONTRACT_ADDRESS and/or C2_CONTRACT_ADDRESS")
        print()
        print("Running route builder test...")
        print()
    
    # Test route building
    print("Building sample arbitrage route...")
    
    route = RouteBuilder.build_simple_arb_route(
        token_a=RouteBuilder.TOKENS['USDC'],
        token_b=RouteBuilder.TOKENS['WETH'],
        amount=int(1000 * 1e6),  # 1000 USDC
        executor_address='0x0000000000000000000000000000000000000000',  # Placeholder
        buy_router=RouteBuilder.ROUTERS['QUICKSWAP_V3'],
        sell_router=RouteBuilder.ROUTERS['UNISWAP_V3'],
        buy_protocol=Protocol.QUICKSWAP_V3,
        sell_protocol=Protocol.UNISWAP_V3,
        fee_tier=500,  # 0.05%
        slippage_bps=50  # 0.5%
    )
    
    print(f"Route built:")
    print(f"  Version: {route.version}")
    print(f"  Steps: {len(route.steps)}")
    print(f"  Gas Reserve: {route.gas_reserve_asset / 1e6:.4f} USDC")
    print(f"  DEX Fee Reserve: {route.dex_fee_reserve_asset / 1e6:.4f} USDC")
    print()
    
    for i, step in enumerate(route.steps):
        print(f"  Step {i+1}:")
        print(f"    Protocol: {Protocol(step.protocol).name}")
        print(f"    Target: {step.target[:20]}...")
        print(f"    Approve: {step.approve_token[:20]}...")
        print(f"    Min Out: {step.min_amount_out}")
        print(f"    Data: {len(step.data)} bytes")
    print()
    
    # Encode route
    encoded = route.encode()
    print(f"Encoded route: {len(encoded)} bytes")
    print(f"Route hash: {Web3.keccak(encoded).hex()[:20]}...")
    print()
    
    # Test executor (dry run)
    if C1_ADDRESS or C2_ADDRESS:
        print("Testing contract executor (dry run)...")
        executor = ApexContractExecutor(
            w3=w3,
            c1_address=C1_ADDRESS if C1_ADDRESS else None,
            c2_address=C2_ADDRESS if C2_ADDRESS else None
        )
        
        if C1_ADDRESS:
            c1 = executor.c1
            print(f"C1 Contract:")
            print(f"  Address: {c1.address}")
            try:
                print(f"  Owner: {c1.get_owner()}")
                print(f"  Vault Mode: {c1.get_vault_mode()}")
            except Exception as e:
                print(f"  (Unable to read contract state: {e})")
        
        result = executor.execute_arbitrage(
            asset=RouteBuilder.TOKENS['USDC'],
            amount=int(1000 * 1e6),
            min_profit=int(5 * 1e6),  # 5 USDC min profit
            route=route,
            use_c1=bool(C1_ADDRESS),
            dry_run=True
        )
        
        print(f"Dry run result: {result}")
    else:
        print("Contract execution skipped (no addresses configured)")
    
    print()
    print("=" * 60)
    print("INTEGRATION TEST COMPLETE")
    print("=" * 60)
    print()
    print("To enable live execution:")
    print("1. Add to .env:")
    print("   C1_CONTRACT_ADDRESS=<your C1 address>")
    print("   C2_CONTRACT_ADDRESS=<your C2 address>")
    print("   PRIVATE_KEY=<your wallet private key>")
    print("2. Fund wallet with MATIC for gas")
    print("3. Ensure wallet is contract owner (for Merkle root updates)")


if __name__ == "__main__":
    main()
