#!/usr/bin/env python3
# ==============================================================================
# cycle_shape.py -- canonical flash multi-mid cycle shape
#
# User desire (canonical executable shape):
#
#   FLASHLOAN_ASSET
#       -> BUY any mid-token on any invariant/protocol/pool
#       -> (optional) hop any further mid-token on any invariant
#       -> SELL back into FLASHLOAN_ASSET on any invariant
#       -> repay flash + keep SURPLUS
#
# Closed path form:
#   [flash, mid_1, mid_2, ..., mid_k, flash]
#
# Special cases:
#   k=1  -> two-leg   FLASH -> MID -> FLASH     (CROSS_POOL / PEGGED_STABLE)
#   k=2  -> triangle  FLASH -> M1 -> M2 -> FLASH
#   k=3  -> 4-hop     FLASH -> M1 -> M2 -> M3 -> FLASH
#   k>=1 -> general Bellman-Ford / fixed-hop multi-mid cycles
#
# Any hop may use any supported invariant:
#   constant_product | concentrated_liquidity | algebra_clmm |
#   stable_swap | weighted_invariant
# ==============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable, Optional

from .config import (
    PROTOCOL_REGISTRY,
    FULLY_EXECUTABLE_PROTOCOLS,
    normalize_protocol,
)


# Protocols / invariants allowed on any hop of the expanded cycle.
# Now sourced from canonical registry. Only canonical keys allowed.
ANY_INVARIANT_PROTOCOLS: frozenset[str] = frozenset(
    k for k, v in PROTOCOL_REGISTRY.items()
)

PROTOCOL_TO_INVARIANT: dict[str, str] = {
    "V2_CPMM": "constant_product",
    "V3_CLMM": "concentrated_liquidity",
    "QS_V2_CPMM": "constant_product",
    "QS_V3_ALGEBRA": "algebra_concentrated_liquidity",
    "BAL_WEIGHTED": "weighted_invariant",
    "CURVE_STABLE": "stable_swap",
    "AAVE_V3": "lending",
    "ROUTE_AGGREGATOR": "aggregator",
}

# Strategies that are closed flash cycles (path[0] == path[-1] == flash asset).
FLASH_CYCLE_STRATEGIES: frozenset[str] = frozenset({
    "BELLMAN_CYCLE",
    "BELLMAN_FORD",
    "THREE_LEG_TRIANGLE",
    "FOUR_LEG_CYCLE",
    "FLASH_MULTI_MID_CYCLE",
    "CROSS_POOL_TWO_LEG",
    "PEGGED_STABLE_TWO_LEG",
    "GENERIC",
})


@dataclass(frozen=True)
class CycleHop:
    """One hop: token_in -> token_out on a concrete pool/invariant."""

    hop_index: int
    token_in: str
    token_out: str
    pool_id: str
    protocol: str  # MUST be canonical internal key
    invariant: str
    liquidity_key: str = ""
    role: str = "MID_HOP"  # FLASH_BUY_MID | MID_TO_MID | MID_SELL_FLASH
    rate: Decimal = Decimal("0")

    def as_metadata(self) -> dict[str, Any]:
        return {
            "hop_index": self.hop_index,
            "token_in": self.token_in,
            "token_out": self.token_out,
            "pool_id": self.pool_id,
            "protocol": self.protocol,
            "invariant": self.invariant,
            "liquidity_key": self.liquidity_key,
            "role": self.role,
            "rate": str(self.rate),
            "any_invariant_allowed": True,
        }


@dataclass
class FlashCycleShape:
    """
    Fully expanded canonical cycle:

        flash_asset
          -> buy mid_tokens[0]   (hops[0], any invariant)
          -> ... mid hops ...
          -> sell to flash_asset (hops[-1], any invariant)
          -> surplus after repay
    """

    flash_asset: str
    mid_tokens: list[str]
    path: list[str]
    hops: list[CycleHop]
    pool_sequence: list[str] = field(default_factory=list)
    protocol_seq: list[str] = field(default_factory=list)  # canonical keys only
    invariants: list[str] = field(default_factory=list)
    hop_count: int = 0
    shape_id: str = ""
    shape_formula: str = (
        "FLASHLOAN_ASSET -> BUY_ANY_MID(ANY_INVARIANT) "
        "[-> ANY_MID(ANY_INVARIANT)]* -> SELL_TO_FLASH(ANY_INVARIANT) -> SURPLUS"
    )
    is_closed: bool = True
    allows_any_mid: bool = True
    allows_any_invariant: bool = True

    def __post_init__(self) -> None:
        if not self.hop_count:
            self.hop_count = len(self.hops) or max(0, len(self.path) - 1)
        if not self.pool_sequence and self.hops:
            self.pool_sequence = [h.pool_id for h in self.hops]
        if not self.protocol_seq and self.hops:
            self.protocol_seq = [h.protocol for h in self.hops]
        if not self.invariants and self.hops:
            self.invariants = [h.invariant for h in self.hops]
        if not self.shape_id:
            self.shape_id = describe_cycle_shape(self.flash_asset, self.mid_tokens)

    def as_metadata(self) -> dict[str, Any]:
        return {
            "schema": "omega_v5.flash_cycle_shape.v1",
            "shape_formula": self.shape_formula,
            "shape_id": self.shape_id,
            "flash_asset": self.flash_asset,
            "mid_tokens": list(self.mid_tokens),
            "mid_count": len(self.mid_tokens),
            "path": list(self.path),
            "hop_count": self.hop_count,
            "pool_sequence": list(self.pool_sequence),
            "protocol_seq": list(self.protocol_seq),  # canonical keys
            "invariants": list(self.invariants),
            "hops": [h.as_metadata() for h in self.hops],
            "is_closed": self.is_closed,
            "allows_any_mid": self.allows_any_mid,
            "allows_any_invariant": self.allows_any_invariant,
            "supported_protocols": sorted(ANY_INVARIANT_PROTOCOLS),
            "surplus_definition": (
                "surplus_base = final_flash_out - flash_principal_base; "
                "net_surplus_usd = surplus_usd - flash_fee - gas - relay - risk_buffer"
            ),
        }


def describe_cycle_shape(flash_asset: str, mid_tokens: Iterable[str]) -> str:
    mids = list(mid_tokens)
    if not mids:
        return f"{flash_asset}->(no-mid)->{flash_asset}"
    body = "->".join(mids)
    return f"{flash_asset}->{body}->{flash_asset}"


def hop_role(hop_index: int, hop_count: int) -> str:
    if hop_count <= 0:
        return "UNKNOWN"
    if hop_index == 0:
        return "FLASH_BUY_MID"
    if hop_index == hop_count - 1:
        return "MID_SELL_FLASH"
    return "MID_TO_MID"


def invariant_for_protocol(protocol: str, explicit: str = "") -> str:
    if explicit:
        return explicit
    canon = normalize_protocol(protocol) if protocol else protocol
    return PROTOCOL_TO_INVARIANT.get(canon, canon or "unknown")


def expand_cycle_shape(
    path: list[str],
    pool_sequence: list[str] | None = None,
    protocol_seq: list[str] | None = None,
    quote_entries: list[dict] | None = None,
    edges: list[dict] | None = None,
) -> FlashCycleShape:
    """
    Expand any closed token path into the canonical flash multi-mid shape.

    Requires path[0] == path[-1] (flash asset in and out).
    Mid-tokens are path[1:-1] — any discoverable/executable assets.
    Each hop may bind any supported protocol/invariant.
    protocol_seq must end up as canonical keys.
    """
    if len(path) < 3:
        raise ValueError("cycle path needs at least flash->mid->flash (len>=3)")
    if path[0] != path[-1]:
        raise ValueError(
            f"cycle must be closed on flash asset: start={path[0]} end={path[-1]}"
        )

    flash = path[0]
    mids = list(path[1:-1])
    hop_count = len(path) - 1
    pools = list(pool_sequence or [])
    protos = list(protocol_seq or [])
    entries = list(quote_entries or edges or [])

    hops: list[CycleHop] = []
    for i in range(hop_count):
        t_in = path[i]
        t_out = path[i + 1]
        entry = entries[i] if i < len(entries) and entries[i] else {}
        pool_id = str(
            (pools[i] if i < len(pools) else "")
            or entry.get("pool_id", "")
        )
        raw_proto = str(
            (protos[i] if i < len(protos) else "")
            or entry.get("protocol", "")
        )
        protocol = normalize_protocol(raw_proto) if raw_proto else ""
        inv = invariant_for_protocol(protocol, str(entry.get("invariant", "")))
        liq = str(entry.get("liquidity_key", pool_id))
        try:
            rate = Decimal(str(entry.get("rate", "0") or "0"))
        except Exception:
            rate = Decimal("0")
        hops.append(CycleHop(
            hop_index=i,
            token_in=t_in,
            token_out=t_out,
            pool_id=pool_id,
            protocol=protocol,  # canonical
            invariant=inv,
            liquidity_key=liq,
            role=hop_role(i, hop_count),
            rate=rate,
        ))

    return FlashCycleShape(
        flash_asset=flash,
        mid_tokens=mids,
        path=list(path),
        hops=hops,
        pool_sequence=[h.pool_id for h in hops],
        protocol_seq=[h.protocol for h in hops],  # canonical keys
        invariants=[h.invariant for h in hops],
        hop_count=hop_count,
    )


def rotate_cycle_to_flash_asset(path: list[str], preferred_flash: str | None = None) -> list[str]:
    """
    Rotate a closed cycle so it starts/ends on preferred flash asset when present.
    Preference order: preferred_flash, then USDC.e/USDC/USDT/DAI/WETH/WPOL.
    """
    if len(path) < 3 or path[0] != path[-1]:
        return list(path)
    core = path[:-1]
    n = len(core)
    if n == 0:
        return list(path)

    preference = []
    if preferred_flash:
        preference.append(preferred_flash)
    preference.extend(["USDC.e", "USDC", "USDT", "DAI", "WETH", "WPOL", "WBTC"])

    start_idx = 0
    for cand in preference:
        if cand in core:
            start_idx = core.index(cand)
            break

    rotated = core[start_idx:] + core[:start_idx]
    return rotated + [rotated[0]]


def cycle_shape_metadata(shape: FlashCycleShape) -> dict[str, Any]:
    return shape.as_metadata()


def normalized_cycle_surplus(
    *,
    flash_asset: str,
    mid_tokens: list[str],
    flash_principal_usd: Decimal,
    flash_principal_base: Decimal,
    final_flash_out_base: Decimal,
    flash_token_usd: Decimal,
    profitability: Any,
    hop_amounts: list[dict[str, Any]] | None = None,
    shape: FlashCycleShape | None = None,
) -> dict[str, Any]:
    """
    Surplus equation for the expanded cycle:

      gross_out_usd   = final_flash_out_base * flash_usd
      raw_delta_usd   = gross_out_usd - principal_usd
      net_surplus_usd = raw_delta_usd - flash_fee - gas - relay - risk_buffer

    Executable when final_flash_out covers principal + fees + min profit (in base).
    """
    gross_out_usd = final_flash_out_base * flash_token_usd if flash_token_usd > 0 else Decimal("0")
    raw_delta_usd = gross_out_usd - flash_principal_usd
    fee_usd = getattr(getattr(profitability, "flashloan", None), "fee_usd", Decimal("0")) or Decimal("0")
    gas_usd = getattr(profitability, "gas_cost_usd", Decimal("0")) or Decimal("0")
    relay_usd = getattr(profitability, "relay_tip_usd", Decimal("0")) or Decimal("0")
    risk_usd = getattr(profitability, "risk_buffer_usd", Decimal("0")) or Decimal("0")
    net_surplus_usd = raw_delta_usd - fee_usd - gas_usd - relay_usd - risk_usd
    surplus_base = final_flash_out_base - flash_principal_base

    return {
        "schema": "omega_v5.cycle_surplus.v1",
        "shape_formula": (
            "FLASHLOAN_ASSET -> BUY_ANY_MID(ANY_INVARIANT) "
            "[-> ANY_MID(ANY_INVARIANT)]* -> SELL_TO_FLASH(ANY_INVARIANT) -> SURPLUS"
        ),
        "flash_asset": flash_asset,
        "mid_tokens": list(mid_tokens),
        "shape_id": shape.shape_id if shape else describe_cycle_shape(flash_asset, mid_tokens),
        "principal": {
            "usd": str(flash_principal_usd),
            "base": str(flash_principal_base),
            "token_usd": str(flash_token_usd),
        },
        "output": {
            "final_flash_out_base": str(final_flash_out_base),
            "gross_out_usd": str(gross_out_usd),
        },
        "surplus": {
            "surplus_base": str(surplus_base),
            "raw_delta_usd": str(raw_delta_usd),
            "flash_fee_usd": str(fee_usd),
            "gas_cost_usd": str(gas_usd),
            "relay_tip_usd": str(relay_usd),
            "risk_buffer_usd": str(risk_usd),
            "net_surplus_usd": str(net_surplus_usd),
            "formula": (
                "net_surplus_usd = (final_flash_out_base * flash_usd) - principal_usd "
                "- flash_fee - gas - relay - risk_buffer"
            ),
        },
        "hop_amounts": hop_amounts or [],
        "passes_positive_surplus": net_surplus_usd > 0,
        "cycle_shape": shape.as_metadata() if shape else None,
    }


def tag_cycle_dict(cycle: dict, preferred_flash: str | None = None) -> dict:
    """
    Attach expanded flash-cycle shape fields onto a detector cycle dict.
    Rotates path onto a flash-friendly asset when possible.
    All protocol values normalized to canonical keys.
    """
    path = list(cycle.get("path") or [])
    if len(path) >= 3 and path[0] == path[-1]:
        path = rotate_cycle_to_flash_asset(path, preferred_flash)

    edges = list(cycle.get("edges") or [])
    # Rotate edges to match rotated path when lengths align.
    if edges and len(edges) == len(path) - 1 and path != list(cycle.get("path") or []):
        original = list(cycle.get("path") or [])[:-1]
        if path[0] in original:
            shift = original.index(path[0])
            edges = edges[shift:] + edges[:shift]
            for i, edge in enumerate(edges):
                if not edge:
                    continue
                edge = dict(edge)
                edge["token_in"] = path[i]
                edge["token_out"] = path[i + 1]
                edges[i] = edge

    pools = [str((e or {}).get("pool_id", "")) for e in edges]
    raw_protos = [str((e or {}).get("protocol", "")) for e in edges]
    protos = []
    for p in raw_protos:
        try:
            protos.append(normalize_protocol(p) if p else "")
        except Exception:
            protos.append(p)  # will fail later in validation if bad

    try:
        shape = expand_cycle_shape(path, pools, protos, edges=edges)
        shape_meta = shape.as_metadata()
    except Exception as exc:
        shape_meta = {"error": str(exc), "path": path}

    out = dict(cycle)
    out["path"] = path
    out["edges"] = edges
    out["flash_asset"] = path[0] if path else ""
    out["mid_tokens"] = path[1:-1] if len(path) >= 3 else []
    out["cycle_shape"] = shape_meta
    out["shape_formula"] = (
        "FLASHLOAN_ASSET -> BUY_ANY_MID(ANY_INVARIANT) "
        "[-> ANY_MID(ANY_INVARIANT)]* -> SELL_TO_FLASH(ANY_INVARIANT) -> SURPLUS"
    )
    if "detector" not in out:
        hops = max(0, len(path) - 1)
        if hops == 3:
            out["detector"] = "THREE_LEG_TRIANGLE"
        elif hops == 4:
            out["detector"] = "FOUR_LEG_CYCLE"
        else:
            out["detector"] = "FLASH_MULTI_MID_CYCLE"
    return out
