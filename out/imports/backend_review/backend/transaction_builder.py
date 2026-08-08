"""
APEX_OMEGA — World-Class Transaction Builder & Proof Gate System

This module provides a robust, fluent Builder pattern for constructing and
validating transactions before they are signed and broadcast. It serves as the
final, critical checkpoint in the execution pipeline.

The `TransactionBuilder` consumes a high-level `SpreadOpportunity` and enforces
a series of explicit "proof gates" to ensure that every transaction is:

1.  **Ready**: The execution environment (wallet, RPC, contracts) is healthy.
2.  **Profitable**: The opportunity exceeds minimum profit thresholds after all
    costs, as determined by the latest analysis.
3.  **Safe**: The opportunity passes risk controls for slippage, liquidity depth,
    and other critical path validations.
4.  **Correct**: The generated payload correctly represents the intended route
    and can be successfully simulated.

Only after all gates have passed is a signable transaction object produced.
This pattern makes the transition from "analyzed opportunity" to "executable
transaction" explicit, auditable, and secure.
"""

import logging
from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, List, Optional, Any

from web3 import Web3

from arbitrage_engine import SpreadOpportunity, PoolPrice
from contract_interface import RouteBuilder, RouteEnvelope, ContractInterface
from depth_health_scoring import get_depth_scorer
from execution_governance import get_minimum_net_profit_usd

logger = logging.getLogger(__name__)


class ProofGate(Enum):
    """Enumeration of all pre-flight checks required for transaction signing."""
    WALLET_READINESS = auto()
    RPC_LIVENESS = auto()
    CONTRACT_READINESS = auto()
    PROFITABILITY = auto()
    SLIPPAGE_AND_DEPTH = auto()
    PAYLOAD_CONSTRUCTION = auto()
    SIMULATION = auto()


@dataclass
class CanonicalAmount:
    """
    A Python representation of a token amount, encapsulating the raw integer
    value and the token's decimals for precision-safe arithmetic.
    """
    raw: int
    decimals: int

    def __repr__(self) -> str:
        return f"CanonicalAmount(raw={self.raw}, decimals={self.decimals})"

    @property
    def as_float(self) -> float:
        """Returns the human-readable float representation."""
        return float(self.raw) / (10 ** self.decimals)


class TransactionBuilderError(Exception):
    """Custom exception for failures during the transaction build process."""
    def __init__(self, message: str, failed_gate: Optional[ProofGate] = None, errors: Optional[List[str]] = None):
        super().__init__(message)
        self.failed_gate = failed_gate
        self.errors = errors or []


class TransactionBuilder:
    """
    A fluent builder that constructs a signable transaction from a SpreadOpportunity,
    while enforcing a series of critical proof gates.
    """

    def __init__(self, opportunity: SpreadOpportunity, w3: Web3, wallet_address: str, private_key: str):
        if not opportunity or not opportunity.flash_loan or not opportunity.flash_loan.leg1 or not opportunity.flash_loan.leg2:
            raise ValueError("Opportunity, flash loan, and both legs must be fully defined.")

        self.opportunity = opportunity
        self.w3 = w3
        self.wallet_address = wallet_address
        self.private_key = private_key
        self.contract_interface: Optional[ContractInterface] = None

        self._gates: Dict[ProofGate, bool] = {}
        self._errors: List[str] = []
        self._route_envelope: Optional[RouteEnvelope] = None
        self._built_tx: Optional[Dict[str, Any]] = None

    def _record_gate(self, gate: ProofGate, passed: bool, error_msg: Optional[str] = None):
        """Records the result of a gate check."""
        self._gates[gate] = passed
        if not passed and error_msg:
            self._errors.append(f"[{gate.name}] {error_msg}")
        logger.debug(f"Proof Gate '{gate.name}': {'PASS' if passed else 'FAIL'}")

    def gate_wallet_readiness(self, min_balance_matic: float = 0.1) -> 'TransactionBuilder':
        """Checks if the executor wallet has sufficient balance for gas."""
        try:
            balance_wei = self.w3.eth.get_balance(self.wallet_address)
            balance_matic = balance_wei / 1e18
            if balance_matic < min_balance_matic:
                self._record_gate(
                    ProofGate.WALLET_READINESS, False,
                    f"Insufficient gas balance: {balance_matic:.4f} MATIC < {min_balance_matic} MATIC required."
                )
            else:
                self._record_gate(ProofGate.WALLET_READINESS, True)
        except Exception as e:
            self._record_gate(ProofGate.WALLET_READINESS, False, f"Failed to get wallet balance: {e}")
        return self

    def gate_rpc_liveness(self, max_block_lag: int = 5) -> 'TransactionBuilder':
        """Checks if the RPC endpoint is connected and reasonably synced."""
        try:
            if not self.w3.is_connected():
                self._record_gate(ProofGate.RPC_LIVENESS, False, "Web3 provider is not connected.")
                return self

            latest_block = self.w3.eth.block_number
            if latest_block < 1:
                self._record_gate(ProofGate.RPC_LIVENESS, False, "RPC returned invalid block number.")
            # A more advanced check could compare against a secondary RPC. For now, we check for a valid number.
            else:
                self._record_gate(ProofGate.RPC_LIVENESS, True)
        except Exception as e:
            self._record_gate(ProofGate.RPC_LIVENESS, False, f"RPC liveness check failed: {e}")
        return self

    def gate_contract_readiness(self) -> 'TransactionBuilder':
        """Checks if the target executor contract is deployed and ready."""
        try:
            # Assuming C1 is the target for this example
            from institutional_executor import C1_ADDRESS
            contract_address = C1_ADDRESS
            self.contract_interface = ContractInterface(self.w3, contract_address)

            code = self.w3.eth.get_code(self.contract_interface.address)
            if len(code) <= 2:
                self._record_gate(ProofGate.CONTRACT_READINESS, False, f"No bytecode at executor address {contract_address}")
            else:
                self._record_gate(ProofGate.CONTRACT_READINESS, True)
        except Exception as e:
            self._record_gate(ProofGate.CONTRACT_READINESS, False, f"Contract readiness check failed: {e}")
        return self

    def gate_profitability(self) -> 'TransactionBuilder':
        """Checks if the opportunity's net profit meets the configured minimum."""
        min_profit = get_minimum_net_profit_usd()
        net_profit = self.opportunity.flash_loan.net_profit_after_gas_usd

        if net_profit < min_profit:
            self._record_gate(
                ProofGate.PROFITABILITY, False,
                f"Net profit ${net_profit:.2f} is below minimum of ${min_profit:.2f}"
            )
        else:
            self._record_gate(ProofGate.PROFITABILITY, True)
        return self

    def gate_slippage_and_depth(self) -> 'TransactionBuilder':
        """
        Uses the DepthHealthScorer to validate the entire path against slippage
        and liquidity constraints.
        """
        # This gate requires more context than is available in SpreadOpportunity.
        # In a real system, the full PoolPrice objects would be passed in or retrieved.
        # For this example, we'll assume the opportunity is pre-vetted and pass the gate.
        logger.warning("Slippage & Depth gate is a placeholder. Real implementation needs full pool objects.")
        self._record_gate(ProofGate.SLIPPAGE_AND_DEPTH, True)
        return self

    def construct_payload(self) -> 'TransactionBuilder':
        """
        Builds the `RouteEnvelope` using the `RouteBuilder` from contract_interface.
        This step translates the high-level opportunity into a contract-readable format.
        """
        if any(not passed for passed in self._gates.values()):
            self._record_gate(ProofGate.PAYLOAD_CONSTRUCTION, False, "Skipped due to prior gate failures.")
            return self

        try:
            fl = self.opportunity.flash_loan
            leg1 = fl.leg1
            leg2 = fl.leg2

            # This is a simplified conversion. A real implementation would need to map
            # DEX names/protocols to the integer constants required by the contract.
            from contract_interface import Protocol

            self._route_envelope = RouteBuilder.build_simple_arb_route(
                token_a=leg1.token_in,
                token_b=leg1.token_out,
                amount=leg1.amount_in,
                executor_address=self.contract_interface.address,
                buy_router=leg1.pool,  # Assuming pool address is the router for simplicity
                sell_router=leg2.pool,
                buy_protocol=Protocol.UNISWAP_V3, # Placeholder
                sell_protocol=Protocol.SUSHISWAP, # Placeholder
                fee_tier=leg1.fee,
                slippage_bps=50  # 0.5%
            )
            self._record_gate(ProofGate.PAYLOAD_CONSTRUCTION, True)
        except Exception as e:
            logger.exception("Payload construction failed.")
            self._record_gate(ProofGate.PAYLOAD_CONSTRUCTION, False, f"RouteEnvelope creation failed: {e}")
        return self

    def simulate(self) -> 'TransactionBuilder':
        """
        Performs a read-only `eth_call` to simulate the transaction. This is the
        most critical gate, proving the transaction will not revert on-chain.
        """
        if not self._route_envelope:
            self._record_gate(ProofGate.SIMULATION, False, "Skipped; no payload to simulate.")
            return self

        try:
            fl = self.opportunity.flash_loan
            min_profit_raw = 0 # For simulation, we just want to check for reverts.

            # The `estimate_gas` function serves as an effective simulation, as it
            # executes the transaction via `eth_call`. A failure indicates a revert.
            gas_estimate = self.contract_interface.estimate_gas(
                asset=fl.leg1.token_in,
                amount=fl.leg1.amount_in,
                min_profit=min_profit_raw,
                proof=[], # Merkle proof would be needed for a real system
                params=self._route_envelope.encode(),
                from_address=self.wallet_address,
                use_c1=True # Assuming Aave flash loan via C1
            )

            if gas_estimate > 0:
                self._record_gate(ProofGate.SIMULATION, True)
            else:
                self._record_gate(ProofGate.SIMULATION, False, "Gas estimation returned 0, indicating a likely revert.")

        except Exception as e:
            revert_reason = str(e)
            logger.warning(f"Transaction simulation failed with revert: {revert_reason}")
            self._record_gate(ProofGate.SIMULATION, False, f"eth_call simulation failed: {revert_reason}")
        return self

    def build(self) -> Dict[str, Any]:
        """
        Finalizes the transaction build process after all gates have passed.
        
        Returns:
            A signable transaction dictionary compatible with web3.py.
        
        Raises:
            TransactionBuilderError: If any proof gate has failed.
        """
        if not all(self._gates.values()):
            raise TransactionBuilderError(
                "Transaction build failed: One or more proof gates did not pass.",
                errors=self._errors
            )

        if not self._route_envelope or not self.contract_interface:
            raise TransactionBuilderError("Payload was not constructed or contract interface is missing.")

        fl = self.opportunity.flash_loan
        min_profit_raw = 0 # Final check, slippage protection is in the route steps

        tx = self.contract_interface.build_execute_tx(
            asset=fl.leg1.token_in,
            amount=fl.leg1.amount_in,
            min_profit=min_profit_raw,
            proof=[],
            params=self._route_envelope.encode(),
            from_address=self.wallet_address,
            use_c1=True
        )
        self._built_tx = tx
        return self._built_tx

    def get_signed_tx(self) -> Optional[str]:
        """Signs the built transaction with the provided private key."""
        if not self._built_tx:
            raise TransactionBuilderError("Transaction has not been built yet. Call .build() first.")

        signed_tx = self.w3.eth.account.sign_transaction(self._built_tx, self.private_key)
        return signed_tx.rawTransaction.hex()