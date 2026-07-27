import unittest
from unittest.mock import patch, MagicMock
from decimal import Decimal
from dataclasses import dataclass
from typing import Tuple, Any

# Mock necessary imports from omega_v5
@dataclass
class MockProfitability:
    net_profit_usd: Decimal = Decimal("0")
    flashloan: Any = None
    gas_cost_usd: Decimal = Decimal("0")

@dataclass
class MockFlashLoanParams:
    principal_usd: Decimal = Decimal("0")

@dataclass
class MockLiveOpportunity:
    path: Tuple[str, ...]
    pool_sequence: Tuple[str, ...]
    protocol_seq: Tuple[str, ...]
    profitability: MockProfitability
    block_detected: int = 0
    metadata: dict = None
    family: str = "C1"

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

class TestBuildTxPayload(unittest.TestCase):

    @patch('omega_v5.execution.TOKEN_ADDRESSES', {
        "WETH": "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",
        "USDC": "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359",
        "DAI": "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063",
        "WBTC": "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6",
    })
    @patch('omega_v5.execution.TOKEN_DECIMALS', {
        "WETH": 18, "USDC": 6, "DAI": 18, "WBTC": 8
    })
    @patch('omega_v5.execution.C1_PAYLOAD_TARGET', "0xExecutorContractAddress")
    @patch('omega_v5.execution.CHAIN_ID', 137)
    @patch('omega_v5.execution.to_raw_units', MagicMock(side_effect=lambda symbol, amount: int(amount * (10**6) if symbol == "USDC" else amount * (10**18))))
    @patch('omega_v5.execution.eip1559_fee_params', MagicMock(return_value=(100_000_000_000, 30_000_000_000, "test_gas_source")))
    @patch('omega_v5.execution.route_tx_gas_limit', MagicMock(return_value=500_000))
    def test_build_tx_payload_two_hop_uniswap_v2(self):
        from omega_v5.execution import build_tx_payload
        
        op = MockLiveOpportunity(
            path=("USDC", "WETH", "USDC"),
            pool_sequence=("pool_usdc_weth_v2", "pool_weth_usdc_v2"),
            protocol_seq=("UniswapV2", "UniswapV2"),
            profitability=MockProfitability(
                net_profit_usd=Decimal("10.0"),
                flashloan=MockFlashLoanParams(principal_usd=Decimal("1000.0"))
            )
        )
        pools = {
            "pool_usdc_weth_v2": {"address": "0x1111111111111111111111111111111111111111", "protocol": "UniswapV2"},
            "pool_weth_usdc_v2": {"address": "0x2222222222222222222222222222222222222222", "protocol": "UniswapV2"},
        }
        nonce = 5
        base_fee_gwei = Decimal("40")

        tx = build_tx_payload(op, pools, nonce, base_fee_gwei)

        self.assertEqual(tx["to"], "0xExecutorContractAddress")
        self.assertEqual(tx["value"], 0)
        self.assertEqual(tx["nonce"], nonce)
        self.assertEqual(tx["chainId"], 137)
        self.assertEqual(tx["gas"], 500_000)
        self.assertEqual(tx["maxFeePerGas"], 100_000_000_000)
        self.assertEqual(tx["maxPriorityFeePerGas"], 30_000_000_000)
        self.assertEqual(tx["type"], 2)
        self.assertTrue(tx["data"].startswith("0x" + "0xafa5f482"[2:])) # Selector for executeFlashArb
        
        # Verify calldata structure (simplified check)
        self.assertIn("0x3c499c542cef5e3811e1192ce70d8cc03d5c3359"[2:].lower(), tx["data"].lower()) # USDC address
        self.assertIn("0x7ceb23fd6bc0add59e62ac25578270cff1b9f619"[2:].lower(), tx["data"].lower()) # WETH address
        self.assertIn("0x1111111111111111111111111111111111111111"[2:].lower(), tx["data"].lower())
        self.assertIn("0x2222222222222222222222222222222222222222"[2:].lower(), tx["data"].lower())
        self.assertIn("01", tx["data"]) # Protocol ID for UniswapV2

    @patch('omega_v5.execution.TOKEN_ADDRESSES', {
        "WETH": "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",
        "USDC": "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359",
        "DAI": "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063",
        "WBTC": "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6",
    })
    @patch('omega_v5.execution.TOKEN_DECIMALS', {
        "WETH": 18, "USDC": 6, "DAI": 18, "WBTC": 8
    })
    @patch('omega_v5.execution.C1_PAYLOAD_TARGET', "0xExecutorContractAddress")
    @patch('omega_v5.execution.CHAIN_ID', 137)
    @patch('omega_v5.execution.to_raw_units', MagicMock(side_effect=lambda symbol, amount: int(amount * (10**6) if symbol == "USDC" else amount * (10**18))))
    @patch('omega_v5.execution.eip1559_fee_params', MagicMock(return_value=(100_000_000_000, 30_000_000_000, "test_gas_source")))
    @patch('omega_v5.execution.route_tx_gas_limit', MagicMock(return_value=700_000))
    def test_build_tx_payload_three_hop_mixed_protocols(self):
        from omega_v5.execution import build_tx_payload

        op = MockLiveOpportunity(
            path=("USDC", "WETH", "DAI", "USDC"),
            pool_sequence=("pool_usdc_weth_v3", "pool_weth_dai_v2", "pool_dai_usdc_algebra"),
            protocol_seq=("UniswapV3", "UniswapV2", "Algebra"),
            profitability=MockProfitability(
                net_profit_usd=Decimal("15.0"),
                flashloan=MockFlashLoanParams(principal_usd=Decimal("5000.0"))
            )
        )
        pools = {
            "pool_usdc_weth_v3": {"address": "0x3333333333333333333333333333333333333333", "protocol": "UniswapV3"},
            "pool_weth_dai_v2": {"address": "0x4444444444444444444444444444444444444444", "protocol": "UniswapV2"},
            "pool_dai_usdc_algebra": {"address": "0x5555555555555555555555555555555555555555", "protocol": "Algebra"},
        }
        nonce = 10

        tx = build_tx_payload(op, pools, nonce)

        self.assertEqual(tx["to"], "0xExecutorContractAddress")
        self.assertEqual(tx["nonce"], nonce)
        self.assertEqual(tx["gas"], 700_000) # 3 hops
        self.assertTrue(tx["data"].startswith("0x" + "0xafa5f482"[2:])) # Selector
        
        # Check protocol IDs
        self.assertIn("02", tx["data"]) # UniswapV3
        self.assertIn("01", tx["data"]) # UniswapV2
        self.assertIn("03", tx["data"]) # Algebra

    @patch('omega_v5.execution.TOKEN_ADDRESSES', {
        "WETH": "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",
        "USDC": "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359",
    })
    @patch('omega_v5.execution.TOKEN_DECIMALS', {
        "WETH": 18, "USDC": 6
    })
    @patch('omega_v5.execution.C1_PAYLOAD_TARGET', "0xExecutorContractAddress")
    @patch('omega_v5.execution.CHAIN_ID', 137)
    @patch('omega_v5.execution.to_raw_units', MagicMock(side_effect=lambda symbol, amount: int(amount * (10**6) if symbol == "USDC" else amount * (10**18))))
    @patch('omega_v5.execution.eip1559_fee_params', MagicMock(return_value=(100_000_000_000, 30_000_000_000, "test_gas_source")))
    @patch('omega_v5.execution.route_tx_gas_limit', MagicMock(return_value=500_000))
    def test_build_tx_payload_missing_flash_asset_address(self):
        from omega_v5.execution import build_tx_payload

        op = MockLiveOpportunity(
            path=("UNKNOWN_TOKEN", "WETH", "UNKNOWN_TOKEN"),
            pool_sequence=("pool_unknown_weth", "pool_weth_unknown"),
            protocol_seq=("UniswapV2", "UniswapV2"),
            profitability=MockProfitability(
                net_profit_usd=Decimal("5.0"),
                flashloan=MockFlashLoanParams(principal_usd=Decimal("500.0"))
            )
        )
        pools = {
            "pool_unknown_weth": {"address": "0x1111111111111111111111111111111111111111", "protocol": "UniswapV2"},
            "pool_weth_unknown": {"address": "0x2222222222222222222222222222222222222222", "protocol": "UniswapV2"},
        }

        with self.assertRaisesRegex(ValueError, "Missing address for flash asset UNKNOWN_TOKEN"):
            build_tx_payload(op, pools)

    @patch('omega_v5.execution.TOKEN_ADDRESSES', {
        "WETH": "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",
        "USDC": "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359",
    })
    @patch('omega_v5.execution.TOKEN_DECIMALS', {
        "WETH": 18, "USDC": 6
    })
    @patch('omega_v5.execution.C1_PAYLOAD_TARGET', "0xExecutorContractAddress")
    @patch('omega_v5.execution.CHAIN_ID', 137)
    @patch('omega_v5.execution.to_raw_units', MagicMock(side_effect=lambda symbol, amount: int(amount * (10**6) if symbol == "USDC" else amount * (10**18))))
    @patch('omega_v5.execution.eip1559_fee_params', MagicMock(return_value=(100_000_000_000, 30_000_000_000, "test_gas_source")))
    @patch('omega_v5.execution.route_tx_gas_limit', MagicMock(return_value=500_000))
    def test_build_tx_payload_missing_pool_metadata(self):
        from omega_v5.execution import build_tx_payload

        op = MockLiveOpportunity(
            path=("USDC", "WETH", "USDC"),
            pool_sequence=("pool_usdc_weth_v2", "pool_weth_usdc_v2"),
            protocol_seq=("UniswapV2", "UniswapV2"),
            profitability=MockProfitability(
                net_profit_usd=Decimal("10.0"),
                flashloan=MockFlashLoanParams(principal_usd=Decimal("1000.0"))
            )
        )
        pools = {
            "pool_usdc_weth_v2": {"address": "0x1111111111111111111111111111111111111111", "protocol": "UniswapV2"},
            # "pool_weth_usdc_v2" is missing
        }

        with self.assertRaisesRegex(ValueError, "Pool metadata not found for pool_id: pool_weth_usdc_v2"):
            build_tx_payload(op, pools)

    @patch('omega_v5.execution.TOKEN_ADDRESSES', {
        "WETH": "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",
        "USDC": "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359",
    })
    @patch('omega_v5.execution.TOKEN_DECIMALS', {
        "WETH": 18, "USDC": 6
    })
    @patch('omega_v5.execution.C1_PAYLOAD_TARGET', "0xExecutorContractAddress")
    @patch('omega_v5.execution.CHAIN_ID', 137)
    @patch('omega_v5.execution.to_raw_units', MagicMock(side_effect=lambda symbol, amount: int(amount * (10**6) if symbol == "USDC" else amount * (10**18))))
    @patch('omega_v5.execution.eip1559_fee_params', MagicMock(return_value=(100_000_000_000, 30_000_000_000, "test_gas_source")))
    @patch('omega_v5.execution.route_tx_gas_limit', MagicMock(return_value=500_000))
    def test_build_tx_payload_missing_token_address_in_route_step(self):
        from omega_v5.execution import build_tx_payload

        op = MockLiveOpportunity(
            path=("USDC", "UNKNOWN_TOKEN_IN_ROUTE", "USDC"),
            pool_sequence=("pool_usdc_unknown", "pool_unknown_usdc"),
            protocol_seq=("UniswapV2", "UniswapV2"),
            profitability=MockProfitability(
                net_profit_usd=Decimal("10.0"),
                flashloan=MockFlashLoanParams(principal_usd=Decimal("1000.0"))
            )
        )
        pools = {
            "pool_usdc_unknown": {"address": "0x1111111111111111111111111111111111111111", "protocol": "UniswapV2"},
            "pool_unknown_usdc": {"address": "0x2222222222222222222222222222222222222222", "protocol": "UniswapV2"},
        }

        with self.assertRaisesRegex(ValueError, "Missing address in route step 0: from=0x3c499c542cef5e3811e1192ce70d8cc03d5c3359 to=None"):
            build_tx_payload(op, pools)

    @patch('omega_v5.execution.TOKEN_ADDRESSES', {
        "WETH": "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",
        "USDC": "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359",
    })
    @patch('omega_v5.execution.TOKEN_DECIMALS', {
        "WETH": 18, "USDC": 6
    })
    @patch('omega_v5.execution.C1_PAYLOAD_TARGET', "0xExecutorContractAddress")
    @patch('omega_v5.execution.CHAIN_ID', 137)
    @patch('omega_v5.execution.to_raw_units', MagicMock(side_effect=lambda symbol, amount: int(amount * (10**6) if symbol == "USDC" else amount * (10**18))))
    @patch('omega_v5.execution.eip1559_fee_params', MagicMock(side_effect=Exception("Gas oracle failed")))
    @patch('omega_v5.execution.route_tx_gas_limit', MagicMock(return_value=500_000))
    def test_build_tx_payload_eip1559_fallback(self):
        from omega_v5.execution import build_tx_payload

        op = MockLiveOpportunity(
            path=("USDC", "WETH", "USDC"),
            pool_sequence=("pool_usdc_weth_v2", "pool_weth_usdc_v2"),
            protocol_seq=("UniswapV2", "UniswapV2"),
            profitability=MockProfitability(
                net_profit_usd=Decimal("10.0"),
                flashloan=MockFlashLoanParams(principal_usd=Decimal("1000.0"))
            )
        )
        pools = {
            "pool_usdc_weth_v2": {"address": "0x1111111111111111111111111111111111111111", "protocol": "UniswapV2"},
            "pool_weth_usdc_v2": {"address": "0x2222222222222222222222222222222222222222", "protocol": "UniswapV2"},
        }
        base_fee_gwei = Decimal("30")

        tx = build_tx_payload(op, pools, base_fee_gwei=base_fee_gwei)

        self.assertEqual(tx["maxFeePerGas"], int((base_fee_gwei + Decimal("30")) * Decimal("1e9")))
        self.assertEqual(tx["maxPriorityFeePerGas"], int(Decimal("30") * Decimal("1e9")))
        self.assertEqual(tx["gasFeeSource"], "legacy_base_plus_30_gwei")


class TestRevalidateAtBroadcast(unittest.TestCase):
    """Tests for re-profitability check before broadcast (simultaneous C1/C2/Liq)."""

    def test_revalidate_profitability_at_broadcast_accepts_still_profitable(self):
        from omega_v5.execution import revalidate_profitability_at_broadcast
        op = MockLiveOpportunity(
            path=("USDC", "WETH", "USDC"),
            pool_sequence=("p1", "p2"),
            protocol_seq=("UniswapV2", "UniswapV2"),
            profitability=MockProfitability(net_profit_usd=Decimal("25.0")),
            family="C1"
        )
        pools = {"p1": {}, "p2": {}}
        self.assertTrue(revalidate_profitability_at_broadcast(op, pools))

    def test_revalidate_profitability_at_broadcast_rejects_negative(self):
        from omega_v5.execution import revalidate_profitability_at_broadcast
        op = MockLiveOpportunity(
            path=("USDC", "WETH", "USDC"),
            pool_sequence=("p1", "p2"),
            protocol_seq=("UniswapV2", "UniswapV2"),
            profitability=MockProfitability(net_profit_usd=Decimal("-3.0")),
            family="C2"
        )
        pools = {"p1": {}, "p2": {}}
        self.assertFalse(revalidate_profitability_at_broadcast(op, pools))

    def test_supports_liquidation_family(self):
        from omega_v5.execution import revalidate_profitability_at_broadcast
        op = MockLiveOpportunity(
            path=("USDC",),
            pool_sequence=(),
            protocol_seq=(),
            profitability=MockProfitability(net_profit_usd=Decimal("180.0")),
            family="LIQUIDATION"
        )
        self.assertTrue(revalidate_profitability_at_broadcast(op, {}))


if __name__ == '__main__':
    unittest.main()
