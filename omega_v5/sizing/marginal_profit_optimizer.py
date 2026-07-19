"""
marginal_profit_optimizer.py — Stop when marginal net profit <= 0.
"""

from decimal import Decimal
from typing import Dict, Any, List


def optimize_marginal_profit(
    size_ladder: List[Decimal],
    net_profit_fn,  # callable(size) -> net_profit_usd
) -> Decimal:
    best = Decimal("0")
    for size in size_ladder:
        profit = net_profit_fn(size)
        if profit <= best * Decimal("0.98"):  # marginal non-positive
            break
        best = profit
    return best
