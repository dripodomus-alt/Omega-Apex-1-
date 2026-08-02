"""
InstitutionalExecutor Integration
Wires arbitrage spreads to deployed C1 contract for flash loan execution
Contract address resolved by executor_registry (Polygon)
"""

import os
import time
import logging
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from web3 import Web3
from eth_abi import encode
from dotenv import load_dotenv
from executor_registry import (
    DEX_ROUTERS,
    get_active_executor_address,
    get_chain_config,
    get_executor_abi,
)

try:
    from .protocol_adapters import (
        POLYGON_EXECUTOR_ADDRESS,
        POLYGON_ROUTERS,
        SwapEncodingContext,
        encode_swap,
    )
except ImportError:  # Support direct script execution from backend/.
    from protocol_adapters import (
        POLYGON_EXECUTOR_ADDRESS,
        POLYGON_ROUTERS,
        SwapEncodingContext,
        encode_swap,
    )

logger = logging.getLogger(__name__)
load_dotenv()


# ============================================================================
# CONSTANTS
# ============================================================================

# Deployed InstitutionalExecutor contract (single source of truth: executor_registry)
C1_ADDRESS = get_active_executor_address("institutional_arbitrage") or "0x0000000000000000000000000000000000000000"

# Flash loan providers (built into C1)
AAVE_POOL = "0x794a61358D6845594F94dc1DB02A252b5b4814aD"
BALANCER_VAULT = POLYGON_ROUTERS["balancer_vault"]

# DEX Routers on Polygon
ROUTERS = dict(DEX_ROUTERS["polygon"])

# Protocol types
PROTOCOL_V2 = 2
PROTOCOL_V3 = 3

# C1 Contract ABI (minimal - only what we need)
C1_ABI = get_executor_abi("institutional_arbitrage")

# ============================================================================
# SWAP CALLDATA ENCODERS
# ============================================================================

class SwapEncoder:
    """Encode swap calldata for different DEX protocols"""
    
    @staticmethod
    def encode_v2_swap(
        router: str,
        amount_in: int,
        amount_out_min: int,
        path: List[str],
        recipient: str,
        deadline: int
    ) -> bytes:
        """
        Encode UniswapV2/QuickSwap/SushiSwap swap
        
        Function: swapExactTokensForTokens(uint256,uint256,address[],address,uint256)
        """
        # Function selector for swapExactTokensForTokens
        selector = Web3.keccak(text='swapExactTokensForTokens(uint256,uint256,address[],address,uint256)')[:4]
        
        # Encode parameters
        path_checksum = [Web3.to_checksum_address(p) for p in path]
        encoded_params = encode(
            ['uint256', 'uint256', 'address[]', 'address', 'uint256'],
            [amount_in, amount_out_min, path_checksum, Web3.to_checksum_address(recipient), deadline]
        )
        
        return selector + encoded_params
    
    @staticmethod
    def encode_v3_swap(
        router: str,
        token_in: str,
        token_out: str,
        fee: int,
        recipient: str,
        amount_in: int,
        amount_out_min: int,
        deadline: int
    ) -> bytes:
        """
        Encode UniswapV3/QuickSwapV3 swap
        
        Function: exactInputSingle((address,address,uint24,address,uint256,uint256,uint256,uint160))
        """
        # Function selector for exactInputSingle
        selector = Web3.keccak(text='exactInputSingle((address,address,uint24,address,uint256,uint256,uint256,uint160))')[:4]
        
        # ExactInputSingleParams struct
        params_tuple = (
            Web3.to_checksum_address(token_in),
            Web3.to_checksum_address(token_out),
            fee,
            Web3.to_checksum_address(recipient),
            deadline,
            amount_in,
            amount_out_min,
            0  # sqrtPriceLimitX96 = 0 (no limit)
        )
        
        encoded_params = encode(
            ['(address,address,uint24,address,uint256,uint256,uint256,uint160)'],
            [params_tuple]
        )
        
        return selector + encoded_params


# ============================================================================
# PAYLOAD BUILDER
# ============================================================================

@dataclass
class ExecutionPayload:
    """Complete execution payload for C1 contract"""
    flash_provider: str  # 'aave' or 'balancer'
    asset: str  # Token to borrow (flash loan token)
    amount: int  # Amount to borrow (in wei)
    min_profit: int  # Minimum profit required (in wei)
    deadline: int  # Transaction deadline timestamp
    targets: List[str]  # Router addresses for each swap
    calldatas: List[bytes]  # Encoded swap calls
    encoded_params: bytes  # ABI-encoded (targets, calldatas)


class InstitutionalExecutorPayloadBuilder:
    """
    Converts SpreadOpportunity to executable payload for InstitutionalExecutor
    """
    
    def __init__(self, w3: Web3):
        self.w3 = w3
        self.encoder = SwapEncoder()
    
    def get_router_for_pool(self, pool_address: str, dex_name: str, protocol: int) -> str:
        """Get router address for a known DEX/protocol pair, fail-closed otherwise."""
        dex_lower = dex_name.lower()
        if 'uniswap' in dex_lower and protocol == PROTOCOL_V3:
            return ROUTERS['uniswap_v3']
        if 'quickswap' in dex_lower and protocol == PROTOCOL_V2:
            return ROUTERS['quickswap_v2']
        if ('quickswap' in dex_lower or 'algebra' in dex_lower) and protocol == PROTOCOL_V3:
            return ROUTERS['quickswap_v3']
        if 'sushi' in dex_lower and protocol == PROTOCOL_V2:
            return ROUTERS['sushiswap']
        raise ValueError(f"Unsupported DEX/protocol combination dex={dex_name!r} protocol={protocol!r}")

    @staticmethod
    def _pool_meta(leg: Dict) -> Dict:
        """Collect pool-derived metadata used by protocol adapters."""
        meta = dict(leg.get('pool_meta') or leg.get('poolMeta') or {})
        for key in ('fee', 'fee_tier', 'feeTier', 'fee_bps', 'tick_spacing', 'tickSpacing', 'pool_id', 'tokens', 'i', 'j'):
            if key in leg and key not in meta:
                meta[key] = leg[key]
        return meta

    def _encode_leg(
        self,
        leg: Dict,
        amount_in: int,
        amount_out_min: int,
        deadline: int,
    ):
        encoded = encode_swap(SwapEncodingContext(
            chain_id=137,
            dex=leg.get('dex', ''),
            protocol=leg.get('protocol'),
            pool=leg.get('pool', ''),
            token_in=leg['tokenIn'],
            token_out=leg['tokenOut'],
            amount_in=amount_in,
            amount_out_min=amount_out_min,
            recipient=C1_ADDRESS,
            deadline=deadline,
            pool_meta=self._pool_meta(leg),
        ))
        return encoded.router, encoded.calldata
    
    @staticmethod
    def _native_amount(value, context: str) -> int:
        """Parse a token-native integer amount and fail closed on invalid input."""
        if value is None:
            raise ValueError(f"Missing native amount for {context}")

        try:
            amount = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid native amount for {context}: {value!r}") from exc

        if amount < 0:
            raise ValueError(f"Native amount for {context} must be non-negative")
        return amount

    @staticmethod
    def _decimal(value, context: str) -> Decimal:
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid decimal value for {context}: {value!r}") from exc
        return amount

    def _usd_to_native_units(
        self,
        usd_value,
        price_usd,
        decimals,
        context: str,
    ) -> int:
        """Convert a USD notional to token-native integer units using explicit price metadata."""
        usd = self._decimal(usd_value, f"{context} USD value")
        price = self._decimal(price_usd, f"{context} token USD price")
        try:
            token_decimals = int(decimals)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid token decimals for {context}: {decimals!r}") from exc

        if usd < 0:
            raise ValueError(f"USD value for {context} must be non-negative")
        if price <= 0:
            raise ValueError(f"Token USD price for {context} must be positive")
        if token_decimals < 0:
            raise ValueError(f"Token decimals for {context} must be non-negative")

        return int((usd / price) * (Decimal(10) ** token_decimals))

    def _amount_from_native_or_usd(
        self,
        data: Dict,
        native_key: str,
        usd_key: str,
        price_key: str,
        decimals_key: str,
        context: str,
    ) -> int:
        """
        Return a token-native amount, preferring explicit native values.

        USD fallback is allowed only when both token price and decimals metadata are present;
        this intentionally fails closed for old payloads that contain USD notionals only.
        """
        if native_key in data and data[native_key] is not None:
            return self._native_amount(data[native_key], context)

        missing = [key for key in (usd_key, price_key, decimals_key) if key not in data or data[key] is None]
        if missing:
            raise ValueError(
                f"Cannot derive native amount for {context}; missing {', '.join(missing)}"
            )

        return self._usd_to_native_units(
            data[usd_key],
            data[price_key],
            data[decimals_key],
            context,
        )

    @staticmethod
    def _apply_slippage(amount: int, slippage_bps: int) -> int:
        if not 0 <= slippage_bps <= 10000:
            raise ValueError("slippage_bps must be between 0 and 10000")
        return int(Decimal(amount) * Decimal(10000 - slippage_bps) / Decimal(10000))

    def build_payload_from_spread(
        self,
        spread: Dict,
        use_balancer: bool = True,
        slippage_bps: int = 50,  # 0.5% slippage tolerance
        deadline_seconds: int = 300  # 5 minutes
    ) -> ExecutionPayload:
        """
        Convert SpreadOpportunity to ExecutionPayload
        
        Args:
            spread: SpreadOpportunity dict from arbitrage_engine
            use_balancer: Use Balancer (FREE) vs Aave (0.05% fee)
            slippage_bps: Slippage tolerance in basis points
            deadline_seconds: Seconds until deadline
            
        Returns:
            ExecutionPayload ready for contract execution
        """
        flash_loan = spread['flashLoan']
        leg1 = flash_loan['leg1']
        leg2 = flash_loan['leg2']

        # Determine flash loan asset (token being borrowed).
        # For this 2-leg arbitrage, the borrowed token is leg1 tokenIn and the
        # profit token is leg2 tokenOut (the round-trip returns to the borrow asset).
        asset = Web3.to_checksum_address(leg1['tokenIn'])

        # Prefer explicit native flash-loan amount, then leg1's native input amount,
        # then derive from loanAmountUsd using the borrowed token's price/decimals.
        if 'loanAmount' in flash_loan and flash_loan['loanAmount'] is not None:
            amount = self._native_amount(flash_loan['loanAmount'], 'flash loan amount')
        elif 'amountIn' in leg1 and leg1['amountIn'] is not None:
            amount = self._native_amount(leg1['amountIn'], 'leg1 amountIn')
        else:
            loan_amount_data = {
                **flash_loan,
                'loanTokenPriceUsd': flash_loan.get('loanTokenPriceUsd', leg1.get('tokenInPriceUsd')),
                'loanTokenDecimals': flash_loan.get('loanTokenDecimals', leg1.get('tokenInDecimals')),
            }
            amount = self._amount_from_native_or_usd(
                loan_amount_data,
                native_key='loanAmount',
                usd_key='loanAmountUsd',
                price_key='loanTokenPriceUsd',
                decimals_key='loanTokenDecimals',
                context='flash loan amount',
            )

        # Minimum profit is denominated in the token received at the end of leg2.
        # Native netProfitAmount wins; otherwise derive netProfitUsd from leg2 tokenOut metadata.
        if 'netProfitAmount' in flash_loan and flash_loan['netProfitAmount'] is not None:
            min_profit = self._native_amount(flash_loan['netProfitAmount'], 'net profit amount')
        else:
            profit_amount_data = {
                **flash_loan,
                'profitTokenPriceUsd': flash_loan.get('profitTokenPriceUsd', leg2.get('tokenOutPriceUsd')),
                'profitTokenDecimals': flash_loan.get('profitTokenDecimals', leg2.get('tokenOutDecimals')),
            }
            min_profit = self._amount_from_native_or_usd(
                profit_amount_data,
                native_key='netProfitAmount',
                usd_key='netProfitUsd',
                price_key='profitTokenPriceUsd',
                decimals_key='profitTokenDecimals',
                context='net profit amount',
            )

        # Deadline
        deadline = int(time.time()) + deadline_seconds

        # Build swap calldata for each leg
        targets = []
        calldatas = []

        # LEG 1: Buy on cheaper pool
        router1 = self.get_router_for_pool(leg1['pool'], leg1['dex'], leg1['protocol'])
        targets.append(router1)

        leg1_expected_out = self._amount_from_native_or_usd(
            leg1,
            native_key='amountOut',
            usd_key='amountOutUsd',
            price_key='tokenOutPriceUsd',
            decimals_key='tokenOutDecimals',
            context='leg1 amountOut',
        )
        leg1_amount_out_min = self._apply_slippage(leg1_expected_out, slippage_bps)

        if leg1['protocol'] == PROTOCOL_V2:
            path = [
                Web3.to_checksum_address(leg1['tokenIn']),
                Web3.to_checksum_address(leg1['tokenOut'])
            ]
            calldata1 = self.encoder.encode_v2_swap(
                router=router1,
                amount_in=amount,
                amount_out_min=leg1_amount_out_min,
                path=path,
                recipient=C1_ADDRESS,
                deadline=deadline
            )
        else:
            fee = leg1.get('fee', 3000)
            calldata1 = self.encoder.encode_v3_swap(
                router=router1,
                token_in=leg1['tokenIn'],
                token_out=leg1['tokenOut'],
                fee=fee,
                recipient=C1_ADDRESS,
                amount_in=amount,
                amount_out_min=leg1_amount_out_min,
                deadline=deadline
            )

        calldatas.append(calldata1)

        # LEG 2: Sell on expensive pool. The input is the actual expected native
        # output from leg1, not a separate USD-derived amount for leg2.
        router2 = self.get_router_for_pool(leg2['pool'], leg2['dex'], leg2['protocol'])
        targets.append(router2)
        leg2_amount_in = leg1_expected_out

        leg2_expected_out = self._amount_from_native_or_usd(
            leg2,
            native_key='amountOut',
            usd_key='amountOutUsd',
            price_key='tokenOutPriceUsd',
            decimals_key='tokenOutDecimals',
            context='leg2 amountOut',
        )
        leg2_amount_out_min = self._apply_slippage(leg2_expected_out, slippage_bps)

        if leg2['protocol'] == PROTOCOL_V2:
            path = [
                Web3.to_checksum_address(leg2['tokenIn']),
                Web3.to_checksum_address(leg2['tokenOut'])
            ]
            calldata2 = self.encoder.encode_v2_swap(
                router=router2,
                amount_in=leg2_amount_in,
                amount_out_min=leg2_amount_out_min,
                path=path,
                recipient=C1_ADDRESS,
                deadline=deadline
            )
        else:
            fee = leg2.get('fee', 3000)
            calldata2 = self.encoder.encode_v3_swap(
                router=router2,
                token_in=leg2['tokenIn'],
                token_out=leg2['tokenOut'],
                fee=fee,
                recipient=C1_ADDRESS,
                amount_in=leg2_amount_in,
                amount_out_min=leg2_amount_out_min,
                deadline=deadline
            )
        
        calldatas.append(calldata2)
        
        # Encode params for C1 contract
        # params = abi.encode((address[] targets, bytes[] calldatas))
        encoded_params = encode(
            ['address[]', 'bytes[]'],
            [targets, calldatas]
        )
        
        # Select flash loan provider
        flash_provider = 'balancer' if use_balancer else 'aave'
        
        return ExecutionPayload(
            flash_provider=flash_provider,
            asset=asset,
            amount=amount,
            min_profit=min_profit,
            deadline=deadline,
            targets=targets,
            calldatas=calldatas,
            encoded_params=encoded_params
        )

# ============================================================================
# TRANSACTION BUILDER
# ============================================================================

class InstitutionalExecutorTxBuilder:
    """Build transactions for InstitutionalExecutor contract"""
    
    def __init__(self, w3: Web3, contract_address: str = C1_ADDRESS):
        self.w3 = w3
        self.contract_address = Web3.to_checksum_address(contract_address)
        self.contract = w3.eth.contract(address=self.contract_address, abi=C1_ABI)
    
    def build_flash_tx(
        self,
        payload: ExecutionPayload,
        from_address: str,
        gas_price_gwei: Optional[float] = None
    ) -> Dict:
        """
        Build transaction for flash loan execution
        
        Args:
            payload: ExecutionPayload from payload builder
            from_address: Executor wallet address
            gas_price_gwei: Gas price (auto if None)
            
        Returns:
            Transaction dict ready to sign and send
        """
        # Select function based on provider
        if payload.flash_provider == 'balancer':
            func = self.contract.functions.initBalancerFlash
        else:
            func = self.contract.functions.initAaveFlash
        
        # Build transaction
        tx = func(
            payload.asset,
            payload.amount,
            payload.min_profit,
            payload.deadline,
            payload.encoded_params
        ).build_transaction({
            'from': Web3.to_checksum_address(from_address),
            'gas': 800000,  # Conservative estimate
            'gasPrice': int(gas_price_gwei * 1e9) if gas_price_gwei else self.w3.eth.gas_price,
            'nonce': self.w3.eth.get_transaction_count(from_address),
            'chainId': get_chain_config('polygon').chain_id
        })
        
        return tx

    def simulate_transaction(self, tx: Dict) -> bytes:
        """Run a required pre-broadcast eth_call against the exact transaction dict."""
        call_tx = dict(tx)
        call_tx.pop('nonce', None)
        return self.w3.eth.call(call_tx)
    
    def estimate_gas(
        self,
        payload: ExecutionPayload,
        from_address: str
    ) -> int:
        """Estimate gas for execution"""
        if payload.flash_provider == 'balancer':
            func = self.contract.functions.initBalancerFlash
        else:
            func = self.contract.functions.initAaveFlash
        
        try:
            gas = func(
                payload.asset,
                payload.amount,
                payload.min_profit,
                payload.deadline,
                payload.encoded_params
            ).estimate_gas({'from': from_address})
            return gas
        except Exception as e:
            logger.error(f"Gas estimation failed: {e}")
            return 800000  # Default
    
    def get_contract_owner(self) -> str:
        """Get contract owner address"""
        return self.contract.functions.owner().call()


# ============================================================================
# MAIN EXECUTOR CLASS
# ============================================================================

class InstitutionalExecutor:
    """
    Main executor that wires arbitrage spreads to C1 contract
    """
    
    def __init__(self, w3: Web3, contract_address: str = C1_ADDRESS):
        self.w3 = w3
        self.payload_builder = InstitutionalExecutorPayloadBuilder(w3)
        self.tx_builder = InstitutionalExecutorTxBuilder(w3, contract_address)
        
        logger.info(f"InstitutionalExecutor initialized for contract: {contract_address}")
    
    def build_execution_from_spread(
        self,
        spread: Dict,
        from_address: str,
        use_balancer: bool = True,
        dry_run: bool = True
    ) -> Dict:
        """
        Build complete execution transaction from spread opportunity
        
        Args:
            spread: SpreadOpportunity dict
            from_address: Executor wallet address
            use_balancer: Use Balancer (FREE) vs Aave (0.05%)
            dry_run: If True, return payload only (no tx send)
            
        Returns:
            {
                'payload': ExecutionPayload,
                'tx': Transaction dict (if not dry_run),
                'estimated_gas': int,
                'status': str
            }
        """
        # Build payload
        payload = self.payload_builder.build_payload_from_spread(
            spread=spread,
            use_balancer=use_balancer
        )
        
        # Estimate gas
        estimated_gas = self.tx_builder.estimate_gas(payload, from_address)
        
        result = {
            'payload': {
                'flash_provider': payload.flash_provider,
                'asset': payload.asset,
                'amount': str(payload.amount),
                'min_profit': str(payload.min_profit),
                'deadline': payload.deadline,
                'targets': payload.targets,
                'encoded_params': '0x' + payload.encoded_params.hex()
            },
            'estimated_gas': estimated_gas,
            'status': 'dry_run' if dry_run else 'ready'
        }
        
        if not dry_run:
            # Build and simulate the exact transaction before it can be broadcast.
            tx = self.tx_builder.build_flash_tx(payload, from_address)
            simulation_result = self.tx_builder.simulate_transaction(tx)
            result['tx'] = tx
            result['simulation'] = '0x' + simulation_result.hex()
            result['status'] = 'ready_after_eth_call'
        
        return result


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_institutional_executor(w3: Web3) -> InstitutionalExecutor:
    """Get or create InstitutionalExecutor instance"""
    return InstitutionalExecutor(w3, C1_ADDRESS)


def build_execution_payload(spread: Dict, w3: Web3) -> Dict:
    """
    Helper: Build execution payload from spread

    Usage:
        spread = engine.scan_for_spreads()[0]
        payload = build_execution_payload(spread, w3)
    """
    executor = get_institutional_executor(w3)

    # Derive from_address from PRIVATE_KEY so the nonce lookup targets the right account.
    # Fall back to EXECUTOR_WALLET only when PRIVATE_KEY is not configured.
    private_key = os.getenv('PRIVATE_KEY')
    if private_key:
        from_address = w3.eth.account.from_key(private_key).address
    else:
        from_address = os.getenv('EXECUTOR_WALLET', '0x0000000000000000000000000000000000000000')

    return executor.build_execution_from_spread(
        spread=spread,
        from_address=from_address,
        use_balancer=True,  # Prefer FREE flash loans
        dry_run=True
    )
