# omega_v6 package - dynamic size + capital
from .capital_allocator import allocate_capital_for_route
from .v6_integration import integrate_dynamic_sizing, get_v6_status
from .validation import validate_dynamic_optimizer, validate_imports_and_paths

__all__ = ["allocate_capital_for_route", "validate_dynamic_optimizer"]
print("omega_v6: dynamic size optimizer integration ready")
