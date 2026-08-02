"""omega_v5 package with merged V6 dynamic sizing compatibility exports."""

try:
    from .capital_allocator import allocate_capital_for_route
    from .v6_integration import get_v6_status, integrate_dynamic_sizing
    from .validation import validate_dynamic_optimizer, validate_imports_and_paths
except Exception:  # pragma: no cover - package import must remain fail-closed for optional V6 layer
    allocate_capital_for_route = None
    get_v6_status = None
    integrate_dynamic_sizing = None
    validate_dynamic_optimizer = None
    validate_imports_and_paths = None

__all__ = [
    "allocate_capital_for_route",
    "integrate_dynamic_sizing",
    "get_v6_status",
    "validate_dynamic_optimizer",
    "validate_imports_and_paths",
]
