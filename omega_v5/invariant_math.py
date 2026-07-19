# ==============================================================================
# invariant_math.py -- Canonical DeFi Invariant Math
#
# This module provides pure, explicit Python implementations of the core swap equations
# for major AMM protocols. It serves as a verifiable reference for the system's
# financial logic.
#
# Block-Bound Execution Principle:
# --------------------------------
# This module contains pure math functions. It does not track block numbers.
# Callers are responsible for enforcing the system's execution discipline:
#
# 1. Bind: At discovery block `n`, snapshot all pool states and live expenses.
# 2. Quote: Use the state from block `n` to compute a gross output `y`.
# 3. Gate: Execute only if `current_block <= n + 4`. After this, the route is stale.
# ==============================================================================

from __future__ import annotations
from decimal import Decimal

# ------------------------------------------------------------------------------
# Primitive Swap Functions
# ------------------------------------------------------------------------------

def quote_uniswap_v2(
    reserve_in: Decimal,
    reserve_out: Decimal,
    amount_in: Decimal,
    fee_fraction: Decimal = Decimal("0.003"),
) -> Decimal:
    """
    Calculates the output amount for a Uniswap V2 (CPMM) swap.

    F_V2(x) = (γ * x * R_out) / (R_in + γ * x)
    where γ = 1 - f
    """
    if amount_in <= 0 or reserve_in <= 0 or reserve_out <= 0:
        return Decimal("0")

    gamma = Decimal("1") - fee_fraction
    amount_in_with_fee = amount_in * gamma

    numerator = amount_in_with_fee * reserve_out
    denominator = reserve_in + amount_in_with_fee

    if denominator <= 0:
        return Decimal("0")

    return numerator / denominator


def quote_uniswap_v3_token0_to_1(
    sqrt_price: Decimal,
    liquidity: Decimal,
    amount_in_token0: Decimal,
    fee_fraction: Decimal = Decimal("0.0005"),
) -> Decimal:
    """
    Calculates the output amount for a Uniswap V3 (CLMM) token0 -> token1 swap
    within a single active tick.

    S' = (L * S) / (L + x' * S)
    Δy = L * (S - S')
    """
    if amount_in_token0 <= 0 or liquidity <= 0 or sqrt_price <= 0:
        return Decimal("0")

    gamma = Decimal("1") - fee_fraction
    amount_in_with_fee = amount_in_token0 * gamma

    # The amount of token0 required to move the price is Δx = L * (1/S_new - 1/S_current).
    # We have Δx (amount_in_with_fee) and need to solve for S_new.
    # Δx = L/S_new - L/S_current  =>  S_new = L / (Δx + L/S_current)
    # This simplifies to the formula below.
    new_sqrt_price = (liquidity * sqrt_price) / (liquidity + amount_in_with_fee * sqrt_price)

    # The amount of token1 out is the change in liquidity's token1 value
    amount_out_token1 = liquidity * (sqrt_price - new_sqrt_price)
    return amount_out_token1


def quote_uniswap_v3_token1_to_0(
    sqrt_price: Decimal,
    liquidity: Decimal,
    amount_in_token1: Decimal,
    fee_fraction: Decimal = Decimal("0.0005"),
) -> Decimal:
    """
    Calculates the output amount for a Uniswap V3 (CLMM) token1 -> token0 swap
    within a single active tick.

    S' = S + (x' / L)
    F(x) = L * (1/S - 1/S')
    """
    if amount_in_token1 <= 0 or liquidity <= 0 or sqrt_price <= 0:
        return Decimal("0")

    gamma = Decimal("1") - fee_fraction
    amount_in_with_fee = amount_in_token1 * gamma

    # Calculate the new sqrt_price after the swap
    new_sqrt_price = sqrt_price + (amount_in_with_fee / liquidity)

    if new_sqrt_price <= 0:
        return Decimal("0")

    # The amount of token0 out is the change in liquidity's token0 value
    amount_out_token0 = liquidity * ((Decimal("1") / sqrt_price) - (Decimal("1") / new_sqrt_price))
    return amount_out_token0


def quote_algebra_clmm(
    sqrt_price: Decimal,
    liquidity: Decimal,
    amount_in: Decimal,
    is_token0_in: bool,
    dynamic_fee_fraction: Decimal,
) -> Decimal:
    """
    Calculates the output for an Algebra CLMM swap, which uses Uniswap V3
    math but with a dynamically sourced fee.
    """
    if is_token0_in:
        return quote_uniswap_v3_token0_to_1(
            sqrt_price, liquidity, amount_in, dynamic_fee_fraction
        )
    else:
        return quote_uniswap_v3_token1_to_0(
            sqrt_price, liquidity, amount_in, dynamic_fee_fraction
        )


def quote_balancer_weighted(
    balance_in: Decimal,
    balance_out: Decimal,
    weight_in: Decimal,
    weight_out: Decimal,
    amount_in: Decimal,
    fee_fraction: Decimal = Decimal("0.001"),
) -> Decimal:
    """
    Calculates the output amount for a Balancer Weighted Pool swap.

    F(x) = B_o * [1 - (B_i / (B_i + x'))^(w_i / w_o)]
    where x' = x * (1 - f)
    """
    if amount_in <= 0 or balance_in <= 0 or balance_out <= 0 or weight_in <= 0 or weight_out <= 0:
        return Decimal("0")

    amount_in_with_fee = amount_in * (Decimal("1") - fee_fraction)

    # Ratio of balances after adding the input amount
    ratio = balance_in / (balance_in + amount_in_with_fee)

    # Exponent is the ratio of weights
    exponent = weight_in / weight_out

    # Final amount out calculation
    amount_out = balance_out * (Decimal("1") - (ratio ** exponent))
    return amount_out


# Note: A full Curve StableSwap implementation requires an iterative solver
# for the invariant D, which is more complex than a single formula. The
# functions above represent the non-iterative AMM primitives.


def net_profit(
    amount_out_final: Decimal,
    amount_in_initial: Decimal,
    cost_flash_at_bind: Decimal,
    cost_gas_at_bind: Decimal,
    cost_relay_at_bind: Decimal = Decimal("0"),
    cost_risk_at_bind: Decimal = Decimal("0"),
) -> Decimal:
    """
    Calculates the net profit of a route based on expenses at bind time.

    π_n = y_n - x - C_flash,n - C_gas,n - C_relay,n - C_risk,n

    This function is pure. The caller must ensure all inputs are from the same
    discovery block `n` to respect the block-bound execution principle.
    """
    return (
        amount_out_final
        - amount_in_initial
        - cost_flash_at_bind
        - cost_gas_at_bind
        - cost_relay_at_bind
        - cost_risk_at_bind
    )


# ------------------------------------------------------------------------------
# Composed Route Family Functions
# ------------------------------------------------------------------------------

def quote_v2_to_v2(
    amount_in: Decimal,
    pool1: dict[str, Decimal],
    pool2: dict[str, Decimal],
) -> Decimal:
    """Quotes a V2 -> V2 route by sequentially composing the primitive function."""
    amount_mid = quote_uniswap_v2(
        pool1["reserve_in"], pool1["reserve_out"], amount_in, pool1["fee"]
    )
    if amount_mid <= 0:
        return Decimal("0")
    return quote_uniswap_v2(
        pool2["reserve_in"], pool2["reserve_out"], amount_mid, pool2.get("fee", pool1.get("fee"))
    )


def quote_v3_to_v2(
    amount_in: Decimal,
    pool1_v3: dict[str, Any],
    pool2_v2: dict[str, Decimal],
) -> Decimal:
    """Quotes a V3 -> V2 route by sequentially composing the primitive functions."""
    is_token0_in = pool1_v3.get("is_token0_in", False)
    if is_token0_in:
        amount_mid = quote_uniswap_v3_token0_to_1(
            pool1_v3["sqrt_price"], pool1_v3["liquidity"], amount_in, pool1_v3["fee"]
        )
    else:
        amount_mid = quote_uniswap_v3_token1_to_0(
            pool1_v3["sqrt_price"], pool1_v3["liquidity"], amount_in, pool1_v3["fee"]
        )

    if amount_mid <= 0:
        return Decimal("0")
    return quote_uniswap_v2(
        pool2_v2["reserve_in"], pool2_v2["reserve_out"], amount_mid, pool2_v2.get("fee", pool1_v3.get("fee"))
    )


# Note: Other composed functions (V2->V3, V3->V3, Balancer->V3, etc.) would
# follow the same pattern of calling the primitive functions in sequence.
# A full implementation would require careful handling of state parameters
# (e.g., `is_token0_in`) for each leg of the route.
