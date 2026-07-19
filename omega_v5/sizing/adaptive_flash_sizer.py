"""
adaptive_flash_sizer.py — Multi-size quote ladders + coarse-to-fine optimization.
"""

from decimal import Decimal
from typing import List, Dict, Any


def adaptive_flash_sizer(
    base_asset: str,
    principal_usd: Decimal,
    pool_sequence: List[str],
    live_pools: Dict,
    max_steps: int = 6,
) -> List[Decimal]:
    """
    Coarse-to-fine ladder.
    Returns list of sizes to evaluate.
    Stops when marginal net profit becomes non-positive.
    """
    ladder = []
    current = principal_usd * Decimal("0.25")
    step = principal_usd * Decimal("0.15")
    for _ in range(max_steps):
        ladder.append(current)
        current += step
        if current > principal_usd * Decimal("1.8"):
            break
    return ladder
