"""
Comprehensive Unit Tests for the Accounting Module.

This test suite provides an exhaustive verification of the functions within the
`omega_v5.accounting` module. The core focus is on ensuring the mathematical
correctness and ro























































































































































































































































































































































































bustness of unit conversions, which are critical for accurate
profitability calculations and on-chain transaction construction.

The tests cover:
- Gas cost calculations from both Gwei and Wei inputs.
- Bidirectional conversions between native token units (e.g., POL), Gwei, and Wei.
- Bidirectional conversions between raw integer amounts and decimal token units for various precisions.
- Conversion from a USD value to a raw token amount based on a given price.
"""

from decimal import Decimal

from omega_v5.accounting import (
    gas_cost_from_gwei,
    gas_cost_from_wei,
    gwei_to_wei,
    token_raw_to_units,
    token_units_to_raw_floor,
    usd_to_token_raw_floor,
    wei_to_gwei,
)


def test_gas_cost_from_gwei_is_comprehensive():
    """
    Verifies that gas cost calculation from Gwei is correct across a range of inputs.
    This test confirms the conversion from Gwei to the native token (POL) and then to USD,
    ensuring all fields in the resulting GasCost object are accurate.
    """
    # --- Test Case 1: Standard values ---
    # Simulates a typical transaction cost on Polygon.
    # 350,000 gas * 50 Gwei/gas = 17,500,000,000 Gwei-gas
    # (17.5e9 Gwei-gas) / (1e9 Gwei/POL) = 0.0175 POL
    # 0.0175 POL * $0.35/POL = $0.006125
    cost1 = gas_cost_from_gwei(
        gas_units=Decimal("350000"),
        gas_price_gwei=Decimal("50"),
        native_price_usd=Decimal("0.35"),
        native_price_source="test_pol_usd_static",
    )
    assert cost1.gas_price_wei == 50_000_000_000, "Wei price should be Gwei * 1e9"
    assert cost1.gas_price_gwei == Decimal("50"), "Gwei price should match input"
    assert cost1.native_amount == Decimal("0.0175"), "Native amount calculation is incorrect"
    assert cost1.gas_cost_usd == Decimal("0.006125"), "Final USD cost is incorrect"
    assert cost1.gas_payer == "user_wallet", "Default gas payer should be user_wallet"
    assert cost1.native_price_source == "test_pol_usd_static", "Price source should be passed through"

    # --- Test Case 2: Zero gas units ---
    # A transaction with zero gas should result in zero cost.
    cost2 = gas_cost_from_gwei(
        gas_units=Decimal("0"),
        gas_price_gwei=Decimal("50"),
        native_price_usd=Decimal("0.35"),
        native_price_source="test_zero_gas",
    )
    assert cost2.native_amount == Decimal("0"), "Zero gas units must result in zero native amount"
    assert cost2.gas_cost_usd == Decimal("0"), "Zero gas units must result in zero USD cost"

    # --- Test Case 3: Zero gas price ---
    # A zero gas price should also result in zero cost.
    cost3 = gas_cost_from_gwei(
        gas_units=Decimal("350000"),
        gas_price_gwei=Decimal("0"),
        native_price_usd=Decimal("0.35"),
        native_price_source="test_zero_price",
    )
    assert cost3.native_amount == Decimal("0"), "Zero gas price must result in zero native amount"
    assert cost3.gas_cost_usd == Decimal("0"), "Zero gas price must result in zero USD cost"


def test_gas_cost_from_wei_is_comprehensive():
    """
    Verifies that gas cost calculation from Wei is correct. This is often used
    when analyzing a transaction receipt where the `effectiveGasPrice` is given in Wei.
    """
    # 21,000 gas * 30,000,000,000 Wei/gas = 630,000,000,000,000 Wei
    # (6.3e14 Wei) / (1e18 Wei/POL) = 0.00063 POL
    # 0.00063 POL * $0.50/POL = $0.000315
    cost = gas_cost_from_wei(
        gas_units=21000,
        gas_price_wei=30_000_000_000,
        native_price_usd=Decimal("0.50"),
        native_price_source="receipt_effective_gas_price",
    )
    assert cost.gas_price_gwei == Decimal("30"), "Gwei conversion from Wei is incorrect"
    assert cost.native_amount == Decimal("0.00063"), "Native amount calculation from Wei is incorrect"
    assert cost.gas_cost_usd == Decimal("0.000315"), "Final USD cost from Wei is incorrect"


def test_wei_gwei_conversions_are_symmetric():
    """Ensures that conversions between Wei and Gwei are lossless and correct."""
    assert gwei_to_wei(Decimal("1.5")) == 1_500_000_000, "Gwei to Wei conversion failed for decimal"
    assert wei_to_gwei(1_500_000_000) == Decimal("1.5"), "Wei to Gwei conversion failed for integer"
    assert gwei_to_wei(Decimal("100")) == 100_000_000_000, "Gwei to Wei conversion failed for whole number"
    assert wei_to_gwei(100_000_000_000) == Decimal("100"), "Wei to Gwei conversion failed for large integer"
    assert gwei_to_wei(Decimal("0")) == 0, "Zero Gwei should be zero Wei"
    assert wei_to_gwei(0) == Decimal("0"), "Zero Wei should be zero Gwei"


def test_token_units_to_raw_floor_truncates_correctly():
    """Verifies that converting from decimal units to raw integer units correctly floors the value."""
    # Standard case with 18 decimals
    assert token_units_to_raw_floor(Decimal("1.2345"), 18) == 1_234_500_000_000_000_000
    # Standard case with 6 decimals
    assert token_units_to_raw_floor(Decimal("123.456"), 6) == 123_456_000
    # Value with more precision than the target decimals should be floored (truncated)
    assert token_units_to_raw_floor(Decimal("1.999999999"), 6) == 1_999_999
    # Zero value
    assert token_units_to_raw_floor(Decimal("0"), 18) == 0


def test_usd_to_token_raw_floor_is_correct():
    """Verifies conversion from a USD amount to a raw token amount based on price."""
    # Basic case: $100 USD of a token priced at $2 should be 50 tokens.
    # With 6 decimals, this is 50,000,000 raw units.
    assert usd_to_token_raw_floor(Decimal("100"), Decimal("2"), 6) == 50_000_000
    # Case with fractional tokens
    # $150 USD of a token priced at $100 should be 1.5 tokens.
    # With 18 decimals, this is 1,500,000,000,000,000,000 raw units.
    assert usd_to_token_raw_floor(Decimal("150"), Decimal("100"), 18) == 1_500_000_000_000_000_000
    # Case with zero USD should be zero raw, not 1.
    assert usd_to_token_raw_floor(Decimal("0"), Decimal("100"), 18) == 0
    # Case with negative USD should be zero raw.
    assert usd_to_token_raw_floor(Decimal("-10"), Decimal("100"), 18) == 0
    # Micro-amount case
    # $0.001 USD @ $0.50/token = 0.002 tokens. With 18 decimals -> 2_000_000_000_000_000
    assert usd_to_token_raw_floor(Decimal("0.001"), Decimal("0.50"), 18) == 2_000_000_000_000_000


def test_token_raw_to_units_converts_correctly():
    """Verifies that raw integer amounts are correctly converted to token units."""
    # Case 1: 18 decimals (e.g., WETH, DAI)
    assert token_raw_to_units(1_500_000_000_000_000_000, 18) == Decimal("1.5")
    # Case 2: 6 decimals (e.g., USDC)
    assert token_raw_to_units(500_000_000, 6) == Decimal("500")
    # Case 3: Zero value
    assert token_raw_to_units(0, 18) == Decimal("0")
    # Case 4: Large value
    assert token_raw_to_units(12345 * 10**18, 18) == Decimal("12345")
    # Case 5: Small, non-zero value
    assert token_raw_to_units(1, 18) == Decimal("0.000000000000000001")
