#!/usr/bin/env python3
# ==============================================================================
# accounting.py -- unit-safe token, native gas, and USD accounting helpers.
# ==============================================================================

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR
from typing import Any


WEI_PER_POL = Decimal("1000000000000000000")
WEI_PER_GWEI = Decimal("1000000000")


def decimal_value(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return default


def wei_to_gwei(wei: int | Decimal) -> Decimal:
    return decimal_value(wei) / WEI_PER_GWEI


def gwei_to_wei(gwei: Decimal) -> int:
    return max(0, int((decimal_value(gwei) * WEI_PER_GWEI).to_integral_value(rounding=ROUND_FLOOR)))


def wei_to_native(wei: int | Decimal) -> Decimal:
    return decimal_value(wei) / WEI_PER_POL


def gwei_to_native_per_gas(gwei: Decimal) -> Decimal:
    return decimal_value(gwei) / WEI_PER_GWEI


def token_units_to_raw_floor(amount: Decimal, decimals: int) -> int:
    units = decimal_value(amount) * (Decimal(10) ** int(decimals))
    return max(0, int(units.to_integral_value(rounding=ROUND_FLOOR)))


def token_raw_to_units(raw: int | Decimal, decimals: int) -> Decimal:
    return decimal_value(raw) / (Decimal(10) ** int(decimals))


def usd_to_token_raw_floor(usd_amount: Decimal, price_usd: Decimal, decimals: int) -> int:
    price = decimal_value(price_usd)
    usd_amount_dec = decimal_value(usd_amount)
    if usd_amount_dec <= 0:
        return 0
    if price <= 0:
        raise ValueError("token USD price must be positive")
    amount = usd_amount_dec / price
    return token_units_to_raw_floor(amount, decimals)


@dataclass(frozen=True)
class GasCost:
    gas_units: Decimal
    gas_price_wei: int
    gas_price_gwei: Decimal
    native_amount: Decimal
    native_symbol: str
    native_price_usd: Decimal
    native_price_source: str
    gas_cost_usd: Decimal
    gas_payer: str = "user_wallet"

    def as_dict(self) -> dict[str, str]:
        return {
            "gas_units": str(self.gas_units),
            "gas_price_wei": str(self.gas_price_wei),
            "gas_price_gwei": str(self.gas_price_gwei),
            "native_amount": str(self.native_amount),
            "native_symbol": self.native_symbol,
            "native_price_usd": str(self.native_price_usd),
            "native_price_source": self.native_price_source,
            "gas_cost_usd": str(self.gas_cost_usd),
            "gas_payer": self.gas_payer,
        }


def gas_cost_from_gwei(
    gas_units: Decimal,
    gas_price_gwei: Decimal,
    native_price_usd: Decimal,
    native_price_source: str,
    *,
    native_symbol: str = "POL",
) -> GasCost:
    units = decimal_value(gas_units)
    gas_price_gwei = Decimal(str(gas_price_gwei))
    pol_price_usd = Decimal(str(native_price_usd))

    # 1 Gwei = 10^9 Wei. 1 POL = 10^18 Wei. Total gas in POL = (units * price_gwei * 10^9) / 10^18
    # Simplified: (units * price_gwei) / 10^9.
    native_amount = (units * gas_price_gwei) / Decimal("1e9")
    gas_cost_usd = native_amount * pol_price_usd

    return GasCost(
        gas_units=units,
        gas_price_wei=gwei_to_wei(gas_price_gwei),
        gas_price_gwei=gas_price_gwei,
        native_amount=native_amount,
        native_symbol=native_symbol,
        native_price_usd=pol_price_usd,
        native_price_source=native_price_source,
        gas_cost_usd=gas_cost_usd,
    )


def gas_cost_from_wei(
    gas_units: int | Decimal,
    gas_price_wei: int | Decimal,
    native_price_usd: Decimal,
    native_price_source: str,
    *,
    native_symbol: str = "POL",
) -> GasCost:
    units = decimal_value(gas_units)
    wei = int(decimal_value(gas_price_wei).to_integral_value(rounding=ROUND_FLOOR))
    native_amount = units * wei_to_native(wei)
    native_price = decimal_value(native_price_usd)
    return GasCost(
        gas_units=units,
        gas_price_wei=max(0, wei),
        gas_price_gwei=wei_to_gwei(wei),
        native_amount=native_amount,
        native_symbol=native_symbol,
        native_price_usd=native_price,
        native_price_source=native_price_source,
        gas_cost_usd=native_amount * native_price,
    )
