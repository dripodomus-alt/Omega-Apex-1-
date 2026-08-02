#!/usr/bin/env python3
"""
START LIVE EXECUTOR WITH WEBSOCKET - REAL-TIME ARBITRAGE
Uses your private Alchemy WSS for mempool monitoring
"""

import asyncio
import logging
from live_executor import LiveExecutor, ExecutorConfig, ExecutionMode, initialize_arbitrage_system

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)

async def main():
    print("=" * 80)
    print("STARTING LIVE EXECUTOR - REAL-TIME MODE")
    print("=" * 80)
    
    # Configure for LIVE execution
    config = ExecutorConfig(
        mode=ExecutionMode.LIVE,
        min_profit_usd=5.0,  # Lower threshold for testing
        max_position_usd=10000,
        max_gas_gwei=150,
        slippage_tolerance_pct=2.0,  # Your 2% cap
        auto_execute=True  # AUTO-EXECUTE profitable trades
    )
    
    executor = LiveExecutor(config)
    
    print(f"\n✅ Configuration:")
    print(f"   Mode: LIVE (AUTO-EXECUTE)")
    print(f"   Min Profit: ${config.min_profit_usd}")
    print(f"   Max Position: ${config.max_position_usd:,}")
    print(f"   Slippage Cap: {config.slippage_tolerance_pct}%")
    print(f"   Private WSS: ENABLED (Alchemy)")
    
    print(f"\n🚀 Starting real-time monitoring...")
    print(f"   Scanning every new block (~2 seconds)")
    print(f"   Will AUTO-EXECUTE when profitable spread appears")
    print(f"\n   Press Ctrl+C to stop\n")
    
    # Warm discovery + arbitrage engine, then start executor stream
    await initialize_arbitrage_system()
    await executor.start_block_stream()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⏹️  Executor stopped by user")
