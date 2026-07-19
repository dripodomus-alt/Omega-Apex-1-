"""
conflict_graph.py — Detect shared resources for concurrent staging.
"""

from typing import List, Dict, Any, Set


def build_conflict_graph(routes: List[Dict[str, Any]]) -> Dict[str, Set[str]]:
    """Simple conflict on pool or token overlap."""
    conflicts: Dict[str, Set[str]] = {}
    for i, r1 in enumerate(routes):
        sig1 = str(r1.get("pool_sequence", []))
        conflicts[sig1] = set()
        for j, r2 in enumerate(routes):
            if i == j:
                continue
            sig2 = str(r2.get("pool_sequence", []))
            shared = set(r1.get("pool_sequence", [])) & set(r2.get("pool_sequence", []))
            if shared:
                conflicts[sig1].add(sig2)
    return conflicts


def select_non_conflicting(routes: List[Dict[str, Any]], max_concurrent: int = 5) -> List[Dict[str, Any]]:
    """Greedy independent set."""
    selected = []
    used_pools: Set[str] = set()
    for r in sorted(routes, key=lambda x: x.get("net_profit_usd", 0), reverse=True):
        pools = set(r.get("pool_sequence", []))
        if not pools & used_pools:
            selected.append(r)
            used_pools.update(pools)
            if len(selected) >= max_concurrent:
                break
    return selected
