"""
flash_source_selector.py — Compare Aave vs Balancer (and future) by net retained profit + success history.
"""

from decimal import Decimal
from typing import Dict, Any, List
from ..flash_loan import FlashSource, compute_flash_params


def select_best_flash_source(
    base_asset: str,
    principal_usd: Decimal,
    route: Dict[str, Any],
    historical_success: Dict[str, float],
) -> FlashSource:
    """Pick source maximizing retained net profit and probability."""
    candidates = [FlashSource.BALANCER, FlashSource.AAVE]
    best = FlashSource.BALANCER
    best_score = Decimal("-1")

    for src in candidates:
        flash = compute_flash_params(principal_usd, src, base_asset)
        fee_penalty = flash.fee_usd
        success_prob = Decimal(str(historical_success.get(src.value, 0.85)))
        score = (principal_usd - fee_penalty) * success_prob
        if score > best_score:
            best_score = score
            best = src
    return best
