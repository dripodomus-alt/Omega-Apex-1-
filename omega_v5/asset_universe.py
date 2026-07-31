#!/usr/bin/env python3
"""Explicit asset-role universes for Apex-Omega routing logistics.

These sets intentionally separate capital sourcing, route middles, swappable
assets, pool-state hydration, and pricing. Do not use ASSET_MATRIX directly for
execution decisions; it is a broad metadata universe.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable


DEFAULT_FLASH_CAPITAL_ASSETS = (
    "USDC",
    "USDC.e",
    "USDT",
    "DAI",
    "WPOL",
    "WETH",
    "WBTC",
)

DEFAULT_BASE_ROUTE_ASSETS = (
    "USDC.e",
    "USDC",
    "WETH",
)

DEFAULT_MID_TOKEN_ASSETS = (
    "USDT",
    "DAI",
    "WPOL",
    "WETH",
    "WBTC",
    "USDC",
    "USDC.e",
    "LINK",
    "AAVE",
    "UNI",
    "QUICK",
    "BAL",
    "CRV",
    "SUSHI",
    "GNS",
    "GHST",
    "TEL",
    "QI",
    "DFYN",
    "EURS",
    "jEUR",
    "EURT",
    "RETH",
    "CBETH",
    "wstETH",
    "ANKR",
    "AVAX",
    "BNB",
    "FXS",
    "USDD",
)

# Assets allowed to appear in swap routes after metadata + behavior checks.
DEFAULT_SWAPPABLE_ASSETS = tuple(dict.fromkeys((
    *DEFAULT_FLASH_CAPITAL_ASSETS,
    *DEFAULT_MID_TOKEN_ASSETS,
    "FRAX",
    "MAI",
    "TUSD",
    "agEUR",
    "MaticX",
    "stMATIC",
    "SNX",
    "MANA",
    "SAND",
    "GHST",
    "RNDR",
    "ANKR",
    "AVAX",
    "BNB",
    "FXS",
    "USDD",
)))

# Assets whose pool reserves/state should be hydrated for route construction.
DEFAULT_POOL_STATE_ASSETS = tuple(dict.fromkeys((
    *DEFAULT_BASE_ROUTE_ASSETS,
    *DEFAULT_MID_TOKEN_ASSETS,
)))

# Assets whose USD price is required for TVL, ranking, gas normalization, and PnL.
DEFAULT_PRICE_ASSETS = tuple(dict.fromkeys((
    *DEFAULT_FLASH_CAPITAL_ASSETS,
    *DEFAULT_SWAPPABLE_ASSETS,
    "POL",
    "WMATIC",
)))


@dataclass(frozen=True)
class AssetUniverse:
    flash_capital_assets: tuple[str, ...]
    base_route_assets: tuple[str, ...]
    mid_token_assets: tuple[str, ...]
    swappable_assets: tuple[str, ...]
    pool_state_assets: tuple[str, ...]
    price_assets: tuple[str, ...]

    def as_dict(self) -> dict[str, list[str]]:
        return {key: list(value) for key, value in asdict(self).items()}


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(v).strip() for v in values if str(v).strip()))


def _parse_csv(value: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if not value:
        return default
    parsed = _dedupe(value.split(","))
    return parsed or default


def build_asset_universe(env_getter=None) -> AssetUniverse:
    env = env_getter or (lambda key, default="": default)
    flash = _parse_csv(env("FLASH_CAPITAL_ASSETS", env("FLASH_BASE_ASSETS", "")), DEFAULT_FLASH_CAPITAL_ASSETS)
    base = _parse_csv(env("BASE_ROUTE_ASSETS", ""), DEFAULT_BASE_ROUTE_ASSETS)
    mids = _parse_csv(env("MID_TOKEN_ASSETS", ""), DEFAULT_MID_TOKEN_ASSETS)
    swappable = _parse_csv(env("SWAPPABLE_ASSETS", ""), DEFAULT_SWAPPABLE_ASSETS)
    pool_state = _parse_csv(env("POOL_STATE_ASSETS", ""), DEFAULT_POOL_STATE_ASSETS)
    prices = _parse_csv(env("PRICE_ASSETS", ""), DEFAULT_PRICE_ASSETS)

    # Enforce role containment without collapsing role identity.
    swappable = _dedupe((*swappable, *base, *mids))
    pool_state = _dedupe((*pool_state, *base, *mids))
    prices = _dedupe((*prices, *flash, *base, *mids))

    return AssetUniverse(
        flash_capital_assets=flash,
        base_route_assets=base,
        mid_token_assets=mids,
        swappable_assets=swappable,
        pool_state_assets=pool_state,
        price_assets=prices,
    )


def asset_role_report(universe: AssetUniverse) -> dict[str, object]:
    role_sets = universe.as_dict()
    overlaps = {
        "flash_and_mid": sorted(set(universe.flash_capital_assets) & set(universe.mid_token_assets)),
        "flash_not_priced": sorted(set(universe.flash_capital_assets) - set(universe.price_assets)),
        "mid_not_swappable": sorted(set(universe.mid_token_assets) - set(universe.swappable_assets)),
        "pool_state_not_priced": sorted(set(universe.pool_state_assets) - set(universe.price_assets)),
    }
    return {"roles": role_sets, "overlaps_and_gaps": overlaps}
