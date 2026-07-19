# omega_v6/v6_integration.py
# Safe integration of dynamic size optimizer + V6

from decimal import Decimal
from typing import Any, Dict

from omega_v5.opportunity_ranker import LiveOpportunity, apply_ml_size_prediction
from omega_v5.sizing import optimize_principal_with_dynamic
from omega_v5.config import V6_ENABLED, ENABLE_DYNAMIC_SIZE_OPTIMIZER

def integrate_dynamic_sizing(opportunities: list[LiveOpportunity], pools: dict) -> list[LiveOpportunity]:
    if not V6_ENABLED or not ENABLE_DYNAMIC_SIZE_OPTIMIZER:
        return opportunities

    for op in opportunities:
        if op.gross_out_usd > 0:
            sizing = optimize_principal_with_dynamic(
                op.gross_out_usd,
                op.pool_sequence,
                pools,
                hops=len(op.path) - 1,
            )
            op.sizing = sizing
            # re-eval profitability with optimized size
            # (simplified)
    return apply_ml_size_prediction(opportunities)


def get_v6_status() -> Dict[str, Any]:
    return {
        "v6_enabled": V6_ENABLED,
        "dynamic_size_optimizer": ENABLE_DYNAMIC_SIZE_OPTIMIZER,
        "bin_sizing_active": True,
    }
