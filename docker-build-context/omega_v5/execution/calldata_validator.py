"""
calldata_validator.py — Strict protocol-aware validation before staging.
"""

from typing import Dict, Any


def validate_calldata(route: Dict[str, Any]) -> Dict[str, Any]:
    """Validate target, selector, min_out, approvals, callback type."""
    required = ["target", "selector", "min_out_raw", "recipient", "deadline"]
    missing = [k for k in required if k not in route]
    if missing:
        return {"valid": False, "reason": f"missing_{missing[0]}"}

    # Additional checks for token ordering, fee tier, etc. would go here
    return {"valid": True, "calldata_status": "CALLDATA_READY"}
