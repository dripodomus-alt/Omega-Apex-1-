#!/usr/bin/env python3
"""
INSTITUTIONAL MATH INTEGRATION TEST
Tests complete pipeline: Optimal sizing → Depth validation → Gas optimization → SSOT → Execution
"""

import logging
import os
from web3 import Web3
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / '.env')

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)

from institutional_integration import get_institutional_coordinator

def test_institutional_math():
    """
    Test complete institutional math integration
    Uses realistic Polygon pool data
    """
    
    print("=" * 80)
    print("INSTITUTIONAL MATH INTEGRATION TEST")
    print("=" * 80)
    
    # Initialize Web3
    rpc_url = os.getenv('POLYGON_RPC_URL')
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    
    if not w3.is_connected():
        print("❌ FAILED: Cannot connect to RPC")
        return False
    
    print(f"\n✅ Connected to Polygon (Block: {w3.eth.block_number:,})")
    
    # Get coordinator
    coordinator = get_institutional_coordinator(w3)
    print(f"✅ Institutional coordinator initialized")
    
    # ========================================================================
    # TEST CASE 1: Profitable USDC/WETH Arbitrage
    # ========================================================================
    print(f"\n" + "=" * 80)
    print("TEST CASE 1: Profitable USDC/WETH Arbitrage")
    print("=" * 80)
    
    # Simulated pool data (realistic Polygon values)
    # Pool 1 (QuickSwap): USDC/WETH, slightly underpriced WETH
    pool1_reserve_usdc = 50_000  # $50k USDC
    pool1_reserve_weth = 20.5    # 20.5 WETH @ $2,439/WETH
    pool1_fee_bps = 30           # 0.3%
    
    # Pool 2 (SushiSwap): USDC/WETH, slightly overpriced WETH  
    pool2_reserve_usdc = 45_000  # $45k USDC
    pool2_reserve_weth = 18.2    # 18.2 WETH @ $2,473/WETH
    pool2_fee_bps = 30           # 0.3%
    
    # Price spread: ~1.4% ($2,473 - $2,439) / $2,439
    
    result = coordinator.analyze_opportunity(
        pool1_reserve_in=pool1_reserve_usdc,
        pool1_reserve_out=pool1_reserve_weth,
        pool1_fee_bps=pool1_fee_bps,
        pool2_reserve_in=pool2_reserve_weth,  # Reversed for return swap
        pool2_reserve_out=pool2_reserve_usdc,
        pool2_fee_bps=pool2_fee_bps,
        token_pair="USDC/WETH",
        buy_dex="QuickSwap V2",
        sell_dex="SushiSwap V2",
        buy_pool_address="0x1234...",
        sell_pool_address="0x5678...",
        token_price_usd=1.0,  # USDC = $1
        max_loan_usd=10_000,
        min_profit_usd=5.0
    )
    
    if result:
        print(f"\n📊 RESULT:")
        print(f"   SSN: {result.ssn}")
        print(f"   Optimal Loan: ${result.optimal_loan_amount:,.2f}")
        print(f"   Net Profit: ${result.net_profit_usd:,.2f}")
        print(f"   ROI: {result.roi_percent:.4f}%")
        print(f"   EV: ${result.ev:,.2f}")
        print(f"   Flash Provider: {result.flash_provider} ({result.flash_fee_bps} bps)")
        print(f"   Gas Cost: ${result.gas_cost_usd:.4f}")
        print(f"   P(fill): {result.tip_recommendation.p_fill:.4f}")
        print(f"   C2 Decision: {result.c2_decision}")
        print(f"   Executable: {'✅ YES' if result.is_executable else '❌ NO'}")
        
        if not result.is_executable:
            print(f"   Rejection: {result.rejection_reason}")
        
        print(f"\n📋 EXECUTION TRACE ({len(result.execution_trace)} steps):")
        for i, trace in enumerate(result.execution_trace, 1):
            status = "✅" if trace.passed else "❌"
            print(f"   {i}. {status} {trace.step_name} ({trace.duration_ms:.2f}ms)")
            if not trace.passed:
                print(f"      Reason: {trace.reason}")
        
        print(f"\n✅ TEST CASE 1: PASSED")
        return True
    else:
        print(f"\n❌ TEST CASE 1: FAILED - No opportunity returned")
        return False


if __name__ == "__main__":
    success = test_institutional_math()
    exit(0 if success else 1)
