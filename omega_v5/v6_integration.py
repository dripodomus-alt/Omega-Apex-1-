"""Safe V6 dynamic sizing integration for omega_v5 opportunities."""

from __future__ import annotations

from dataclasses import replace, is_dataclass
from typing import TYPE_CHECKING, Any

from . import config
from .flash_loan import FlashSource
if TYPE_CHECKING:
    from .opportunity_ranker import LiveOpportunity
from .sizing import optimize_route_principal


def _enabled(name: str, default: bool = False) -> bool:
    return bool(getattr(config, name, default))


def _ml_size_prediction(opportunities: list["LiveOpportunity" | Any]) -> list["LiveOpportunity" | Any]:
    try:
        from .opportunity_ranker import apply_ml_size_prediction
        return apply_ml_size_prediction(opportunities)
    except Exception:
        return opportunities


def integrate_dynamic_sizing(opportunities: list["LiveOpportunity" | Any], pools: dict) -> list["LiveOpportunity" | Any]:
    if not (_enabled("V6_ENABLED", False) and _enabled("ENABLE_DYNAMIC_SIZE_OPTIMIZER", True)):
        return opportunities

    updated: list["LiveOpportunity" | Any] = []
    for op in opportunities:
        try:
            sizing = optimize_route_principal(
                op.profitability.flashloan.principal_usd,
                list(op.pool_sequence),
                pools,
                path=list(op.path),
                flash_source=getattr(op, "flash_source", FlashSource.BALANCER),
            )
            metadata = dict(getattr(op, "metadata", {}) or {})
            metadata["v6_dynamic_sizing"] = {
                "selected_principal_usd": str(getattr(sizing, "selected_principal_usd", "")),
                "method": str(getattr(sizing, "method", "")),
            }
            updated.append(replace(op, metadata=metadata) if is_dataclass(op) else op)
        except Exception:
            updated.append(op)
    return _ml_size_prediction(updated)


def get_v6_status() -> dict[str, Any]:
    return {
        "v6_enabled": _enabled("V6_ENABLED", False),
        "dynamic_size_optimizer": _enabled("ENABLE_DYNAMIC_SIZE_OPTIMIZER", True),
        "capital_allocation": _enabled("V6_CAPITAL_ALLOCATION_ENABLED", False),
        "bin_sizing_active": True,
    }


