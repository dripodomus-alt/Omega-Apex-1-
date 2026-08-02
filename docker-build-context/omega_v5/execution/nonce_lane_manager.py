"""
nonce_lane_manager.py — Multiple nonce lanes to avoid contention.
"""

from typing import Dict, Any


class NonceLaneManager:
    def __init__(self, lanes: int = 3):
        self.lanes = {i: 0 for i in range(lanes)}

    def reserve_nonce(self, route: Dict[str, Any]) -> bool:
        # Simple round-robin for demo; real impl tracks on-chain nonce
        for lane, nonce in self.lanes.items():
            if nonce < 100:  # safety
                self.lanes[lane] += 1
                route["nonce_lane"] = lane
                route["nonce"] = nonce
                return True
        return False
