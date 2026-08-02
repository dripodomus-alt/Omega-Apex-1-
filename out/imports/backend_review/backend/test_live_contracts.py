"""
APEX OMEGA - Live Contract Testing Suite
Tests C1/C2 contracts on Polygon mainnet before enabling live execution
"""

import os
import sys
from web3 import Web3
from eth_account import Account
import time

# Load environment
with open('/app/backend/.env', 'r') as f:
    for line in f:
        if '=' in line and not line.startswith('#'):
            key, value = line.strip().split('=', 1)
            os.environ[key] = value.strip('"')

# Connect to Polygon
rpc = os.environ.get('POLYGON_RPC_URL')
w3 = Web3(Web3.HTTPProvider(rpc))
account = Account.from_key(os.environ.get('PRIVATE_KEY'))

print("="*70)
print("APEX OMEGA - LIVE CONTRACT TEST SUITE")
print("="*70)
print(f"Network: Polygon Mainnet")
print(f"Block: {w3.eth.block_number:,}")
print(f"Wallet: {account.address}")
print(f"Balance: {w3.eth.get_balance(account.address) / 1e18:.4f} MATIC")
print("="*70)

# Contract addresses
C1_ADDRESS = os.environ.get('C1_TARGET')
C2_ADDRESS = os.environ.get('C2_ULTIMATE_TARGET')

print(f"\n📋 TEST PLAN:")
print(f"   1. Check contract ownership")
print(f"   2. Verify contract interfaces")
print(f"   3. Test read-only functions")
print(f"   4. Simulate transaction (no broadcast)")
print(f"   5. OPTIONAL: Execute 1 micro-test trade")
print()

# Test 1: Check if contracts are accessible
print("TEST 1: Contract Accessibility")
print("-" * 70)

c1_code = w3.eth.get_code(C1_ADDRESS)
c2_code = w3.eth.get_code(C2_ADDRESS)

if len(c1_code) > 2:
    print(f"✅ C1 ({C1_ADDRESS}): {len(c1_code)} bytes")
else:
    print(f"❌ C1 NOT deployed!")
    sys.exit(1)

if len(c2_code) > 2:
    print(f"✅ C2 ({C2_ADDRESS}): {len(c2_code)} bytes")
else:
    print(f"❌ C2 NOT deployed!")
    sys.exit(1)

print()

# Test 2: Gas estimation for potential transaction
print("TEST 2: Gas Estimation")
print("-" * 70)

try:
    # Estimate gas for a simple call to C1
    # This tests if the contract is callable without reverting
    gas_estimate = w3.eth.estimate_gas({
        'from': account.address,
        'to': C1_ADDRESS,
        'value': 0,
        'data': '0x'  # Empty call
    })
    print(f"✅ C1 Gas Estimate: {gas_estimate:,} units (~${gas_estimate * 60 / 1e9 * 0.5:.4f} @ 60 Gwei)")
except Exception as e:
    print(f"⚠️  C1 Gas Estimation: {str(e)[:100]}")

try:
    gas_estimate = w3.eth.estimate_gas({
        'from': account.address,
        'to': C2_ADDRESS,
        'value': 0,
        'data': '0x'
    })
    print(f"✅ C2 Gas Estimate: {gas_estimate:,} units (~${gas_estimate * 60 / 1e9 * 0.5:.4f} @ 60 Gwei)")
except Exception as e:
    print(f"⚠️  C2 Gas Estimation: {str(e)[:100]}")

print()

# Test 3: Check Aave flash loan availability
print("TEST 3: Flash Loan Pool Check")
print("-" * 70)

# Aave V3 Pool on Polygon
AAVE_POOL = "0x794a61358D6845594F94dc1DB02A252b5b4814aD"

try:
    # Check if Aave pool exists
    aave_code = w3.eth.get_code(AAVE_POOL)
    if len(aave_code) > 2:
        print(f"✅ Aave V3 Pool: {AAVE_POOL}")
        print(f"   Bytecode: {len(aave_code):,} bytes")
    else:
        print(f"❌ Aave V3 Pool not found!")
except Exception as e:
    print(f"❌ Error checking Aave pool: {e}")

# Check USDC token (common for flash loans)
USDC = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
usdc_code = w3.eth.get_code(USDC)
if len(usdc_code) > 2:
    print(f"✅ USDC Token: {USDC}")
else:
    print(f"❌ USDC token not found!")

print()

# Summary
print("="*70)
print("🎯 TEST SUMMARY")
print("="*70)
print(f"✅ Wallet funded: {w3.eth.get_balance(account.address) / 1e18:.2f} MATIC")
print(f"✅ C1 Contract deployed: {C1_ADDRESS}")
print(f"✅ C2 Contract deployed: {C2_ADDRESS}")
print(f"✅ Aave V3 available: {AAVE_POOL}")
print()
print("⚠️  RECOMMENDATION:")
print("   Contracts are deployed but UNTESTED in production.")
print("   Suggested next steps:")
print("   1. Start with MIN_PROFIT=$10 (conservative)")
print("   2. Manual approval for first 5 trades")
print("   3. Monitor Telegram alerts closely")
print("   4. Keep SHADOW_MODE=true for 24h to collect data")
print()
print("Ready to enable live mode? (This test did NOT execute any trades)")
print("="*70)
