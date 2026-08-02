"""
APEX_OMEGA UNIFIED STRATEGY CONTROLLER
Master orchestrator for all MEV strategies

Integrates:
- Cross-DEX Arbitrage (C1 contract)
- Dual-Punch Recursive (C2 contract + Phase 3)
- Liquidation Hunting (Aave V3)
- Mempool Sandwich (Front-run/Back-run)

Zero-drift execution with contract-specific helpers
"""

import asyncio
import logging
from typing import Dict, List, Optional, Tuple
from enum import Enum
from dataclasses import dataclass
from web3 import Web3
import os
from execution_governance import get_minimum_net_profit_usd
from institutional_executor import C1_ADDRESS, InstitutionalExecutor
from liquidation_executor_contract import (
    get_configured_liquidation_executor_address,
    get_liquidation_executor,
)

# Phase 3 imports
from dual_punch_manager import get_dual_punch_manager
from rust_bridge_client import get_rust_bridge_client
from execution_logger import get_execution_logger
from amm_math import get_protocol_router
from v3_tick_walker import calculate_v3_swap_with_ticks
from curve_onchain import calculate_curve_swap_onchain
from executor_registry import get_rpc_url

logger = logging.getLogger(__name__)


# ============================================================================
# STRATEGY TYPES
# ============================================================================

class StrategyType(Enum):
    """All supported MEV strategy types."""
    CROSS_DEX_ARB = "cross_dex_arbitrage"      # Simple A→B arbitrage
    DUAL_PUNCH = "dual_punch_recursive"        # C1+C2 cascade
    LIQUIDATION = "liquidation_hunt"           # Aave/Compound liquidations
    SANDWICH = "mempool_sandwich"              # Front-run + back-run
    FLASH_ARB = "flash_arbitrage"              # Flash loan arbitrage


class ExecutorContract(Enum):
    """Deployed contract addresses."""
    C1_PRIMARY = "0xAF54E6cA47E2B494C9c4aEc985B25c17F1F7b607"     # C1 Arbitrage
    C1_SECONDARY = "0xa75f0b421b00E007cEe84FB7d0463a5aAf59771c"   # C1 Arbitrage (backup)
    C2_LIQUIDATION = "0xEDa4F1ACa3A0533e8C2C4CFC7F04Ddcd5f68C5b8"  # C2 + Liquidation
    C2_DUAL_PUNCH = None  # Will be set when deployed


@dataclass
class Opportunity:
    """Unified opportunity structure."""
    strategy: StrategyType
    pair: str
    dex_in: str
    dex_out: str
    amount_in: float
    expected_profit: float
    gas_cost: float
    pool_liquidity: float
    spread_bps: float
    priority: int  # 1=critical, 2=high, 3=medium, 4=low
    metadata: Dict  # Strategy-specific data


# ============================================================================
# UNIFIED STRATEGY CONTROLLER
# ============================================================================

class UnifiedStrategyController:
    """
    Master controller for all MEV strategies.
    
    Routes opportunities to correct execution path:
    - Simple arbitrage → C1 contract
    - Dual-punch → C2 contract + Shadow Gate
    - Liquidation → C2 liquidation contract
    - Sandwich → Mempool executor
    """
    
    def __init__(self):
        self.dual_punch_manager = get_dual_punch_manager()
        self.rust_bridge = get_rust_bridge_client()
        self.execution_logger = get_execution_logger()
        self.protocol_router = get_protocol_router()
        
        # Contract addresses
        self.c1_primary = os.environ.get('INSTITUTIONAL_EXECUTOR_ADDRESS', C1_ADDRESS)
        self.c1_secondary = ExecutorContract.C1_SECONDARY.value
        self.c2_liquidation = get_configured_liquidation_executor_address()
        
        # Web3 instance
        self.rpc_url = get_rpc_url('polygon')
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url)) if self.rpc_url else None
        
        # Strategy stats
        self.stats = {
            StrategyType.CROSS_DEX_ARB: {'executed': 0, 'profit': 0, 'failed': 0},
            StrategyType.DUAL_PUNCH: {'executed': 0, 'profit': 0, 'failed': 0},
            StrategyType.LIQUIDATION: {'executed': 0, 'profit': 0, 'failed': 0},
            StrategyType.SANDWICH: {'executed': 0, 'profit': 0, 'failed': 0},
        }
        
        # Execution queue (priority-based)
        self.execution_queue = asyncio.PriorityQueue()
        
        logger.info("🔱 Unified Strategy Controller initialized")
        logger.info(f"   C1 Primary: {self.c1_primary}")
        logger.info(f"   C2 Liquidation: {self.c2_liquidation}")
    
    async def evaluate_opportunity(
        self,
        strategy: StrategyType,
        pool_data: Dict,
        amount_in: float
    ) -> Optional[Opportunity]:
        """
        Evaluate opportunity using strategy-specific logic.
        
        Returns Opportunity if profitable, None otherwise.
        """
        if strategy == StrategyType.CROSS_DEX_ARB:
            return await self._evaluate_cross_dex_arb(pool_data, amount_in)
        
        elif strategy == StrategyType.DUAL_PUNCH:
            return await self._evaluate_dual_punch(pool_data, amount_in)
        
        elif strategy == StrategyType.LIQUIDATION:
            return await self._evaluate_liquidation(pool_data)
        
        elif strategy == StrategyType.SANDWICH:
            return await self._evaluate_sandwich(pool_data)
        
        else:
            logger.warning(f"Unknown strategy: {strategy}")
            return None
    
    async def execute_opportunity(self, opportunity: Opportunity) -> Dict:
        """
        Execute opportunity using correct executor.
        
        Routes to:
        - C1 contract for simple arbitrage
        - C2 + Shadow Gate for dual-punch
        - C2 for liquidations
        - Mempool executor for sandwich
        """
        logger.info(f"🎯 Executing {opportunity.strategy.value}: {opportunity.pair}")
        
        try:
            if opportunity.strategy == StrategyType.CROSS_DEX_ARB:
                result = await self._execute_c1_arbitrage(opportunity)
            
            elif opportunity.strategy == StrategyType.DUAL_PUNCH:
                result = await self._execute_c2_dual_punch(opportunity)
            
            elif opportunity.strategy == StrategyType.LIQUIDATION:
                result = await self._execute_c2_liquidation(opportunity)
            
            elif opportunity.strategy == StrategyType.SANDWICH:
                result = await self._execute_sandwich(opportunity)
            
            else:
                raise ValueError(f"Unknown strategy: {opportunity.strategy}")
            
            # Update stats
            if result['success']:
                self.stats[opportunity.strategy]['executed'] += 1
                self.stats[opportunity.strategy]['profit'] += result.get('profit', 0)
            else:
                self.stats[opportunity.strategy]['failed'] += 1
            
            return result
        
        except Exception as e:
            logger.error(f"❌ Execution failed: {e}")
            self.stats[opportunity.strategy]['failed'] += 1
            return {'success': False, 'error': str(e)}
    
    # ========================================================================
    # EVALUATION METHODS (Strategy-Specific)
    # ========================================================================
    
    async def _evaluate_cross_dex_arb(
        self,
        pool_data: Dict,
        amount_in: float
    ) -> Optional[Opportunity]:
        """
        Evaluate simple cross-DEX arbitrage.
        
        Example: Buy WMATIC on QuickSwap, sell on Sushi
        """
        dex_in = pool_data.get('dex_in', 'quickswap_v2')
        dex_out = pool_data.get('dex_out', 'sushi_v2')
        
        # Calculate using exact AMM math
        swap_in = self.protocol_router.calculate_swap(
            dex=dex_in,
            pool_data={
                'reserve_in': pool_data['reserve_in_dex1'],
                'reserve_out': pool_data['reserve_out_dex1']
            },
            amount_in=amount_in,
            fee=pool_data.get('fee_dex1', 0.003)
        )
        
        amount_out = swap_in['amount_out']
        
        swap_out = self.protocol_router.calculate_swap(
            dex=dex_out,
            pool_data={
                'reserve_in': pool_data['reserve_out_dex2'],
                'reserve_out': pool_data['reserve_in_dex2']
            },
            amount_in=amount_out,
            fee=pool_data.get('fee_dex2', 0.003)
        )
        
        final_amount = swap_out['amount_out']
        gross_profit = final_amount - amount_in
        gas_cost = 0.02  # Estimated
        net_profit = gross_profit - gas_cost
        
        if net_profit < get_minimum_net_profit_usd():
            return None
        
        return Opportunity(
            strategy=StrategyType.CROSS_DEX_ARB,
            pair=pool_data['pair'],
            dex_in=dex_in,
            dex_out=dex_out,
            amount_in=amount_in,
            expected_profit=net_profit,
            gas_cost=gas_cost,
            pool_liquidity=pool_data.get('liquidity', 0),
            spread_bps=(gross_profit / amount_in) * 10000,
            priority=2,  # High priority
            metadata={
                'amount_mid': amount_out,
                'amount_final': final_amount,
                'slippage_in': swap_in['slippage'],
                'slippage_out': swap_out['slippage']
            }
        )
    
    async def _evaluate_dual_punch(
        self,
        pool_data: Dict,
        amount_in: float
    ) -> Optional[Opportunity]:
        """
        Evaluate dual-punch opportunity.
        
        Uses Phase 3 dual-punch manager for evaluation.
        """
        evaluation = await self.dual_punch_manager.evaluate_dual_punch_opportunity(
            pair=pool_data['pair'],
            c1_size_usd=amount_in,
            c1_entry_price=pool_data.get('entry_price', 1.0),
            c1_target_price=pool_data.get('target_price', 1.003),
            pool_liquidity_usd=pool_data['liquidity'],
            pool_current_price=pool_data.get('current_price', 1.0),
            volatility_1h=pool_data.get('volatility_1h', 0.01),
            volatility_24h=pool_data.get('volatility_24h', 0.02),
            gas_cost_usd=0.02
        )
        
        if evaluation['decision'] == 'ABORT':
            return None
        
        return Opportunity(
            strategy=StrategyType.DUAL_PUNCH,
            pair=pool_data['pair'],
            dex_in=pool_data.get('dex', 'quickswap_v3'),
            dex_out=pool_data.get('dex', 'quickswap_v3'),
            amount_in=amount_in,
            expected_profit=evaluation.get('net_profit', 0),
            gas_cost=0.02,
            pool_liquidity=pool_data['liquidity'],
            spread_bps=evaluation.get('spread_bps', 0),
            priority=1,  # Critical priority
            metadata={'evaluation': evaluation}
        )
    
    async def _evaluate_liquidation(self, pool_data: Dict) -> Optional[Opportunity]:
        """
        Evaluate liquidation opportunity on Aave V3.
        
        Monitors health factors < 1.0
        """
        # Placeholder - would integrate with Aave subgraph
        health_factor = pool_data.get('health_factor', 1.5)
        
        if health_factor >= 1.0:
            return None
        
        collateral_value = pool_data.get('collateral_value_usd', 0)
        debt_value = pool_data.get('debt_value_usd', 0)
        liquidation_bonus = 0.05  # 5% bonus
        
        max_liquidatable = debt_value * 0.5  # 50% max
        expected_profit = max_liquidatable * liquidation_bonus
        gas_cost = 0.03
        net_profit = expected_profit - gas_cost
        
        if net_profit < get_minimum_net_profit_usd():
            return None
        
        return Opportunity(
            strategy=StrategyType.LIQUIDATION,
            pair=f"{pool_data.get('collateral_asset')}/{pool_data.get('debt_asset')}",
            dex_in='aave_v3',
            dex_out='aave_v3',
            amount_in=max_liquidatable,
            expected_profit=net_profit,
            gas_cost=gas_cost,
            pool_liquidity=collateral_value,
            spread_bps=liquidation_bonus * 10000,
            priority=1,  # Critical
            metadata={
                'borrower': pool_data.get('borrower'),
                'health_factor': health_factor,
                'collateral_asset': pool_data.get('collateral_asset'),
                'debt_asset': pool_data.get('debt_asset'),
                'max_liquidatable_debt_usd': max_liquidatable,
                'liquidation_bonus': liquidation_bonus,
                'execution_mode': pool_data.get('execution_mode', 'confirmed')
            }
        )
    
    async def _evaluate_sandwich(self, pool_data: Dict) -> Optional[Opportunity]:
        """
        Evaluate sandwich opportunity from mempool transaction.
        
        Front-run + victim tx + back-run
        """
        victim_tx = pool_data.get('victim_tx', {})
        victim_amount = victim_tx.get('amount', 0)
        victim_slippage = victim_tx.get('max_slippage', 0.01)
        
        # Calculate frontrun size (smaller than victim)
        frontrun_amount = victim_amount * 0.3
        
        # Simulate price impact
        pool_liquidity = pool_data.get('liquidity', 0)
        price_impact = (frontrun_amount + victim_amount) / pool_liquidity
        
        # Profit = capture victim's slippage
        expected_profit = victim_amount * price_impact * 0.5  # Conservative
        gas_cost = 0.04  # 2 transactions
        net_profit = expected_profit - gas_cost
        
        if net_profit < get_minimum_net_profit_usd():
            return None
        
        return Opportunity(
            strategy=StrategyType.SANDWICH,
            pair=pool_data.get('pair', 'UNKNOWN'),
            dex_in=pool_data.get('dex', 'unknown'),
            dex_out=pool_data.get('dex', 'unknown'),
            amount_in=frontrun_amount,
            expected_profit=net_profit,
            gas_cost=gas_cost,
            pool_liquidity=pool_liquidity,
            spread_bps=price_impact * 10000,
            priority=3,  # Medium (time-sensitive)
            metadata={
                'victim_tx_hash': victim_tx.get('hash'),
                'victim_amount': victim_amount,
                'frontrun_amount': frontrun_amount,
                'backrun_amount': frontrun_amount  # Sell same amount
            }
        )
    
    # ========================================================================
    # EXECUTION METHODS (Contract-Specific)
    # ========================================================================
    
    async def _execute_c1_arbitrage(self, opp: Opportunity) -> Dict:
        """
        Execute simple arbitrage via the InstitutionalExecutor C1 contract.

        This path intentionally fails closed unless the opportunity includes a
        concrete flashLoan payload that can be encoded by institutional_executor.
        """
        logger.info(f"📡 C1 Execution: {opp.pair} via {self.c1_primary}")

        self._require_w3()
        self._require_contract_address(self.c1_primary, 'INSTITUTIONAL_EXECUTOR_ADDRESS')
        account = self._get_execution_account()

        spread = self._build_c1_spread(opp)
        executor = InstitutionalExecutor(self.w3, self.c1_primary)
        self._assert_contract_owner(executor.tx_builder, account.address, "C1 InstitutionalExecutor")

        execution = executor.build_execution_from_spread(
            spread=spread,
            from_address=account.address,
            use_balancer=opp.metadata.get('use_balancer', True),
            dry_run=False,
        )

        result = self._sign_send_and_maybe_wait(
            tx=execution['tx'],
            private_key=os.environ['PRIVATE_KEY'],
            mode=opp.metadata.get('execution_mode', 'confirmed'),
        )
        result.update({
            'strategy': StrategyType.CROSS_DEX_ARB.value,
            'profit': opp.expected_profit if result['success'] else 0,
            'estimated_gas': execution.get('estimated_gas'),
        })

        if result['success']:
            logger.info(f"✅ C1 transaction {result['tx_hash']} accepted")
        else:
            logger.warning(f"❌ C1 transaction failed: {result.get('revert_reason')}")

        return result

    async def _execute_c2_dual_punch(self, opp: Opportunity) -> Dict:
        """
        Execute dual-punch via C2 contract + Phase 3 Shadow Gate.
        
        MANDATORY: Shadow Gate simulation before execution
        """
        logger.info(f"🔱 C2 Dual-Punch: {opp.pair}")
        
        evaluation = opp.metadata['evaluation']
        
        # Execute via dual-punch manager (includes Shadow Gate)
        result = await self.dual_punch_manager.execute_dual_punch(
            evaluation=evaluation,
            pool_address=opp.metadata.get('pool_address', '0x' + '0' * 40),
            token0=opp.pair.split('/')[0],
            token1=opp.pair.split('/')[1],
            volatility_1h=0.01,
            volatility_24h=0.02,
            gas_price_gwei=50
        )
        
        if result['success']:
            logger.info(f"✅ C2 Dual-Punch Success: ${result['actual_profit']:.2f}")
        else:
            logger.warning(f"❌ C2 Dual-Punch Failed: {result.get('reason')}")
        
        return result
    
    async def _execute_c2_liquidation(self, opp: Opportunity) -> Dict:
        """
        Execute liquidation via the LiquidationExecutor contract.
        """
        logger.info(f"💀 C2 Liquidation: {opp.pair}")
        logger.info(f"   Borrower: {opp.metadata.get('borrower')}")
        logger.info(f"   Health Factor: {opp.metadata.get('health_factor'):.4f}")

        self._require_w3()
        account = self._get_execution_account()
        self._require_contract_address(self.c2_liquidation, 'LIQUIDATION_EXECUTOR_ADDRESS')

        position = self._build_liquidation_position(opp)
        executor = get_liquidation_executor(self.w3, self.c2_liquidation)
        self._assert_contract_owner(executor.tx_builder, account.address, "LiquidationExecutor")

        execution = executor.build_execution_from_position(
            position=position,
            from_address=account.address,
            min_profit_bps=opp.metadata.get('min_profit_bps', 50),
            dry_run=False,
        )

        result = self._sign_send_and_maybe_wait(
            tx=execution['tx'],
            private_key=os.environ['PRIVATE_KEY'],
            mode=opp.metadata.get('execution_mode', 'confirmed'),
        )
        result.update({
            'strategy': StrategyType.LIQUIDATION.value,
            'profit': opp.expected_profit if result['success'] else 0,
            'estimated_gas': execution.get('estimated_gas'),
            'liquidation_bonus': opp.metadata.get('liquidation_bonus', 0.05),
        })

        if result['success']:
            logger.info(f"✅ Liquidation transaction {result['tx_hash']} accepted")
        else:
            logger.warning(f"❌ Liquidation failed: {result.get('revert_reason')}")

        return result
    
    async def _execute_sandwich(self, opp: Opportunity) -> Dict:
        """
        Sandwich/MEV execution is disabled until a private relay bundle path is
        available. Public mempool submission would leak strategy and can harm
        users, so this route fails closed instead of simulating success.
        """
        logger.warning("Sandwich execution requested but private relay bundle support is unavailable")
        return {
            'success': False,
            'strategy': StrategyType.SANDWICH.value,
            'error': 'sandwich execution disabled: private relay bundle support unavailable',
            'revert_reason': 'PRIVATE_RELAY_UNAVAILABLE',
            'tx_hash': None,
            'receipt_status': None,
            'gas_used': None,
        }

    # ========================================================================
    # HELPERS
    # ========================================================================
    
    def _require_w3(self) -> None:
        """Require a configured and reachable RPC before building transactions."""
        if not self.rpc_url or not self.w3:
            raise RuntimeError("Polygon RPC is not configured")
        if not self.w3.is_connected():
            raise RuntimeError("Polygon RPC is not reachable")


    @staticmethod
    def _require_contract_address(address: Optional[str], label: str) -> None:
        """Require a configured, non-zero contract address."""
        if not address or not Web3.is_address(address) or int(address, 16) == 0:
            raise RuntimeError(f"{label} is not configured")

    def _get_execution_account(self):
        """Return the signer account, failing closed when PRIVATE_KEY is absent."""
        private_key = os.environ.get('PRIVATE_KEY')
        if not private_key:
            raise RuntimeError("PRIVATE_KEY is not configured")
        return self.w3.eth.account.from_key(private_key)

    @staticmethod
    def _assert_contract_owner(tx_builder, from_address: str, label: str) -> None:
        """Ensure the configured signer owns the executor contract."""
        owner = Web3.to_checksum_address(tx_builder.get_contract_owner())
        sender = Web3.to_checksum_address(from_address)
        if owner != sender:
            raise PermissionError(
                f"{label} owner mismatch: signer {sender} is not contract owner {owner}"
            )

    @staticmethod
    def _build_c1_spread(opp: Opportunity) -> Dict:
        """Build the spread dict required by institutional_executor."""
        flash_loan = opp.metadata.get('flashLoan') or opp.metadata.get('flash_loan')
        if not flash_loan:
            raise ValueError(
                "C1 arbitrage execution requires a concrete flashLoan payload with token addresses, pools, protocols, and USD amounts"
            )
        return {
            'pair': opp.pair,
            'dex_in': opp.dex_in,
            'dex_out': opp.dex_out,
            'flashLoan': flash_loan,
        }

    @staticmethod
    def _build_liquidation_position(opp: Opportunity) -> Dict:
        """Build the position dict required by liquidation_executor_contract."""
        required = ('borrower', 'collateral_asset', 'debt_asset')
        missing = [key for key in required if not opp.metadata.get(key)]
        if missing:
            raise ValueError(f"Liquidation execution missing required fields: {', '.join(missing)}")

        return {
            'user_address': opp.metadata['borrower'],
            'collateral_asset': opp.metadata['collateral_asset'],
            'debt_asset': opp.metadata['debt_asset'],
            'max_liquidatable_debt_usd': opp.metadata.get('max_liquidatable_debt_usd', opp.amount_in),
            'health_factor': opp.metadata.get('health_factor'),
        }

    def _sign_send_and_maybe_wait(self, tx: Dict, private_key: str, mode: str = 'confirmed') -> Dict:
        """Sign, broadcast, and optionally wait for a transaction receipt."""
        mode = (mode or 'confirmed').lower()
        if mode not in {'accepted', 'confirmed'}:
            raise ValueError("execution_mode must be 'accepted' or 'confirmed'")

        signed = self.w3.eth.account.sign_transaction(tx, private_key)
        raw_tx = getattr(signed, 'rawTransaction', None) or getattr(signed, 'raw_transaction')
        tx_hash_bytes = self.w3.eth.send_raw_transaction(raw_tx)
        tx_hash = self.w3.to_hex(tx_hash_bytes)

        result = {
            'success': True,
            'tx_hash': tx_hash,
            'receipt_status': None,
            'gas_used': None,
            'revert_reason': None,
            'accepted': True,
            'confirmed': False,
        }

        if mode == 'accepted':
            return result

        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
        status = receipt.get('status')
        result.update({
            'success': status == 1,
            'receipt_status': status,
            'gas_used': receipt.get('gasUsed'),
            'confirmed': True,
        })
        if status != 1:
            result['revert_reason'] = self._get_revert_reason(tx, receipt)
        return result

    def _get_revert_reason(self, tx: Dict, receipt: Dict) -> str:
        """Best-effort revert reason extraction via eth_call at the mined block."""
        call_tx = {key: value for key, value in tx.items() if key in {'from', 'to', 'data', 'value'}}
        try:
            self.w3.eth.call(call_tx, block_identifier=receipt.get('blockNumber'))
        except Exception as exc:
            return str(exc)
        return 'transaction reverted without reason'

    def get_stats(self) -> Dict:
        """Get execution statistics for all strategies."""
        return {
            'strategies': self.stats,
            'total_executed': sum(s['executed'] for s in self.stats.values()),
            'total_profit': sum(s['profit'] for s in self.stats.values()),
            'total_failed': sum(s['failed'] for s in self.stats.values())
        }


# ============================================================================
# SINGLETON
# ============================================================================

_controller = None


def get_unified_controller() -> UnifiedStrategyController:
    """Get singleton unified controller."""
    global _controller
    if _controller is None:
        _controller = UnifiedStrategyController()
    return _controller
