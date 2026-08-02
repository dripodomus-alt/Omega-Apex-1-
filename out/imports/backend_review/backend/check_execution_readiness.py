#!/usr/bin/env python3
"""
REAL EXECUTION READINESS CHECK
Validates that the system can actually execute profitable trades
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from eth_account import Account
from web3 import Web3
from executor_registry import get_configured_executor_wallet, get_rpc_url
from institutional_executor import C1_ADDRESS

load_dotenv(Path(__file__).parent / '.env')

rpc_url = get_rpc_url('polygon')
w3 = Web3(Web3.HTTPProvider(rpc_url))

print('=' * 80)
print('REAL EXECUTION CAPABILITY CHECK')
print('=' * 80)

# Check wallet
wallet = get_configured_executor_wallet(w3)
private_key = os.getenv('PRIVATE_KEY', '')

if (not wallet or wallet == '0x0000000000000000000000000000000000000000') and private_key:
    try:
        wallet = Account.from_key(private_key).address
    except Exception:
        wallet = None

balance_matic = 0.0
if wallet and w3.is_connected():
    try:
        balance_wei = w3.eth.get_balance(wallet)
        balance_matic = balance_wei / 1e18
    except Exception:
        balance_matic = 0.0

print(f'\n💼 WALLET: {wallet}')
print(f'   Balance: {balance_matic:.4f} MATIC (${balance_matic * 0.85:.2f} USD @ $0.85/MATIC)')

if not wallet:
    print('   ❌ CRITICAL: No executor wallet configured')
elif balance_matic < 0.1:
    print(f'   ❌ CRITICAL: Low balance (need ~1 MATIC for gas)')
    print(f'   ACTION REQUIRED: Deposit MATIC to execute trades')
elif balance_matic < 1:
    print(f'   ⚠️  CAUTION: Moderate balance (good for testing)')
else:
    print(f'   ✅ GOOD: Sufficient balance for execution')

# Check contract deployment
contracts = {
    'C1 Arbitrage': os.getenv('C1_CONTRACT_ADDRESS') or os.getenv('C1_ARB_EXECUTOR_ADDRESS') or C1_ADDRESS,
    'C2 Arbitrage': os.getenv('C2_CONTRACT_ADDRESS') or os.getenv('C2_ARB_EXECUTOR_ADDRESS'),
    'Liquidation': os.getenv('LIQUIDATION_EXECUTOR_ADDRESS'),
}

print(f'\n📜 SMART CONTRACTS:')
deployed_count = 0
for name, addr in contracts.items():
    if addr and addr != '0x0000000000000000000000000000000000000000':
        try:
            code = w3.eth.get_code(addr)
            if len(code) > 2:
                print(f'   ✅ {name}: {addr} (DEPLOYED)')
                deployed_count += 1
            else:
                print(f'   ❌ {name}: {addr} (NOT DEPLOYED)')
        except Exception as e:
            print(f'   ❌ {name}: {addr} (RPC ERROR: {e})')
    else:
        print(f'   ❌ {name}: NOT CONFIGURED')

print(f'\n🔗 RPC CONNECTION:')
if w3.is_connected():
    print(f'   URL: {rpc_url}')
    print(f'   Block: {w3.eth.block_number:,}')
    print(f'   Gas Price: {w3.eth.gas_price / 1e9:.2f} Gwei')
    print(f'   Connected: ✅')
else:
    print(f'   URL: {rpc_url or "NOT_CONFIGURED"}')
    print(f'   Connected: ❌')

# CRITICAL PATH ASSESSMENT
print(f'\n' + '=' * 80)
print('CRITICAL PATH TO REAL PROFIT:')
print('=' * 80)

issues = []
if not w3.is_connected():
    issues.append('❌ RPC not connected')
if not wallet:
    issues.append('❌ Executor wallet is not configured')
elif balance_matic < 0.1:
    issues.append('❌ Insufficient wallet balance for gas')
if deployed_count == 0:
    issues.append('❌ No smart contracts deployed')
    
if issues:
    print('\n⚠️  BLOCKERS PREVENTING REAL EXECUTION:')
    for issue in issues:
        print(f'   {issue}')
    print('\n💡 NEXT STEPS:')
    if not w3.is_connected():
        print('   1. Configure POLYGON_RPC_URL (or ALCHEMY_HTTP_1 / PRIVATE_RPC_URL)')
    if not wallet:
        print('   2. Set EXECUTOR_WALLET or PRIVATE_KEY in backend/.env')
    elif balance_matic < 0.1:
        print(f'   1. Deposit at least 1 MATIC to {wallet}')
    if deployed_count == 0:
        print(f'   3. Deploy arbitrage smart contracts to Polygon mainnet')
else:
    print('\n✅ SYSTEM READY FOR EXECUTION')
    print('   All prerequisites met - can execute trades when profitable spreads appear')
