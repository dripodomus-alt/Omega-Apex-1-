# ==============================================================================
# state_machine.py  —  C1/C2 full execution state machine
# Extracted from Cell 9 of notebooks/omega_v5.ipynb
#
# C1 executes against the pre-trade pool state.
# After C1 confirms on-chain, pools mutate.
# C2 reloads the confirmed post-C1 state, independently recomputes
# profitability, and decides: MIRROR | REVERSE | DO_NOTHING.
# C2 is bounded to ~5 blocks (~10 seconds on Polygon).
#
# Lifecycle
# ---------
#   Opportunity detected
#     ↓
#   C1Cycle created  (PRE_CHECK → SIMULATING → SUBMITTED → CONFIRMED | FAILED)
#     ↓
#   C1 tx confirms → pools mutate
#     ↓
#   C2Cycle created from post-C1 snapshot
#   C2 recomputes route within 5-block window
#     ↓
#   C2Decision: MIRROR | REVERSE | DO_NOTHING
#     ↓
#   C2 submitted if MIRROR or REVERSE
# ==============================================================================

import time
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum, auto
from typing import Dict, List, Optional

from .math_engine import DeFiEngineMath
from .flash_loan import evaluate_profitability, FlashSource
from .oracle_layer import PriceUnavailable, token_price_usd
from . import rpc_layer
from .opportunity_ranker import LiveOpportunity, _quote_route_amount
from .rpc_layer import DEEP_POOL_REGISTRY, load_live_pool_state

BLOCKS_C2_WINDOW = 5    # maximum blocks C2 may act after C1 confirmation
BLOCK_TIME_S     = 2.0  # Polygon average block time in seconds


# ── Enums ─────────────────────────────────────────────────────────────────────

class OppStatus(Enum):
    DETECTED   = auto()
    EVALUATING = auto()
    GATE_PASS  = auto()
    GATE_FAIL  = auto()
    EXPIRED    = auto()


class C1Status(Enum):
    PRE_CHECK  = auto()
    SIMULATING = auto()
    SIM_FAIL   = auto()
    SUBMITTED  = auto()
    CONFIRMED  = auto()
    FAILED     = auto()
    REVERTED   = auto()


class C2Decision(Enum):
    PENDING    = auto()
    MIRROR     = auto()     # Same direction — spread persists post-C1
    REVERSE    = auto()     # Opposite direction — C1 moved price, new spread emerged
    DO_NOTHING = auto()     # No profitable edge within C2 window


class C2Status(Enum):
    PENDING    = auto()
    COMPUTING  = auto()
    SUBMITTED  = auto()
    CONFIRMED  = auto()
    FAILED     = auto()
    EXPIRED    = auto()


# ── Pool snapshot ─────────────────────────────────────────────────────────────

@dataclass
class PoolSnapshot:
    """Immutable point-in-time pool state captured at a specific block."""
    pool_id:   str
    protocol:  str
    tokens:    List[str]
    reserves:  List[Decimal]
    block:     int
    timestamp: float = field(default_factory=time.time)

    sqrt_price_x96: Optional[Decimal] = None
    liquidity:      Optional[Decimal] = None
    fee_bps:        Optional[int]     = None
    decimal_adjustment: Optional[Decimal] = None
    weights:        Optional[List[Decimal]] = None
    swap_fee:       Optional[Decimal] = None
    A:              Optional[Decimal] = None


def snapshot_pool(pool_id: str, pool: dict, block: int) -> PoolSnapshot:
    """Captures a PoolSnapshot from a live pool dict at the given block."""
    return PoolSnapshot(
        pool_id        = pool_id,
        protocol       = pool["protocol"],
        tokens         = list(pool["tokens"]),
        reserves       = list(pool.get("reserves", [])),
        block          = block,
        sqrt_price_x96 = pool.get("sqrtPriceX96"),
        liquidity      = pool.get("liquidity"),
        fee_bps        = pool.get("fee_bps"),
        decimal_adjustment = pool.get("decimal_adjustment"),
        weights        = pool.get("weights"),
        swap_fee       = pool.get("swap_fee"),
        A              = pool.get("A"),
    )


def snapshot_to_pool_dict(snap: PoolSnapshot) -> dict:
    """Reconstructs a pool dict from a snapshot for use with DeFiEngineMath."""
    d: dict = {"protocol": snap.protocol, "tokens": snap.tokens, "reserves": snap.reserves}
    if snap.protocol == "UniswapV2":
        d["fee"]        = snap.swap_fee or Decimal("0.003")
    elif snap.protocol in {"UniswapV3", "QuickSwapV3", "Algebra"}:
        d["sqrtPriceX96"] = snap.sqrt_price_x96
        d["liquidity"]    = snap.liquidity
        d["fee_bps"]      = snap.fee_bps
        d["decimal_adjustment"] = snap.decimal_adjustment or Decimal("1")
    elif snap.protocol == "Curve":
        d["A"]          = snap.A or Decimal("100")
    elif snap.protocol == "Balancer":
        d["weights"]    = snap.weights
        d["swap_fee"]   = snap.swap_fee or Decimal("0.0025")
    return d


# ── Helper: path-walk ─────────────────────────────────────────────────────────

def walk_path(path: List[str], pool_seq: List[str], pools: dict) -> Decimal:
    """Simulates the amount-out walk along a token path using given pool states."""
    amount = Decimal("10000")
    for hop_idx, pid in enumerate(pool_seq):
        pool = pools.get(pid)
        if not pool:
            return Decimal("0")
        t_in  = path[hop_idx]
        t_out = path[hop_idx + 1] if hop_idx + 1 < len(path) else path[0]
        tok   = pool.get("tokens", [])
        i     = tok.index(t_in)  if t_in  in tok else 0
        j     = tok.index(t_out) if t_out in tok else 1
        proto = pool["protocol"]
        if proto == "UniswapV2":
            amount = DeFiEngineMath.query_uniswap_v2(
                pool["reserves"][i], pool["reserves"][j], amount, pool["fee"])
        elif proto in {"UniswapV3", "QuickSwapV3", "Algebra"}:
            amount = DeFiEngineMath.query_uniswap_v3(
                pool["sqrtPriceX96"],
                pool["liquidity"],
                amount,
                i == 0,
                pool["fee_bps"],
                pool.get("decimal_adjustment", Decimal("1")),
            )
        elif proto == "Curve":
            ains    = [Decimal("0")] * len(pool["reserves"])
            ains[i] = amount
            amount  = DeFiEngineMath.query_curve_stable(pool["reserves"], ains, i, j, pool["A"])
        elif proto == "Balancer":
            amount = DeFiEngineMath.query_balancer_weighted(
                pool["reserves"], pool["weights"], amount, i, j, pool["swap_fee"])
        if amount <= 0:
            return Decimal("0")
    return amount


def _recreate_opportunity(
    original_opp: LiveOpportunity,
    pools: dict,
    path: list[str],
    pool_seq: list[str],
    principal_usd: Decimal,
) -> LiveOpportunity | None:
    """Re-evaluates and creates a new LiveOpportunity from a new market state."""
    from .opportunity_ranker import replace

    try:
        price = token_price_usd(path[0])
    except PriceUnavailable:
        return None
    if price <= 0 or principal_usd <= 0:
        return None

    amount_in = principal_usd / price
    amount_out = walk_path(path, pool_seq, pools) # Simplified quote for speed
    if amount_out <= 0:
        return None

    gross_out_usd = amount_out * price
    profitability = evaluate_profitability(
        gross_out_usd, principal_usd, len(path) - 1, original_opp.flash_source, path[0]
    )
    if not profitability.passes_gate:
        return None

    gross_rate = gross_out_usd / principal_usd if principal_usd > 0 else Decimal("0")
    return replace(original_opp, path=path, pool_sequence=pool_seq, gross_rate=gross_rate, gross_out_usd=gross_out_usd, profitability=profitability)


# ── C1 / C2 dataclasses ───────────────────────────────────────────────────────

@dataclass
class C1Cycle:
    c1_id:       str
    opportunity: "object"        # LiveOpportunity (avoids circular import at module level)
    status:      C1Status = C1Status.PRE_CHECK

    pre_snapshots:      Dict[str, PoolSnapshot] = field(default_factory=dict)
    tx_hash:            Optional[str]           = None
    block_confirmed:    Optional[int]           = None
    gas_used:           Optional[int]           = None
    actual_profit_usd:  Optional[Decimal]       = None
    created_at:         float                   = field(default_factory=time.time)

    def capture_pre_state(self, pools: dict, block: int):
        for pid in self.opportunity.pool_sequence:
            if pid in pools:
                self.pre_snapshots[pid] = snapshot_pool(pid, pools[pid], block)

    def mark_confirmed(
        self, tx_hash: str, block: int, gas_used: int, profit_usd: Decimal
    ):
        self.tx_hash           = tx_hash
        self.block_confirmed   = block
        self.gas_used          = gas_used
        self.actual_profit_usd = profit_usd
        self.status            = C1Status.CONFIRMED


@dataclass
class C2Cycle:
    c2_id:     str
    c1_cycle:  C1Cycle
    decision:  C2Decision = C2Decision.PENDING
    status:    C2Status   = C2Status.PENDING

    post_snapshots:         Dict[str, PoolSnapshot] = field(default_factory=dict)
    recomputed_opportunity: Optional[object]        = None
    mirror_payload:         Optional[dict]          = None
    reverse_payload:        Optional[dict]          = None
    tx_hash:                Optional[str]           = None
    block_confirmed:        Optional[int]           = None
    actual_profit_usd:      Optional[Decimal]       = None
    created_at:             float                   = field(default_factory=time.time)
    deadline_block:         int                     = 0

    def set_deadline(self):
        from .rpc_layer import BLOCK as _BLOCK
        self.deadline_block = (self.c1_cycle.block_confirmed or _BLOCK) + BLOCKS_C2_WINDOW

    def is_within_window(self, current_block: int) -> bool:
        return current_block <= self.deadline_block

    def capture_post_state(self, pools: dict, block: int):
        """Load fresh pool states after C1 has mutated on-chain reserves."""
        for pid in self.c1_cycle.opportunity.pool_sequence:
            if rpc_layer.RPC_LIVE:
                pool_meta = DEEP_POOL_REGISTRY.get(pid)
                if pool_meta:
                    fresh = load_live_pool_state(pid, pool_meta)
                    if fresh:
                        pools[pid] = fresh
            if pid in pools:
                self.post_snapshots[pid] = snapshot_pool(pid, pools[pid], block)

    def recompute(self, pools: dict, current_block: int) -> C2Decision:
        """
        Independently recomputes profitability using post-C1 pool state.
        Evaluates original direction (MIRROR) and reversed path (REVERSE).
        """
        self.status = C2Status.COMPUTING

        if not self.is_within_window(current_block):
            self.decision = C2Decision.DO_NOTHING
            self.status   = C2Status.EXPIRED
            return self.decision

        post_pool_dict = {
            pid: snapshot_to_pool_dict(snap)
            for pid, snap in self.post_snapshots.items()
        }

        original_opp = self.c1_cycle.opportunity
        principal_usd = original_opp.profitability.flashloan.principal_usd

        # ── MIRROR: same path, same direction ─────────────────────────────────
        mirror_opp = _recreate_opportunity(
            original_opp, post_pool_dict, original_opp.path, original_opp.pool_sequence, principal_usd
        )

        # ── REVERSE: flip the path ─────────────────────────────────────────────
        rev_path = list(reversed(original_opp.path))
        rev_pool_seq = list(reversed(original_opp.pool_sequence))
        reverse_opp = _recreate_opportunity(
            original_opp, post_pool_dict, rev_path, rev_pool_seq, principal_usd
        )

        best_decision = C2Decision.DO_NOTHING
        best_opp = None
        best_net = Decimal("0")

        mirror_net = getattr(getattr(mirror_opp, "profitability", None), "net_profit_usd", Decimal("-1"))
        reverse_net = getattr(getattr(reverse_opp, "profitability", None), "net_profit_usd", Decimal("-1"))

        if mirror_net > best_net:
            best_decision = C2Decision.MIRROR
            best_net = mirror_net
            best_opp = mirror_opp

        if reverse_net > best_net:
            best_decision = C2Decision.REVERSE
            best_opp = reverse_opp

        self.decision = best_decision
        self.recomputed_opportunity = best_opp
        if best_decision != C2Decision.DO_NOTHING:
            self.status = C2Status.PENDING
        return self.decision
