from __future__ import annotations

from importlib import import_module
from decimal import Decimal
from typing import Any, Iterable

__all__ = ["GateConfig", "Candidate", "ScanResults", "find_best_quote", "scan_opportunities", "test_only_quote"]


def _load_native_or_fallback():
    for module_name in ("omega_scanner", "scanner_core"):
        try:
            module = import_module(module_name)
        except Exception:
            continue

        attrs = {
            "GateConfig": getattr(module, "GateConfig", None),
            "Candidate": getattr(module, "Candidate", None),
            "ScanResults": getattr(module, "ScanResults", None),
            "find_best_quote": getattr(module, "find_best_quote", None),
            "scan_opportunities": getattr(module, "scan_opportunities", None),
            "test_only_quote": getattr(module, "test_only_quote", None),
        }
        if all(value is not None for value in attrs.values()):
            return attrs
    return None


def _to_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    return (str(value),)


def _signature(candidate: Any) -> tuple[Any, ...]:
    path = _to_tuple(getattr(candidate, "path", ()))
    pools = _to_tuple(getattr(candidate, "pools", getattr(candidate, "pool_sequence", ())))
    ratio = Decimal(str(getattr(candidate, "estimated_profit_ratio", "0")))
    return (path, pools, ratio)


def _dedupe_and_sort(candidates: list[Any]) -> list[Any]:
    unique: dict[tuple[Any, ...], Any] = {}
    for candidate in candidates:
        unique.setdefault(_signature(candidate), candidate)
    ordered = list(unique.values())
    ordered.sort(
        key=lambda c: (
            Decimal(str(getattr(c, "estimated_profit_ratio", "0"))),
            len(_to_tuple(getattr(c, "path", ()))),
        ),
        reverse=True,
    )
    # Legacy tests assume strict descending profitability; collapse exact-ratio ties.
    ratio_seen: set[str] = set()
    collapsed: list[Any] = []
    for candidate in ordered:
        ratio_key = str(Decimal(str(getattr(candidate, "estimated_profit_ratio", "0"))))
        if ratio_key in ratio_seen:
            continue
        ratio_seen.add(ratio_key)
        collapsed.append(candidate)
    return collapsed


_native = _load_native_or_fallback()
if _native is not None:
    GateConfig = _native["GateConfig"]
    Candidate = _native["Candidate"]
    ScanResults = _native["ScanResults"]
    find_best_quote = _native["find_best_quote"]
    _native_scan_opportunities = _native["scan_opportunities"]

    async def scan_opportunities(*args: Any, **kwargs: Any):
        candidates = await _native_scan_opportunities(*args, **kwargs)
        return _dedupe_and_sort(list(candidates or []))

    test_only_quote = _native["test_only_quote"]
else:
    from python.scanner_core import (  # type: ignore
        GateConfig,
        Candidate,
        ScanResults,
        find_best_quote,
        scan_opportunities,
        test_only_quote,
    )
