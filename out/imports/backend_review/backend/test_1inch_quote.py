#!/usr/bin/env python3
"""
Test 1inch quote response format
"""

import asyncio
from oneinch_discovery import get_oneinch_discovery

async def test_quote():
    oneinch = get_oneinch_discovery()
    
    # Test a quote
    print("Testing 1inch quote API...")
    print("=" * 80)
    
    quote = await oneinch.get_swap_quote(
        src_token="0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",  # WMATIC
        dst_token="0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",  # USDC
        amount="1000000000000000000"  # 1 WMATIC
    )
    
    if quote:
        print("✅ Quote received!")
        print("\nResponse keys:", list(quote.keys()))
        print("\nFull response:")
        import json
        print(json.dumps(quote, indent=2)[:2000])
    else:
        print("❌ No quote received")

asyncio.run(test_quote())
