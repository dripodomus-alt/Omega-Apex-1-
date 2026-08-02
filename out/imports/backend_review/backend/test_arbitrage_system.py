#!/usr/bin/env python3
"""
Test the full arbitrage system with real pool data
"""

import os
import sys
sys.path.insert(0, '/app/backend')
os.chdir('/app/backend')

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path('/app/backend/.env'))

from arbitrage_engine import ArbitrageEngine, get_arbitrage_engine, DexId, Protocol
from engine import Web3PoolScanner, POLYGON_POOLS
from titan_slippage import titan_engine


def main():
    print("=" * 60)
    print("APEX_OMEGA ARBITRAGE SYSTEM TEST")
    print("=" * 60)
    
    rpc_url = os.getenv('POLYGON_RPC_URL')
    engine = get_arbitrage_engine()
    
    print(f"\nConfiguration:")
    print(f"  Min Reserve: ${engine.min_reserve_usd:,.0f}")
    print(f"  Min Profit: ${engine.min_profit_usd}")
    print(f"  Flash Loan Fee: {engine.flash_loan_fee_bps} bps")
    print(f"  Gas Price: {engine.gas_price_gwei} gwei")
    print()
    
    # Populate with real pool data
    print("Loading pool data from Web3...")
    scanner = Web3PoolScanner(rpc_url)
    
    if not scanner.is_connected():
        print("ERROR: Web3 not connected")
        return
    
    print(f"Chain: {scanner.w3.eth.chain_id} | Block: {scanner.w3.eth.block_number}")
    
    pools = scanner.scan_all_pools()
    print(f"Scanned {len(pools)} pools")
    
    # Create synthetic pool data for testing spreads
    # (In production, this comes from multiple DEXes)
    test_pools = [
        # QuickSwap V3 USDC/WETH
        {
            'poolAddress': '0x45dDa9cb7c25131DF268515131f647d726f50608',
            'dexId': DexId.QUICKSWAP_V3,
            'token0': '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174',  # USDC
            'token1': '0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619',  # WETH
            'spotPrice': 0.000385,  # ETH/USDC
            'reserveUsd': 2_500_000,
            'protocol': Protocol.V3,
            'fee': 500,
        },
        # Uniswap V3 USDC/WETH (different price for arbitrage)
        {
            'poolAddress': '0x45dDa9cb7c25131DF268515131f647d726f50609',
            'dexId': DexId.UNISWAP_V3,
            'token0': '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174',  # USDC
            'token1': '0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619',  # WETH
            'spotPrice': 0.000390,  # Slightly higher
            'reserveUsd': 3_000_000,
            'protocol': Protocol.V3,
            'fee': 500,
        },
        # SushiSwap USDC/WMATIC
        {
            'poolAddress': '0xA374094527e1673A86dE625aa59517c5dE346d32',
            'dexId': DexId.SUSHISWAP,
            'token0': '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174',  # USDC
            'token1': '0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270',  # WMATIC
            'spotPrice': 2.10,  # MATIC/USDC
            'reserveUsd': 1_500_000,
            'protocol': Protocol.V2,
            'fee': 3000,
        },
        # QuickSwap V2 USDC/WMATIC
        {
            'poolAddress': '0x6e7a5FAFcec6BB1e78bAE2A1F0B612012BF14827',
            'dexId': DexId.QUICKSWAP_V2,
            'token0': '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174',  # USDC
            'token1': '0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270',  # WMATIC
            'spotPrice': 2.08,  # Slightly different price
            'reserveUsd': 2_000_000,
            'protocol': Protocol.V2,
            'fee': 3000,
        },
    ]
    
    print(f"\nLoading {len(test_pools)} test pools...")
    for pool_data in test_pools:
        engine.update_pool(pool_data)
    
    print(f"Total pools in engine: {len(engine.pools)}")
    
    # Scan for spreads
    print("\nScanning for spread opportunities...")
    spreads = engine.scan_for_spreads(loan_amount_usd=10000)
    
    print(f"\nFound {len(spreads)} potential spreads")
    
    # Show top opportunities
    executable = [s for s in spreads if s.flash_loan.is_executable]
    print(f"Executable opportunities: {len(executable)}")
    print()
    
    for i, spread in enumerate(spreads[:5]):
        fl = spread.flash_loan
        print(f"{'='*50}")
        print(f"Opportunity #{i+1}: {spread.token_pair}")
        print(f"  ID: {spread.id}")
        print(f"  Min Reserve: ${spread.min_reserve_usd:,.0f}")
        print()
        print(f"  Flash Loan:")
        print(f"    Amount: ${fl.loan_amount_usd:,.2f}")
        print(f"    Fee: ${fl.flash_loan_fee_usd:.4f} ({fl.flash_loan_fee_bps} bps)")
        print()
        
        if fl.leg1:
            print(f"  Leg 1 (Buy):")
            print(f"    DEX: {fl.leg1.dex}")
            print(f"    Pool: {fl.leg1.pool[:20]}...")
            print(f"    Amount In: ${fl.leg1.amount_in_usd:,.2f}")
            print(f"    Amount Out: ${fl.leg1.amount_out_usd:,.2f}")
            print(f"    Fee: ${fl.leg1.fee_paid_usd:.4f}")
            print(f"    Slippage: ${fl.leg1.slippage_usd:.4f}")
            print(f"    Spot Price: {fl.leg1.spot_price:.6f}")
            print(f"    Effective: {fl.leg1.effective_price:.6f}")
        
        if fl.leg2:
            print(f"  Leg 2 (Sell):")
            print(f"    DEX: {fl.leg2.dex}")
            print(f"    Pool: {fl.leg2.pool[:20]}...")
            print(f"    Amount In: ${fl.leg2.amount_in_usd:,.2f}")
            print(f"    Amount Out: ${fl.leg2.amount_out_usd:,.2f}")
            print(f"    Fee: ${fl.leg2.fee_paid_usd:.4f}")
            print(f"    Slippage: ${fl.leg2.slippage_usd:.4f}")
        
        print()
        print(f"  Summary:")
        print(f"    Total Fees: ${fl.total_fees_usd:.4f}")
        print(f"    Total Slippage: ${fl.total_slippage_usd:.4f}")
        print(f"    Gas Cost: ${fl.gas_cost_usd:.4f}")
        print(f"    Repay Amount: ${fl.repay_amount_usd:,.2f}")
        print(f"    Net Profit: ${fl.net_profit_usd:.4f}")
        print(f"    ROI: {fl.roi_percent:.4f}%")
        print(f"    Executable: {'YES ✓' if fl.is_executable else 'NO ✗'}")
    
    # Test API format
    print("\n" + "=" * 50)
    print("API Output Format Test:")
    data = engine.get_spreads()
    print(f"  Timestamp: {data['timestamp']}")
    print(f"  Spreads count: {len(data['spreads'])}")
    
    if data['spreads']:
        sample = data['spreads'][0]
        print(f"  Sample spread keys: {list(sample.keys())}")
        if sample.get('flashLoan'):
            print(f"  Flash loan keys: {list(sample['flashLoan'].keys())}")


if __name__ == "__main__":
    main()
