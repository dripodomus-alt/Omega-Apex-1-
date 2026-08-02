#!/usr/bin/env python3
"""
Test script for fixed 1inch and DefiLlama APIs
"""

import asyncio
import sys
from defillama_discovery import get_defillama_discovery
from oneinch_discovery import get_oneinch_discovery

async def test_defillama():
    """Test DefiLlama API integration."""
    print("=" * 80)
    print("TESTING DEFILLAMA API")
    print("=" * 80)
    print()
    
    llama = get_defillama_discovery()
    
    try:
        # Test getting Polygon pools
        pools = await llama.get_polygon_pools(min_tvl=50000)
        
        if pools:
            print(f'✅ SUCCESS: Retrieved {len(pools)} Polygon pools with TVL >= $50k')
            print()
            print('Sample pool data:')
            for i, pool in enumerate(pools[:5], 1):
                print(f"\n{i}. {pool.get('project', 'Unknown')} - {pool.get('symbol', 'N/A')}")
                print(f"   Chain: {pool.get('chain', 'N/A')}")
                print(f"   TVL: ${pool.get('tvlUsd', 0):,.2f}")
                apy = pool.get('apy', 0) or 0
                print(f"   APY: {apy:.2f}%")
            
            return True
        else:
            print('❌ FAILED: No pools retrieved')
            return False
    
    except Exception as e:
        print(f'❌ ERROR: {str(e)}')
        import traceback
        traceback.print_exc()
        return False


async def test_1inch():
    """Test 1inch API integration."""
    print()
    print("=" * 80)
    print("TESTING 1INCH API")
    print("=" * 80)
    print()
    
    oneinch = get_oneinch_discovery()
    
    try:
        # Test liquidity sources discovery
        sources = await oneinch.discover_liquidity_sources()
        
        if sources:
            print(f'✅ SUCCESS: Retrieved {len(sources)} liquidity sources')
            print()
            print('Sample liquidity sources:')
            for i, (protocol_id, protocol_data) in enumerate(list(sources.items())[:10], 1):
                title = protocol_data.get('title', protocol_id)
                print(f"  {i}. {title} (ID: {protocol_id})")
            
            return True
        else:
            print('⚠️ WARNING: No liquidity sources retrieved (may be API key issue)')
            return False
    
    except Exception as e:
        print(f'❌ ERROR: {str(e)}')
        import traceback
        traceback.print_exc()
        return False


async def main():
    print("\n")
    print("🧪 API INTEGRATION TESTING")
    print()
    
    # Test DefiLlama (critical for TVL data)
    defillama_ok = await test_defillama()
    
    # Test 1inch (optional - for extended pool discovery)
    oneinch_ok = await test_1inch()
    
    print()
    print("=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"DefiLlama API: {'✅ WORKING' if defillama_ok else '❌ FAILED'}")
    print(f"1inch API: {'✅ WORKING' if oneinch_ok else '⚠️ NOT WORKING (check API key)'}")
    print()
    
    if defillama_ok:
        print("✅ PRIMARY OBJECTIVE ACHIEVED: DefiLlama TVL data is working!")
        print("   This is sufficient to fix the dust liquidity problem.")
    else:
        print("❌ CRITICAL: DefiLlama is not working. Cannot proceed with fixes.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
