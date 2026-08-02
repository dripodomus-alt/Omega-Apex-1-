"""
Liquidation Executor Contract Interface
Integrates Python backend with deployed LiquidationExecutor smart contract
"""

import os
import json
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from web3 import Web3
from eth_abi import encode
from dotenv import load_dotenv
from executor_registry import (
    LIQUIDATION_EXECUTOR_ABI,
    UNDEPLOYED_MARKERS,
    get_active_executor_address,
    get_chain_config,
)

logger = logging.getLogger(__name__)
load_dotenv()


# ============================================================================
# CONSTANTS
# ============================================================================

# Polygon mainnet LiquidationExecutor address documented across the repo.
DEFAULT_LIQUIDATION_EXECUTOR_ADDRESS = get_active_executor_address("liquidation")


def get_configured_liquidation_executor_address() -> Optional[str]:
    """Return the configured liquidation executor address, if deployed."""
    contract_address = (
        os.getenv('LIQUIDATION_EXECUTOR_ADDRESS')
        or DEFAULT_LIQUIDATION_EXECUTOR_ADDRESS
        or ''
    ).strip()

    if contract_address in UNDEPLOYED_MARKERS:
        return None

    return Web3.to_checksum_address(contract_address)

# Protocol enum (must match Solidity)
class Protocol:
    QUICKSWAP_V3 = 0
    UNISWAP_V3 = 1
    SUSHISWAP = 2
    QUICKSWAP_V2 = 3


# Contract ABI is sourced from executor_registry.


# ============================================================================
# PAYLOAD BUILDER
# ============================================================================

@dataclass
class LiquidationPayload:
    """Liquidation execution payload"""
    collateral_asset: str
    debt_asset: str
    user: str
    debt_to_cover: int  # Wei
    min_profit_bps: int  # Basis points (50 = 0.5%)
    swap_protocol: int  # Protocol enum value
    swap_fee: int  # Fee tier (3000 = 0.3% for V3)
    max_slippage_bps: int  # Basis points (100 = 1%)


class LiquidationExecutorPayloadBuilder:
    """
    Build execution payloads for LiquidationExecutor contract
    """

    def __init__(self, w3: Web3):
        self.w3 = w3

    def build_payload_from_position(
        self,
        position: Dict,
        min_profit_bps: int = 50,  # 0.5% minimum profit
        swap_protocol: int = Protocol.QUICKSWAP_V3,
        swap_fee: int = 3000,  # 0.3%
        max_slippage_bps: int = 100  # 1%
    ) -> LiquidationPayload:
        """
        Convert LiquidatablePosition to execution payload

        Args:
            position: Dict from liquidation_hunter.py
            min_profit_bps: Minimum profit threshold
            swap_protocol: DEX to use for collateral swap
            swap_fee: V3 pool fee tier
            max_slippage_bps: Max slippage tolerance

        Returns:
            LiquidationPayload ready for contract execution
        """
        # Convert USD amounts to wei
        debt_decimals = self._get_token_decimals(position['debt_asset'])
        debt_to_cover = int(position['max_liquidatable_debt_usd'] * (10 ** debt_decimals))

        return LiquidationPayload(
            collateral_asset=Web3.to_checksum_address(position['collateral_asset']),
            debt_asset=Web3.to_checksum_address(position['debt_asset']),
            user=Web3.to_checksum_address(position['user_address']),
            debt_to_cover=debt_to_cover,
            min_profit_bps=min_profit_bps,
            swap_protocol=swap_protocol,
            swap_fee=swap_fee,
            max_slippage_bps=max_slippage_bps
        )

    def _get_token_decimals(self, token_address: str) -> int:
        """Get token decimals (simplified - extend with real ERC20 calls)"""
        # Common token decimals on Polygon
        decimals_map = {
            "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174": 6,   # USDC
            "0xc2132D05D31c914a87C6611C10748AEb04B58e8F": 6,   # USDT
            "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063": 18,  # DAI
            "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619": 18,  # WETH
            "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6": 8,   # WBTC
            "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270": 18,  # WMATIC
        }
        return decimals_map.get(Web3.to_checksum_address(token_address), 18)


# ============================================================================
# TRANSACTION BUILDER
# ============================================================================

class LiquidationExecutorTxBuilder:
    """Build transactions for LiquidationExecutor contract"""

    def __init__(self, w3: Web3, contract_address: Optional[str] = None):
        self.w3 = w3
        resolved_address = contract_address or get_configured_liquidation_executor_address()
        if not resolved_address:
            raise ValueError(
                "No liquidation executor contract address available. "
                "Set LIQUIDATION_EXECUTOR_ADDRESS or deploy the contract."
            )

        self.contract_address = Web3.to_checksum_address(resolved_address)
        self.contract = w3.eth.contract(address=self.contract_address, abi=LIQUIDATION_EXECUTOR_ABI)

    def build_liquidation_tx(
        self,
        payload: LiquidationPayload,
        from_address: str,
        gas_price_gwei: Optional[float] = None
    ) -> Dict:
        """
        Build transaction for liquidation execution

        Args:
            payload: LiquidationPayload
            from_address: Executor wallet (must be contract owner)
            gas_price_gwei: Gas price (auto if None)

        Returns:
            Transaction dict ready to sign and send
        """
        # Build transaction params tuple (must match Solidity struct)
        params = (
            payload.collateral_asset,
            payload.debt_asset,
            payload.user,
            payload.debt_to_cover,
            payload.min_profit_bps,
            payload.swap_protocol,
            payload.swap_fee,
            payload.max_slippage_bps
        )

        # Build transaction
        tx = self.contract.functions.executeLiquidation(params).build_transaction({
            'from': Web3.to_checksum_address(from_address),
            'gas': 800000,  # Conservative estimate
            'gasPrice': int(gas_price_gwei * 1e9) if gas_price_gwei else self.w3.eth.gas_price,
            'nonce': self.w3.eth.get_transaction_count(from_address),
            'chainId': get_chain_config('polygon').chain_id
        })

        return tx

    def estimate_gas(
        self,
        payload: LiquidationPayload,
        from_address: str
    ) -> int:
        """Estimate gas for liquidation execution"""
        params = (
            payload.collateral_asset,
            payload.debt_asset,
            payload.user,
            payload.debt_to_cover,
            payload.min_profit_bps,
            payload.swap_protocol,
            payload.swap_fee,
            payload.max_slippage_bps
        )

        try:
            gas = self.contract.functions.executeLiquidation(params).estimate_gas({
                'from': from_address
            })
            return gas
        except Exception as e:
            logger.error(f"Gas estimation failed: {e}")
            return 800000  # Default

    def get_contract_owner(self) -> str:
        """Get contract owner address"""
        return self.contract.functions.owner().call()

    def build_withdraw_tx(
        self,
        token: str,
        to: str,
        from_address: str,
        gas_price_gwei: Optional[float] = None
    ) -> Dict:
        """Build transaction to withdraw profits"""
        tx = self.contract.functions.withdrawAll(
            Web3.to_checksum_address(token),
            Web3.to_checksum_address(to)
        ).build_transaction({
            'from': Web3.to_checksum_address(from_address),
            'gas': 100000,
            'gasPrice': int(gas_price_gwei * 1e9) if gas_price_gwei else self.w3.eth.gas_price,
            'nonce': self.w3.eth.get_transaction_count(from_address),
            'chainId': get_chain_config('polygon').chain_id
        })

        return tx


# ============================================================================
# MAIN EXECUTOR CLASS
# ============================================================================

class LiquidationExecutor:
    """
    Main executor that wires liquidatable positions to deployed contract
    """

    def __init__(self, w3: Web3, contract_address: Optional[str] = None):
        resolved_address = contract_address or get_configured_liquidation_executor_address()
        if not resolved_address:
            raise ValueError(
                "No liquidation executor contract address available. "
                "Set LIQUIDATION_EXECUTOR_ADDRESS or deploy the contract."
            )

        self.w3 = w3
        self.payload_builder = LiquidationExecutorPayloadBuilder(w3)
        self.tx_builder = LiquidationExecutorTxBuilder(w3, resolved_address)

        logger.info(f"LiquidationExecutor initialized for contract: {resolved_address}")

    def build_execution_from_position(
        self,
        position: Dict,
        from_address: str,
        min_profit_bps: int = 50,
        dry_run: bool = True
    ) -> Dict:
        """
        Build complete execution transaction from liquidatable position

        Args:
            position: LiquidatablePosition dict from liquidation_hunter
            from_address: Executor wallet address (must be contract owner)
            min_profit_bps: Minimum profit threshold
            dry_run: If True, return payload only (no tx send)

        Returns:
            {
                'payload': LiquidationPayload dict,
                'tx': Transaction dict (if not dry_run),
                'estimated_gas': int,
                'status': str
            }
        """
        # Build payload
        payload = self.payload_builder.build_payload_from_position(
            position=position,
            min_profit_bps=min_profit_bps
        )

        # Estimate gas
        estimated_gas = self.tx_builder.estimate_gas(payload, from_address)

        result = {
            'payload': {
                'collateral_asset': payload.collateral_asset,
                'debt_asset': payload.debt_asset,
                'user': payload.user,
                'debt_to_cover': str(payload.debt_to_cover),
                'min_profit_bps': payload.min_profit_bps,
                'swap_protocol': payload.swap_protocol,
                'swap_fee': payload.swap_fee,
                'max_slippage_bps': payload.max_slippage_bps
            },
            'estimated_gas': estimated_gas,
            'estimated_gas_cost_usd': (estimated_gas * 60 * 0.5) / 1e9,  # 60 gwei, $0.50 MATIC
            'status': 'dry_run' if dry_run else 'ready'
        }

        if not dry_run:
            # Build transaction
            tx = self.tx_builder.build_liquidation_tx(payload, from_address)
            result['tx'] = tx

        return result


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_liquidation_executor(w3: Web3, contract_address: Optional[str] = None) -> LiquidationExecutor:
    """Get or create LiquidationExecutor instance"""
    return LiquidationExecutor(
        w3,
        contract_address or get_configured_liquidation_executor_address()
    )


def build_liquidation_payload(position: Dict, w3: Web3, contract_address: Optional[str] = None) -> Dict:
    """
    Helper: Build execution payload from liquidatable position

    Usage:
        positions = hunter.scan_for_liquidations()
        payload = build_liquidation_payload(positions[0], w3)
    """
    executor = get_liquidation_executor(w3, contract_address)
    return executor.build_execution_from_position(
        position=position,
        from_address=os.getenv('EXECUTOR_WALLET', '0x0000000000000000000000000000000000000000'),
        min_profit_bps=50,  # 0.5% minimum profit
        dry_run=True
    )
