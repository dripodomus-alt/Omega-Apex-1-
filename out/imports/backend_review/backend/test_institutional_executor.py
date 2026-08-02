"""
Test InstitutionalExecutor payload encoding.

Unit tests verify price-aware USD-to-native conversion without RPC access.
The integration helper at the bottom can still be run manually when a Polygon RPC is configured.
"""

import os
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from eth_abi import decode
from web3 import Web3

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from institutional_executor import InstitutionalExecutorPayloadBuilder  # noqa: E402


TOKENS = {
    "USDC": {
        "address": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
        "decimals": 6,
        "price": Decimal("1"),
    },
    "WMATIC": {
        "address": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",
        "decimals": 18,
        "price": Decimal("0.85"),
    },
    "WETH": {
        "address": "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",
        "decimals": 18,
        "price": Decimal("3300"),
    },
    "WBTC": {
        "address": "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6",
        "decimals": 8,
        "price": Decimal("95000"),
    },
}


def usd_to_native(usd, token):
    return int((Decimal(str(usd)) / token["price"]) * (Decimal(10) ** token["decimals"]))


def decode_v2_swap(calldata):
    return decode(
        ["uint256", "uint256", "address[]", "address", "uint256"],
        calldata[4:],
    )


def make_spread(symbol):
    borrowed = TOKENS[symbol]
    usdc = TOKENS["USDC"]
    loan_usd = Decimal("1000")
    leg1_out_usd = Decimal("1004")
    leg2_out_usd = Decimal("1012")
    net_profit_usd = Decimal("12")

    return {
        "id": f"test-{symbol}",
        "timestamp": 1234567890,
        "tokenPair": f"{symbol}/USDC",
        "flashLoan": {
            "loanAmountUsd": float(loan_usd),
            "loanToken": borrowed["address"],
            "loanTokenDecimals": borrowed["decimals"],
            "loanTokenPriceUsd": str(borrowed["price"]),
            "profitToken": borrowed["address"],
            "profitTokenDecimals": borrowed["decimals"],
            "profitTokenPriceUsd": str(borrowed["price"]),
            "netProfitUsd": float(net_profit_usd),
            "leg1": {
                "pool": "0x86f1d8390222a3691c28938ec7404a1661e618e0",
                "dex": "QuickSwap V2",
                "protocol": 2,
                "tokenIn": borrowed["address"],
                "tokenOut": usdc["address"],
                "amountInUsd": float(loan_usd),
                "amountOutUsd": float(leg1_out_usd),
                "tokenInDecimals": borrowed["decimals"],
                "tokenOutDecimals": usdc["decimals"],
                "tokenInPriceUsd": str(borrowed["price"]),
                "tokenOutPriceUsd": str(usdc["price"]),
            },
            "leg2": {
                "pool": "0xadbf1854e5883eb8aa7baf50705338739e558e5b",
                "dex": "SushiSwap",
                "protocol": 2,
                "tokenIn": usdc["address"],
                "tokenOut": borrowed["address"],
                # Deliberately wrong/poisoned; builder must use leg1's expected output.
                "amountIn": "1",
                "amountInUsd": 1,
                "amountOutUsd": float(leg2_out_usd),
                "tokenInDecimals": usdc["decimals"],
                "tokenOutDecimals": borrowed["decimals"],
                "tokenInPriceUsd": str(usdc["price"]),
                "tokenOutPriceUsd": str(borrowed["price"]),
            },
        },
    }


@pytest.mark.parametrize("symbol", ["USDC", "WMATIC", "WETH", "WBTC"])
def test_payload_builder_uses_price_aware_native_conversions(symbol):
    builder = InstitutionalExecutorPayloadBuilder(Web3())
    payload = builder.build_payload_from_spread(
        make_spread(symbol),
        use_balancer=True,
        slippage_bps=50,
        deadline_seconds=300,
    )

    borrowed = TOKENS[symbol]
    expected_loan = usd_to_native("1000", borrowed)
    expected_profit = usd_to_native("12", borrowed)
    expected_leg1_out = usd_to_native("1004", TOKENS["USDC"])
    expected_leg2_out = usd_to_native("1012", borrowed)

    assert payload.amount == expected_loan
    assert payload.min_profit == expected_profit

    leg1_amount_in, leg1_amount_out_min, leg1_path, _, _ = decode_v2_swap(payload.calldatas[0])
    leg2_amount_in, leg2_amount_out_min, leg2_path, _, _ = decode_v2_swap(payload.calldatas[1])

    assert leg1_amount_in == expected_loan
    assert leg1_amount_out_min == expected_leg1_out * 9950 // 10000
    assert [Web3.to_checksum_address(address) for address in leg1_path] == [
        Web3.to_checksum_address(borrowed["address"]),
        Web3.to_checksum_address(TOKENS["USDC"]["address"]),
    ]

    assert leg2_amount_in == expected_leg1_out
    assert leg2_amount_out_min == expected_leg2_out * 9950 // 10000
    assert [Web3.to_checksum_address(address) for address in leg2_path] == [
        Web3.to_checksum_address(TOKENS["USDC"]["address"]),
        Web3.to_checksum_address(borrowed["address"]),
    ]


def test_payload_builder_fails_closed_when_usd_values_have_no_price_metadata():
    spread = make_spread("WMATIC")
    del spread["flashLoan"]["loanTokenPriceUsd"]
    del spread["flashLoan"]["leg1"]["tokenInPriceUsd"]
    del spread["flashLoan"]["leg1"]["tokenOutPriceUsd"]

    builder = InstitutionalExecutorPayloadBuilder(Web3())
    with pytest.raises(ValueError, match="missing loanTokenPriceUsd"):
        builder.build_payload_from_spread(spread)


def run_payload_encoding_integration():
    """Manual RPC smoke test: `python backend/test_institutional_executor.py`."""
    print("=" * 80)
    print("Testing InstitutionalExecutor Payload Encoding")
    print("=" * 80)

    rpc_url = os.getenv("POLYGON_RPC_URL", "")
    if not rpc_url or "YOUR_API_KEY" in rpc_url:
        print("❌ ERROR: POLYGON_RPC_URL not configured in .env")
        return False

    w3 = Web3(Web3.HTTPProvider(rpc_url))

    if not w3.is_connected():
        print("❌ ERROR: Cannot connect to Polygon RPC")
        return False

    print("✅ Connected to Polygon RPC")
    print(f"   Latest block: {w3.eth.block_number}")

    from institutional_executor import InstitutionalExecutor, C1_ADDRESS

    executor = InstitutionalExecutor(w3)
    print("✅ InstitutionalExecutor initialized")
    print(f"   Contract: {C1_ADDRESS}")

    mock_spread = make_spread("WMATIC")

    try:
        result_balancer = executor.build_execution_from_spread(
            spread=mock_spread,
            from_address="0x0000000000000000000000000000000000000000",
            use_balancer=True,
            dry_run=True,
        )

        print("\n✅ Balancer Flash Loan Payload Built:")
        print(f"   Provider: {result_balancer['payload']['flash_provider']}")
        print(f"   Asset: {result_balancer['payload']['asset']}")
        print(f"   Amount: {result_balancer['payload']['amount']}")
        print(f"   Min Profit: {result_balancer['payload']['min_profit']}")
        print(f"   Targets: {len(result_balancer['payload']['targets'])} routers")
        print(f"   Estimated Gas: {result_balancer['estimated_gas']:,}")

        print("\n" + "=" * 80)
        print("✅ ALL TESTS PASSED")
        print("=" * 80)
        return True

    except Exception as e:
        print(f"\n❌ ERROR building payload: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_payload_encoding_integration()
    sys.exit(0 if success else 1)
