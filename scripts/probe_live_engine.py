import os
import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'out' / 'imports' / 'backend_review' / 'backend'))

from coefficient_arbitrage_engine import get_coefficient_engine

eng = get_coefficient_engine()
print('initial_loading', eng.pools_loading)
for _ in range(20):
    if not eng.pools_loading:
        break
    time.sleep(1)
print('final_loading', eng.pools_loading)
print('pool_count', len(eng.pools))
print('sample', list(eng.pools.items())[:1] if eng.pools else [])
