"""
APEX_OMEGA Contract Integration
Interface to deployed UltimateArbitrageExecutor contracts (C1 & C2)
"""

import os
import json
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from web3 import Web3
from eth_abi import encode, decode
import hashlib
import logging
from executor_registry import get_active_executor_address, get_executor_abi

logger = logging.getLogger(__name__)

# Protocol Constants (must match contract)
class Protocol(IntEnum):
    UNISWAP_V2 = 1
    UNISWAP_V3 = 2
    QUICKSWAP_V3 = 3
    SUSHISWAP = 4
    ALGEBRA = 5
    CURVE = 6
    BALANCER = 7

class VaultMode(IntEnum):
    BALANCER_V2 = 0
    BALANCER_V3 = 1
    AAVE_V3 = 2
    CURVE = 3

# Route version
ROUTE_VERSION_1 = 1
STEP_OPTIONAL_FLAG = 0x80


@dataclass
class RouteStep:
    """Single step in arbitrage route"""
    protocol: int
    target: str
    approve_token: str
    call_value: int = 0
    min_amount_in: int = 0
    min_amount_out: int = 0
    fee_bps: int = 30
    data: bytes = field(default_factory=bytes)
    optional: bool = False
    
    def encode(self) -> Tuple:
        """Encode as tuple for ABI encoding"""
        protocol = self.protocol | (STEP_OPTIONAL_FLAG if self.optional else 0)
        return (
            protocol,
            Web3.to_checksum_address(self.target),
            Web3.to_checksum_address(self.approve_token) if self.approve_token else '0x0000000000000000000000000000000000000000',
            self.call_value,
            self.min_amount_in,
            self.min_amount_out,
            self.fee_bps,
            self.data
        )


@dataclass
class RouteEnvelope:
    """Complete route definition"""
    version: int = ROUTE_VERSION_1
    profit_token: str = '0x0000000000000000000000000000000000000000'
    gas_reserve_asset: int = 0
    dex_fee_reserve_asset: int = 0
    steps: List[RouteStep] = field(default_factory=list)
    
    def encode(self) -> bytes:
        """Encode route envelope for contract"""
        steps_encoded = [step.encode() for step in self.steps]
        
        # RouteEnvelope struct: (uint8, address, uint256, uint256, RouteStep[])
        # RouteStep struct: (uint8, address, address, uint256, uint256, uint256, uint16, bytes)
        encoded = encode(
            ['(uint8,address,uint256,uint256,(uint8,address,address,uint256,uint256,uint256,uint16,bytes)[])'],
            [(
                self.version,
                Web3.to_checksum_address(self.profit_token),
                self.gas_reserve_asset,
                self.dex_fee_reserve_asset,
                steps_encoded
            )]
        )
        return encoded


class MerkleTree:
    """Simple Merkle Tree for route authorization"""
    
    @staticmethod
    def hash_leaf(data: bytes) -> bytes:
        """Hash a leaf node"""
        return Web3.keccak(data)
    
    @staticmethod
    def hash_pair(a: bytes, b: bytes) -> bytes:
        """Hash two nodes together (sorted)"""
        if a < b:
            return Web3.keccak(a + b)
        return Web3.keccak(b + a)
    
    @staticmethod
    def build_tree(leaves: List[bytes]) -> Tuple[bytes, List[List[bytes]]]:
        """Build Merkle tree, return root and layers"""
        if not leaves:
            return b'\x00' * 32, []
        
        layers = [leaves]
        while len(layers[-1]) > 1:
            layer = layers[-1]
            new_layer = []
            for i in range(0, len(layer), 2):
                if i + 1 < len(layer):
                    new_layer.append(MerkleTree.hash_pair(layer[i], layer[i+1]))
                else:
                    new_layer.append(layer[i])
            layers.append(new_layer)
        
        return layers[-1][0], layers
    
    @staticmethod
    def get_proof(layers: List[List[bytes]], index: int) -> List[bytes]:
        """Get proof for leaf at index"""
        proof = []
        for layer in layers[:-1]:
            sibling_idx = index ^ 1
            if sibling_idx < len(layer):
                proof.append(layer[sibling_idx])
            index //= 2
        return proof


class ContractInterface:
    """Interface to deployed UltimateArbitrageExecutor contracts"""
    
    # Minimal ABI for execution
    EXECUTOR_ABI = get_executor_abi("ultimate_arbitrage")
    
    def __init__(self, w3: Web3, contract_address: str):
        self.w3 = w3
        self.address = Web3.to_checksum_address(contract_address)
        self.contract = w3.eth.contract(address=self.address, abi=self.EXECUTOR_ABI)
    
    def get_owner(self) -> str:
        """Get contract owner"""
        return self.contract.functions.owner().call()
    
    def get_merkle_root(self) -> bytes:
        """Get current merkle root"""
        return self.contract.functions.merkleRoot().call()
    
    def get_vault_mode(self) -> int:
        """Get global vault mode"""
        return self.contract.functions.globalVaultMode().call()
    
    def build_execute_tx(
        self,
        asset: str,
        amount: int,
        min_profit: int,
        proof: List[bytes],
        params: bytes,
        from_address: str,
        gas_price_gwei: float = 60,
        use_c1: bool = True  # True for initAaveFlash, False for executeArbitrage
    ) -> Dict[str, Any]:
        """Build execution transaction"""
        func_name = 'initAaveFlash' if use_c1 else 'executeArbitrage'
        func = getattr(self.contract.functions, func_name)
        
        tx = func(
            Web3.to_checksum_address(asset),
            amount,
            min_profit,
            proof,
            params
        ).build_transaction({
            'from': Web3.to_checksum_address(from_address),
            'gas': 800000,
            'gasPrice': int(gas_price_gwei * 1e9),
            'nonce': self.w3.eth.get_transaction_count(from_address)
        })
        
        return tx
    
    def estimate_gas(
        self,
        asset: str,
        amount: int,
        min_profit: int,
        proof: List[bytes],
        params: bytes,
        from_address: str,
        use_c1: bool = True
    ) -> int:
        """Estimate gas for execution"""
        func_name = 'initAaveFlash' if use_c1 else 'executeArbitrage'
        func = getattr(self.contract.functions, func_name)
        
        try:
            gas = func(
                Web3.to_checksum_address(asset),
                amount,
                min_profit,
                proof,
                params
            ).estimate_gas({'from': from_address})
            return gas
        except Exception as e:
            logger.error(f"Gas estimation failed: {e}")
            return 800000  # Default


class RouteBuilder:
    """Helper to build arbitrage routes for the contracts"""
    
    # Common token addresses on Polygon
    TOKENS = {
        'USDC': '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174',
        'USDT': '0xc2132D05D31c914a87C6611C10748AEb04B58e8F',
        'WMATIC': '0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270',
        'WETH': '0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619',
        'WBTC': '0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6',
        'DAI': '0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063',
    }
    
    # DEX Router addresses on Polygon
    ROUTERS = {
        'UNISWAP_V3': '0xE592427A0AEce92De3Edee1F18E0157C05861564',
        'QUICKSWAP_V3': '0xf5b509bB0909a69B1c207E495f687a596C168E12',
        'SUSHISWAP': '0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506',
        'QUICKSWAP_V2': '0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff',
    }
    
    @staticmethod
    def encode_uniswap_v3_swap(
        token_in: str,
        token_out: str,
        fee: int,
        recipient: str,
        amount_in: int,
        amount_out_min: int,
        deadline: int
    ) -> bytes:
        """Encode UniswapV3 exactInputSingle call"""
        # exactInputSingle((address,address,uint24,address,uint256,uint256,uint256,uint160))
        params_tuple = (
            Web3.to_checksum_address(token_in),
            Web3.to_checksum_address(token_out),
            fee,
            Web3.to_checksum_address(recipient),
            deadline,
            amount_in,
            amount_out_min,
            0  # sqrtPriceLimitX96 = 0 means no limit
        )
        
        # Function selector for exactInputSingle
        selector = Web3.keccak(text='exactInputSingle((address,address,uint24,address,uint256,uint256,uint256,uint160))')[:4]
        
        encoded_params = encode(
            ['(address,address,uint24,address,uint256,uint256,uint256,uint160)'],
            [params_tuple]
        )
        
        return selector + encoded_params
    
    @staticmethod
    def encode_uniswap_v2_swap(
        amount_in: int,
        amount_out_min: int,
        path: List[str],
        recipient: str,
        deadline: int
    ) -> bytes:
        """Encode UniswapV2 swapExactTokensForTokens call"""
        # swapExactTokensForTokens(uint256,uint256,address[],address,uint256)
        selector = Web3.keccak(text='swapExactTokensForTokens(uint256,uint256,address[],address,uint256)')[:4]
        
        path_checksum = [Web3.to_checksum_address(p) for p in path]
        
        encoded_params = encode(
            ['uint256', 'uint256', 'address[]', 'address', 'uint256'],
            [amount_in, amount_out_min, path_checksum, Web3.to_checksum_address(recipient), deadline]
        )
        
        return selector + encoded_params
    
    @staticmethod
    def build_simple_arb_route(
        token_a: str,
        token_b: str,
        amount: int,
        executor_address: str,
        buy_router: str,
        sell_router: str,
        buy_protocol: int,
        sell_protocol: int,
        fee_tier: int = 3000,
        slippage_bps: int = 50
    ) -> RouteEnvelope:
        """Build a simple A->B->A arbitrage route"""
        import time
        deadline = int(time.time()) + 300
        
        min_amount_out = amount * (10000 - slippage_bps) // 10000
        
        steps = []
        
        # Step 1: Buy token_b with token_a
        if buy_protocol == Protocol.UNISWAP_V3:
            buy_data = RouteBuilder.encode_uniswap_v3_swap(
                token_in=token_a,
                token_out=token_b,
                fee=fee_tier,
                recipient=executor_address,
                amount_in=amount,
                amount_out_min=0,  # Will use minAmountOut in step
                deadline=deadline
            )
        else:
            buy_data = RouteBuilder.encode_uniswap_v2_swap(
                amount_in=amount,
                amount_out_min=0,
                path=[token_a, token_b],
                recipient=executor_address,
                deadline=deadline
            )
        
        steps.append(RouteStep(
            protocol=buy_protocol,
            target=buy_router,
            approve_token=token_a,
            min_amount_in=amount,
            min_amount_out=0,
            fee_bps=30,
            data=buy_data
        ))
        
        # Step 2: Sell token_b back to token_a
        if sell_protocol == Protocol.UNISWAP_V3:
            sell_data = RouteBuilder.encode_uniswap_v3_swap(
                token_in=token_b,
                token_out=token_a,
                fee=fee_tier,
                recipient=executor_address,
                amount_in=0,  # Will use cascaded amount
                amount_out_min=min_amount_out,
                deadline=deadline
            )
        else:
            sell_data = RouteBuilder.encode_uniswap_v2_swap(
                amount_in=0,
                amount_out_min=min_amount_out,
                path=[token_b, token_a],
                recipient=executor_address,
                deadline=deadline
            )
        
        steps.append(RouteStep(
            protocol=sell_protocol,
            target=sell_router,
            approve_token=token_b,
            min_amount_in=0,
            min_amount_out=min_amount_out,
            fee_bps=30,
            data=sell_data
        ))
        
        return RouteEnvelope(
            version=ROUTE_VERSION_1,
            profit_token=token_a,
            gas_reserve_asset=int(0.01 * 1e6),  # 0.01 USDC for gas
            dex_fee_reserve_asset=int(0.005 * 1e6),  # 0.005 USDC for DEX fees
            steps=steps
        )


class ApexContractExecutor:
    """
    Main executor that integrates with deployed C1/C2 contracts
    """
    
    def __init__(
        self,
        w3: Web3,
        c1_address: Optional[str] = None,
        c2_address: Optional[str] = None,
        private_key: Optional[str] = None
    ):
        self.w3 = w3
        c1_address = c1_address or get_active_executor_address("institutional_arbitrage")
        c2_address = c2_address or get_active_executor_address("ultimate_arbitrage")
        self.c1 = ContractInterface(w3, c1_address) if c1_address else None
        self.c2 = ContractInterface(w3, c2_address) if c2_address else None
        self.wallet = None
        
        if private_key:
            self.wallet = w3.eth.account.from_key(private_key)
            logger.info(f"Wallet: {self.wallet.address}")
        
        # Merkle tree for route authorization
        self.merkle_leaves: List[bytes] = []
        self.merkle_root: bytes = b'\x00' * 32
        self.merkle_layers: List[List[bytes]] = []
    
    def add_authorized_route(self, params: bytes) -> int:
        """Add a route to the Merkle tree, return index"""
        leaf = Web3.keccak(params)
        self.merkle_leaves.append(leaf)
        self.merkle_root, self.merkle_layers = MerkleTree.build_tree(self.merkle_leaves)
        return len(self.merkle_leaves) - 1
    
    def get_proof_for_route(self, index: int) -> List[bytes]:
        """Get Merkle proof for route at index"""
        return MerkleTree.get_proof(self.merkle_layers, index)
    
    def update_contract_merkle_root(self, use_c1: bool = True) -> Optional[str]:
        """Update the Merkle root on the contract"""
        if not self.wallet:
            raise ValueError("No wallet configured")
        
        contract = self.c1 if use_c1 else self.c2
        if not contract:
            raise ValueError("Contract not configured")
        
        # Build transaction
        try:
            # Try updateRoot first (C1 style)
            tx = contract.contract.functions.updateRoot(self.merkle_root).build_transaction({
                'from': self.wallet.address,
                'gas': 100000,
                'gasPrice': int(60 * 1e9),
                'nonce': self.w3.eth.get_transaction_count(self.wallet.address)
            })
        except Exception:
            # Try updateMerkleRoot (C2 style)
            tx = contract.contract.functions.updateMerkleRoot(self.merkle_root).build_transaction({
                'from': self.wallet.address,
                'gas': 100000,
                'gasPrice': int(60 * 1e9),
                'nonce': self.w3.eth.get_transaction_count(self.wallet.address)
            })
        
        # Sign and send
        signed = self.w3.eth.account.sign_transaction(tx, self.wallet.key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        
        logger.info(f"Merkle root update tx: {tx_hash.hex()}")
        return tx_hash.hex()
    
    def execute_arbitrage(
        self,
        asset: str,
        amount: int,
        min_profit: int,
        route: RouteEnvelope,
        use_c1: bool = True,
        dry_run: bool = True
    ) -> Dict[str, Any]:
        """Execute an arbitrage through the deployed contract"""
        
        # Encode route
        params = route.encode()
        
        # Add to Merkle tree and get proof
        route_index = self.add_authorized_route(params)
        proof = self.get_proof_for_route(route_index)
        
        contract = self.c1 if use_c1 else self.c2
        if not contract:
            raise ValueError("Contract not configured")
        
        if dry_run:
            logger.info("[DRY RUN] Would execute arbitrage:")
            logger.info("  Asset: %s", asset)
            logger.info("  Amount: %s", amount)
            logger.info("  Min Profit: %s", min_profit)
            logger.info("  Steps: %s", len(route.steps))
            logger.info(f"  Merkle Root: {self.merkle_root.hex()}")
            return {
                'status': 'dry_run',
                'params_hash': Web3.keccak(params).hex(),
                'merkle_root': self.merkle_root.hex(),
                'proof_length': len(proof)
            }
        
        if not self.wallet:
            raise ValueError("No wallet configured for live execution")
        
        # First update Merkle root on contract
        logger.info("Updating Merkle root on contract...")
        # root_tx = self.update_contract_merkle_root(use_c1)
        
        # Build and send execution transaction
        tx = contract.build_execute_tx(
            asset=asset,
            amount=amount,
            min_profit=min_profit,
            proof=proof,
            params=params,
            from_address=self.wallet.address,
            use_c1=use_c1
        )
        
        signed = self.w3.eth.account.sign_transaction(tx, self.wallet.key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        
        logger.info(f"Execution tx: {tx_hash.hex()}")
        
        # Wait for receipt
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        
        return {
            'status': 'executed' if receipt['status'] == 1 else 'failed',
            'tx_hash': tx_hash.hex(),
            'gas_used': receipt['gasUsed'],
            'block': receipt['blockNumber']
        }
