"""
receipt_reconciler.py — Actual vs estimated profit from on-chain receipt.
"""

from decimal import Decimal
from typing import Dict, Any


def reconcile_receipt(
    staged: Dict[str, Any],
    receipt: Dict[str, Any],
    base_asset: str,
    base_price: Decimal,
) -> Dict[str, Any]:
    actual_surplus = int(receipt.get("net_base_surplus_raw", 0))
    estimated = staged.get("net_base_surplus_raw", 0)
    profit_usd = Decimal(actual_surplus) / Decimal(10**18) * base_price  # rough

    return {
        "actual_profit_usd": profit_usd,
        "estimated_profit_usd": staged.get("net_profit_usd"),
        "profit_retention_rate": float(profit_usd / Decimal(str(staged.get("net_profit_usd", 1)))) if staged.get("net_profit_usd") else 0,
        "reconciled": True,
    }
