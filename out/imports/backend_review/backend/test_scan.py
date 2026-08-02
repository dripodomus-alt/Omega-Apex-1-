#!/usr/bin/env python3
"""Quick test of the APEX_OMEGA execution pipeline"""

import os
import sys
sys.path.insert(0, '/app/backend')
os.chdir('/app/backend')

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path('/app/backend/.env'))

from engine import Web3PoolScanner, C1Aggressor, SlippageSentinel, TITAN_ENABLED

rpc_url = os.getenv('POLYGON_RPC_URL')

print('=== APEX_OMEGA LIVE EXECUTION TEST ===')
print(f'TITAN Engine: {"ACTIVE" if TITAN_ENABLED else "FALLBACK"}')
print()

scanner = Web3PoolScanner(rpc_url)
print(f'Web3: CONNECTED | Chain: {scanner.w3.eth.chain_id} | Block: {scanner.w3.eth.block_number}')
print()

sentinel = SlippageSentinel(tolerance=0.03)
aggressor = C1Aggressor(sentinel)

print('Scanning Polygon UniswapV3 pools...')
results = aggressor.scan_and_analyze(scanner)

validated = [r for r in results if r['status'] == 'VALIDATED']
rejected = [r for r in results if r['status'] == 'REJECTED']
insufficient = [r for r in results if r['status'] == 'INSUFFICIENT_YIELD']

print(f'Scanned: {len(results)} | VALIDATED: {len(validated)} | REJECTED: {len(rejected)} | LOW_YIELD: {len(insufficient)}')
print()

for r in results[:6]:
    status_icon = '🎯' if r['status'] == 'VALIDATED' else ('⚠️' if r['status'] == 'REJECTED' else '📊')
    if r['status'] == 'VALIDATED':
        profit_pct = r.get('profit_percentage', 0)
        net = r.get('predicted_profit', 0)
        ratio = r.get('profit_to_gas_ratio', 0)
        print(f"{status_icon} {r['pool']}: +{profit_pct:.4f}% | Net: ${net:.4f} | Ratio: {ratio:.1f}x")
    else:
        reason = r.get('reason', f"Profit: {r.get('profit_percentage', 0):.4f}%")
        print(f"{status_icon} {r['pool']}: {r['status']} | {reason}")
