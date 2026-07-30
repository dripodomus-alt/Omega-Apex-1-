"""Validation helpers for merged V6 dynamic sizing paths."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from . import config
from .sizing import dynamic_size_optimizer


def validate_dynamic_optimizer(gross: Decimal = Decimal("12000")) -> dict[str, Any]:
    try:
        result = dynamic_size_optimizer(gross, hops=2)
        if isinstance(result, tuple):
            principal, profitability = result
            return {
                "best_principal": str(principal),
                "net_profit": str(getattr(profitability, "net_profit_usd", "0") if profitability else "0"),
                "passes": bool(getattr(profitability, "passes_gate", False)) if profitability else False,
                "bins_evaluated": len(getattr(config, "DYNAMIC_SIZE_OPT_BINS_USD", []) or []),
                "method": "tuple_compat",
                "ml_used": False,
                "config_bins": [str(item) for item in getattr(config, "DYNAMIC_SIZE_OPT_BINS_USD", [])],
            }
        return {
            "best_principal": str(getattr(result, "best_principal_usd", "0")),
            "net_profit": str(getattr(getattr(result, "best_profitability", None), "net_profit_usd", "0")),
            "passes": bool(getattr(getattr(result, "best_profitability", None), "passes_gate", False)),
            "bins_evaluated": len(getattr(result, "evaluated_sizes", []) or []),
            "method": str(getattr(result, "best_method", "object_compat")),
            "ml_used": bool(getattr(result, "ml_prediction_used", False)),
            "config_bins": [str(item) for item in getattr(config, "DYNAMIC_SIZE_OPT_BINS_USD", [])],
        }
    except Exception as exc:
        return {"passes": False, "error": f"{type(exc).__name__}:{exc}"}


def validate_imports_and_paths() -> list[str]:
    issues: list[str] = []
    for module_name in ("sizing", "flash_loan", "capital_allocator", "v6_integration"):
        try:
            __import__(f"omega_v5.{module_name}", fromlist=["*"])
        except Exception as exc:
            issues.append(f"import_error:{module_name}:{exc}")
    if not getattr(config, "DYNAMIC_SIZE_OPT_BINS_USD", []):
        issues.append("no_bins_configured")
    return issues

