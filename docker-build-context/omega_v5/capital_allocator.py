"""V6 capital allocation compatibility layer for omega_v5."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from . import config
from .adapter_registry import resolve_capital_source_adapter
from .flash_loan import FlashSource
from .sizing import RouteSizing, optimize_route_principal


def _enabled(name: str, default: bool = False) -> bool:
    return bool(getattr(config, name, default))


def allocate_capital_for_route(
    gross_usd: Decimal,
    pool_sequence: list[str],
    pools: dict,
    hops: int = 2,
    asset: str = "USDC",
) -> dict[str, Any]:
    if not _enabled("V6_CAPITAL_ALLOCATION_ENABLED", False):
        return {"source": FlashSource.BALANCER.value, "principal_usd": str(gross_usd), "method": "v6_disabled"}

    try:
        sizing: RouteSizing = optimize_route_principal(
            Decimal(str(gross_usd)),
            pool_sequence,
            pools,
            path=[asset] + ["MID"] * max(0, hops - 1) + [asset] if hops >= 2 else [asset],
            flash_source=FlashSource.BALANCER,
        )
    except Exception:
        sizing = RouteSizing(selected_principal_usd=Decimal(str(gross_usd)), method="v6_sizing_fallback")

    best_source = FlashSource.BALANCER
    adapter_ok = False
    for source in (FlashSource.BALANCER, FlashSource.AAVE):
        try:
            resolution = resolve_capital_source_adapter(source)
            if getattr(resolution, "ok", False) and getattr(resolution, "executable", False):
                best_source = source
                adapter_ok = True
                break
        except Exception:
            continue

    return {
        "source": best_source.value,
        "principal_usd": str(getattr(sizing, "selected_principal_usd", gross_usd)),
        "net_profit_usd": str(getattr(sizing, "max_profit_usd", Decimal("0"))),
        "method": str(getattr(sizing, "method", "unknown")),
        "adapter_ok": adapter_ok,
        "bin_sizing": _enabled("ENABLE_DYNAMIC_SIZE_OPTIMIZER", True),
    }
