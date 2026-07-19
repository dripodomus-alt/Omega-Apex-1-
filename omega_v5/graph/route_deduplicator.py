"""
route_deduplicator.py — Canonical route signatures to avoid wasting simulation budget.
"""

from typing import List, Dict, Any, Tuple


def route_signature(route: Dict[str, Any]) -> Tuple:
    """Canonical signature: (path, pool_sequence, principal_bucket)"""
    path = tuple(route.get("path", []))
    pools = tuple(route.get("pool_sequence", []))
    principal = str(route.get("flash_principal_usd", "0"))[:6]  # coarse bucket
    return (path, pools, principal)


def deduplicate_routes(routes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    unique = []
    for r in routes:
        sig = route_signature(r)
        if sig not in seen:
            seen.add(sig)
            unique.append(r)
    return unique
