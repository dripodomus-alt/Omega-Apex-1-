"""
submission_router.py — Private vs public based on value and risk.
"""

from decimal import Decimal
from typing import Dict, Any


def choose_submission_channel(route: Dict[str, Any]) -> str:
    profit = Decimal(str(route.get("net_profit_usd", 0)))
    if profit > Decimal("50"):
        return "private_relay"
    if profit > Decimal("15"):
        return "private_mempool"
    return "public_mempool"
