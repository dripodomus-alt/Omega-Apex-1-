# ==============================================================================
# __init__.py -- Omega V5 package exports
# ==============================================================================

from __future__ import annotations

from importlib import import_module
from typing import Any

_SUBMODULES = {
    "accounting",
    "adapter_registry",
    "amm_adapters",
    "arbitrage",
    "capital_injector",
    "config",
    "execution",
    "execution_truth",
    "flash_loan",
    "gas_oracle",
    "math_engine",
    "opportunity_ranker",
    "oracle_layer",
    "pool_quality",
    "precision_pricing",
    "ranker",
    "route_execution_stager",
    "rpc_layer",
    "sizing",
    "stable_strategies",
    "state_machine",
}

_EXPORTS = {
    "CapitalInjectionResult": ("capital_injector", "CapitalInjectionResult"),
    "compute_optimal_injection": ("capital_injector", "compute_optimal_injection"),
    "import_metadata_for_route": ("capital_injector", "import_metadata_for_route"),
    "prepare_sizing_for_rust": ("capital_injector", "prepare_sizing_for_rust"),
    "LiveOpportunity": ("opportunity_ranker", "LiveOpportunity"),
    "UNIFIED_ROUTE_SCHEMA_VERSION": ("payload_envelope", "UNIFIED_ROUTE_SCHEMA_VERSION"),
    "compute_all_pool_rates": ("ranker", "compute_all_pool_rates"),
    "detect_cross_pool_two_leg_spreads": ("ranker", "detect_cross_pool_two_leg_spreads"),
    "build_route_identity": ("route_execution_stager", "build_route_identity"),
    "freeze_staged_opportunity_id": ("route_execution_stager", "freeze_staged_opportunity_id"),
}


def __getattr__(name: str) -> Any:
    if name in _SUBMODULES:
        module = import_module(f".{name}", __name__)
        globals()[name] = module
        return module
    if name in _EXPORTS:
        module_name, attr_name = _EXPORTS[name]
        module = import_module(f".{module_name}", __name__)
        value = getattr(module, attr_name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = sorted(_SUBMODULES | set(_EXPORTS))