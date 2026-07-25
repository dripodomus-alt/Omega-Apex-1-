# ==============================================================================
# oracle_sources.py -- Concrete implementations of the OracleSource interface.
#
# This module provides pluggable sources for the PrecisionPricingEngine,
# allowing it to aggregate prices from various on-chain and off-chain venues.
# ==============================================================================

from __future__ import annotations

from web3 import Web3

from .precision_pricing import (
    OracleSource,
    OracleKind,
    OracleObservation,
    TokenMetadata,
    PricingContext,
    PricingError,
)
from .. import rpc_layer

# Minimal ABI for Chainlink AggregatorV3Interface
CHAINLINK_ABI = [
    {
        "inputs": [],
        "name": "latestRoundData",
        "outputs": [
            {"internalType": "uint80", "name": "roundId", "type": "uint80"},
            {"internalType": "int256", "name": "answer", "type": "int256"},
            {"internalType": "uint256", "name": "startedAt", "type": "uint256"},
            {"internalType": "uint256", "name": "updatedAt", "type": "uint256"},
            {"internalType": "uint80", "name": "answeredInRound", "type": "uint80"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
]

# Minimal ABI for Uniswap V2 Pair
UNISWAP_V2_PAIR_ABI = [
    {
        "inputs": [],
        "name": "getReserves",
        "outputs": [
            {"internalType": "uint112", "name": "_reserve0", "type": "uint112"},
            {"internalType": "uint112", "name": "_reserve1", "type": "uint112"},
            {"internalType": "uint32", "name": "_blockTimestampLast", "type": "uint32"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {"inputs": [], "name": "token0", "outputs": [{"internalType": "address", "name": "", "type": "address"}], "stateMutability": "view", "type": "function"},
]


class ChainlinkSource(OracleSource):
    """An OracleSource that reads from Chainlink's on-chain price feeds."""

    def __init__(self, chain_id: int, feed_registry: dict[str, str]):
        self.id = f"chainlink_feeds_chain_{chain_id}"
        self.kind = OracleKind.ONCHAIN_FEED
        self.chain_id = chain_id
        self.feed_registry = {addr.lower(): feed for addr, feed in feed_registry.items()}
        self.w3 = rpc_layer.get_w3_instance_for_chain(chain_id)

    def read_usd_price(self, token: TokenMetadata, context: PricingContext) -> OracleObservation:
        feed_address = self.feed_registry.get(token.address.lower())
        if not feed_address:
            raise PricingError(f"No Chainlink feed registered for {token.symbol}", "SOURCE_CONFIG_ERROR")

        contract = self.w3.eth.contract(address=Web3.to_checksum_address(feed_address), abi=CHAINLINK_ABI)
        try:
            # Returns (roundId, answer, startedAt, updatedAt, answeredInRound)
            round_data = contract.functions.latestRoundData().call(block_identifier=context.current_block)
            answer_decimals = contract.functions.decimals().call(block_identifier=context.current_block)
        except Exception as e:
            raise PricingError(f"Chainlink contract call failed for {token.symbol}: {e}", "SOURCE_RPC_ERROR")

        return OracleObservation(
            source_id=self.id,
            source_kind=self.kind,
            answer=round_data[1],
            answer_decimals=answer_decimals,
            updated_at=round_data[3],
            observed_at_block=context.current_block,
            confidence_bps=9900,  # Chainlink feeds are high confidence
        )


class DexV2UsdPairSource(OracleSource):
    """
    An OracleSource that derives a spot price from a Uniswap V2-style pool,
    assuming one asset is the target token and the other is a reference stablecoin (e.g., USDC).
    """

    def __init__(self, chain_id: int, pool_address: str, reference_stable: TokenMetadata):
        self.id = f"dex_v2_spot_{pool_address[:10]}"
        self.kind = OracleKind.DEX_TWAP  # Using this kind, though it's a spot price
        self.chain_id = chain_id
        self.pool_address = Web3.to_checksum_address(pool_address)
        self.reference_stable = reference_stable
        self.w3 = rpc_layer.get_w3_instance_for_chain(chain_id)
        self.contract = self.w3.eth.contract(address=self.pool_address, abi=UNISWAP_V2_PAIR_ABI)

    def read_usd_price(self, token: TokenMetadata, context: PricingContext) -> OracleObservation:
        try:
            token0_address = self.contract.functions.token0().call()
            reserves = self.contract.functions.getReserves().call(block_identifier=context.current_block)
        except Exception as e:
            raise PricingError(f"DEX V2 pool contract call failed for {self.pool_address}: {e}", "SOURCE_RPC_ERROR")

        reserve0, reserve1, _ = reserves

        if token.address.lower() == token0_address.lower():
            reserve_token = reserve0
            reserve_stable = reserve1
        else:
            reserve_token = reserve1
            reserve_stable = reserve0

        if reserve_token == 0:
            raise PricingError(f"Token reserve is zero in DEX pool {self.pool_address}", "ZERO_RESERVE")

        # Price of token = (amount of stable) / (amount of token)
        # We scale the stable reserve by the token's decimals to get the price of one whole token,
        # then scale that result to the stablecoin's decimals.
        # price_in_stable = reserve_stable * (10**token.decimals) / reserve_token
        # The answer should be in the stablecoin's raw units.
        # answer = (reserve_stable * 10**stable.decimals) / reserve_token
        # To avoid large intermediate numbers, we can do:
        # answer = reserve_stable * (10**stable.decimals) // reserve_token

        # Let's use a simpler and safer approach: calculate price of 1 atomic unit of token
        # price_atomic = reserve_stable / reserve_token
        # price_whole = price_atomic * 10**token.decimals
        # answer = price_whole * 10**stable.decimals
        # This can overflow. Let's use mul_div logic.
        
        # Price of one whole token, in units of the stablecoin.
        # (reserve_stable / reserve_token) is the price. We want it scaled to stablecoin's decimals.
        price_in_stable_units = (reserve_stable * (10 ** self.reference_stable.decimals)) // reserve_token

        return OracleObservation(
            source_id=self.id,
            source_kind=self.kind,
            answer=price_in_stable_units,
            answer_decimals=self.reference_stable.decimals,
            updated_at=context.current_timestamp,  # Spot price is always "now"
            observed_at_block=context.current_block,
            confidence_bps=8500,  # Spot price is lower confidence than a TWAP or Chainlink
        )