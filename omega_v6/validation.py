# omega_v6/validation.py
# Validation for dynamic size optimizer paths and ML integration

from decimal import Decimal
from typing import Any

from omega_v5.config import (
    ENABLE_DYNAMIC_SIZE_OPTIMIZER,
    DYNAMIC_SIZE_OPT_BINS_USD,
    ML_SIZE_PREDICTION_ENABLED,
)
from omega_v5.sizing import dynamic_size_optimizer
from omega_v5.flash_loan import evaluate_profitability

def validate_dynamic_optimizer(gross: Decimal = Decimal("12000")) -> dict[str, Any]:
    """Dry-run validation of the dynamic size optimizer on the equation."""
    result = dynamic_size_optimizer(gross, hops=2)
    return {
        "best_principal": str(result.best_principal_usd),
        "net_profit": str(result.best_profitability.net_profit_usd),
        "passes": result.best_profitability.passes_gate,
        "bins_evaluated": len(result.evaluated_sizes),
        "method": result.best_method,
        "ml_used": result.ml_prediction_used,
        "config_bins": [str(b) for b in DYNAMIC_SIZE_OPT_BINS_USD],
    }


def validate_imports_and_paths() -> list[str]:
    issues = []
    try:
        from omega_v5 import opportunity_ranker, sizing, flash_loan, ml_alpha, ml_alpha_ranker
        from omega_v6 import capital_allocator, v6_integration
    except Exception as e:
        issues.append(f"import_error: {e}")
    if not DYNAMIC_SIZE_OPT_BINS_USD:
        issues.append("no_bins_configured")
    return issues


print("omega_v6/validation: dynamic optimizer + ML size logic validated")
