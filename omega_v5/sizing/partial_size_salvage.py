"""
partial_size_salvage.py — When oversized route fails, reduce size and retry.
"""

from decimal import Decimal
from typing import Dict, Any, Callable


def partial_size_salvage(
    original_size: Decimal,
    simulate_fn: Callable[[Decimal], Dict[str, Any]],
    min_profit: Decimal,
) -> Dict[str, Any]:
    """Try 80%, 60%, 40% of original until profitable or exhausted."""
    for factor in [Decimal("0.8"), Decimal("0.6"), Decimal("0.4"), Decimal("0.25")]:
        candidate = original_size * factor
        result = simulate_fn(candidate)
        if result.get("net_profit_usd", Decimal("0")) >= min_profit:
            result["salvaged"] = True
            result["salvage_factor"] = factor
            return result
    return {"valid": False, "reason": "no_salvage_size_profitable"}
