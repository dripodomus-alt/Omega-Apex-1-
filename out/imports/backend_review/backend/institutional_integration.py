"""
Institutional Math Integration Layer
Wrapper that coordinates all institutional math modules for arbitrage_engine.py

This module integrates:
1. Flash loan provider selection (Balancer 0% vs Aave 0.09%)
2. Depth & health validation
3. Optimal sizing (Angeris-Chitra)
4. Gas oracle + optimal tip
5. SSOT pipeline validation

Usage:
    from institutional_integration import analyze_opportunity_institutional
    
    result = analyze_opportunity_institutional(
        pool1=buy_pool,
        pool2=sell_pool,
        w3=w3_instance
    )
"""

import logging
import time
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from web3 import Web3

# Import institutional math modules
from optimal_sizing import get_optimal_input, verify_profitability
from depth_health_scoring import get_depth_scorer, PoolMetrics
from ssot_pipeline import get_ssot_finalizer, PipelineFinalResult, C2Decision
from mev_gas_oracle import get_gas_oracle, get_tip_optimizer, GasSnapshot, TipRecommendation
from flash_loan_providers import FlashLoanSelector, FlashLoanProvider, FLASH_LOAN_PROVIDERS

logger = logging.getLogger(__name__)


@dataclass
class ExecutionTrace:
    """Complete execution trace for dashboard visibility"""
    timestamp: int
    step_name: str
    formula_used: str
    inputs: Dict
    outputs: Dict
    passed: bool
    reason: Optional[str] = None
    duration_ms: float = 0


@dataclass
class InstitutionalOpportunity:
    """
    Complete opportunity with institutional math analysis
    This extends the basic SpreadOpportunity with full transparency
    """
    # Basic info
    ssn: str  # Unique ID (e.g., "OPP-2024-001234")
    timestamp: int
    token_pair: str
    
    # Pool details
    buy_pool_address: str
    sell_pool_address: str
    buy_dex: str
    sell_dex: str
    
    # Sizing
    optimal_loan_amount: float  # USD
    optimal_loan_token_units: float
    
    # Economics
    gross_profit_usd: float
    net_profit_usd: float
    roi_percent: float
    ev: float  # Expected value (P_fill × net_profit)
    
    # Flash loan
    flash_provider: str  # "Balancer" or "Aave V3"
    flash_fee_bps: int
    flash_fee_usd: float
    
    # Gas
    gas_snapshot: GasSnapshot
    tip_recommendation: TipRecommendation
    gas_cost_usd: float
    
    # Depth & health
    buy_pool_metrics: PoolMetrics
    sell_pool_metrics: PoolMetrics
    path_liquidity_factor: float
    
    # SSOT validation
    pipeline_result: PipelineFinalResult
    c2_decision: str  # "STRIKE" | "DO_NOTHING"
    
    # Execution
    is_executable: bool
    rejection_reason: Optional[str] = None
    
    # Transparency (for dashboard)
    execution_trace: List[ExecutionTrace] = field(default_factory=list)
    route_details: Dict = field(default_factory=dict)
    
    def add_trace(self, trace: ExecutionTrace):
        """Add execution trace step"""
        self.execution_trace.append(trace)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for API response"""
        return {
            "ssn": self.ssn,
            "timestamp": self.timestamp,
            "tokenPair": self.token_pair,
            "buyDex": self.buy_dex,
            "sellDex": self.sell_dex,
            "optimalLoanUsd": self.optimal_loan_amount,
            "netProfitUsd": self.net_profit_usd,
            "roiPercent": self.roi_percent,
            "ev": self.ev,
            "flashProvider": self.flash_provider,
            "gasCostUsd": self.gas_cost_usd,
            "pFill": self.tip_recommendation.p_fill,
            "c2Decision": self.c2_decision,
            "isExecutable": self.is_executable,
            "rejectionReason": self.rejection_reason,
            "executionTrace": [
                {
                    "step": t.step_name,
                    "formula": t.formula_used,
                    "passed": t.passed,
                    "durationMs": t.duration_ms
                }
                for t in self.execution_trace
            ],
            "depthMetrics": {
                "buyPool": {
                    "depthScore": self.buy_pool_metrics.depth_score,
                    "slippageBps": self.buy_pool_metrics.slippage_impact_bps,
                    "healthIndex": self.buy_pool_metrics.health_index
                },
                "sellPool": {
                    "depthScore": self.sell_pool_metrics.depth_score,
                    "slippageBps": self.sell_pool_metrics.slippage_impact_bps,
                    "healthIndex": self.sell_pool_metrics.health_index
                }
            }
        }


class InstitutionalMathCoordinator:
    """
    Coordinates all institutional math modules for complete opportunity analysis
    """
    
    def __init__(self, w3: Web3):
        self.w3 = w3
        self.depth_scorer = get_depth_scorer()
        self.flash_selector = FlashLoanSelector()
        self.ssot_finalizer = get_ssot_finalizer()
        
        # Initialize gas oracle
        self.gas_oracle = get_gas_oracle(w3)
        self.tip_optimizer = get_tip_optimizer(w3)
        
        # Counter for SSN generation
        self._ssn_counter = 0
    
    def generate_ssn(self) -> str:
        """Generate unique SSN for opportunity"""
        import datetime
        self._ssn_counter += 1
        date_str = datetime.datetime.now().strftime("%Y%m%d")
        return f"OPP-{date_str}-{self._ssn_counter:06d}"
    
    def analyze_opportunity(
        self,
        pool1_reserve_in: float,
        pool1_reserve_out: float,
        pool1_fee_bps: int,
        pool2_reserve_in: float,
        pool2_reserve_out: float,
        pool2_fee_bps: int,
        token_pair: str,
        buy_dex: str,
        sell_dex: str,
        buy_pool_address: str,
        sell_pool_address: str,
        token_price_usd: float,
        max_loan_usd: float = 50_000,
        min_profit_usd: float = 10.0
    ) -> Optional[InstitutionalOpportunity]:
        """
        Complete institutional math analysis
        
        Returns InstitutionalOpportunity if profitable, None otherwise
        """
        
        start_time = time.time()
        ssn = self.generate_ssn()
        timestamp = int(time.time())
        
        # Initialize opportunity (will be populated or rejected)
        opportunity = InstitutionalOpportunity(
            ssn=ssn,
            timestamp=timestamp,
            token_pair=token_pair,
            buy_pool_address=buy_pool_address,
            sell_pool_address=sell_pool_address,
            buy_dex=buy_dex,
            sell_dex=sell_dex,
            optimal_loan_amount=0,
            optimal_loan_token_units=0,
            gross_profit_usd=0,
            net_profit_usd=0,
            roi_percent=0,
            ev=0,
            flash_provider="Balancer",
            flash_fee_bps=0,
            flash_fee_usd=0,
            gas_snapshot=None,
            tip_recommendation=None,
            gas_cost_usd=0,
            buy_pool_metrics=None,
            sell_pool_metrics=None,
            path_liquidity_factor=0,
            pipeline_result=None,
            c2_decision="DO_NOTHING",
            is_executable=False
        )
        
        # ========================================================================
        # STEP 1: PROFITABILITY CHECK (Angeris-Chitra)
        # ========================================================================
        step_start = time.time()
        
        fee1_decimal = pool1_fee_bps / 10_000
        fee2_decimal = pool2_fee_bps / 10_000
        
        is_profitable, price_ratio = verify_profitability(
            r1_in=pool1_reserve_in,
            r1_out=pool1_reserve_out,
            fee1=fee1_decimal,
            r2_in=pool2_reserve_in,
            r2_out=pool2_reserve_out,
            fee2=fee2_decimal
        )
        
        trace_profitability = ExecutionTrace(
            timestamp=timestamp,
            step_name="Profitability Check",
            formula_used="Angeris-Chitra: γ₁γ₂R₁ₒR₂ₒ > R₁ᵢR₂ᵢ",
            inputs={
                "r1_in": pool1_reserve_in,
                "r1_out": pool1_reserve_out,
                "fee1": fee1_decimal,
                "r2_in": pool2_reserve_in,
                "r2_out": pool2_reserve_out,
                "fee2": fee2_decimal
            },
            outputs={
                "is_profitable": is_profitable,
                "price_ratio": price_ratio
            },
            passed=is_profitable,
            reason=None if is_profitable else f"Price ratio {price_ratio:.4f} ≤ 1.0",
            duration_ms=(time.time() - step_start) * 1000
        )
        opportunity.add_trace(trace_profitability)
        
        if not is_profitable:
            opportunity.is_executable = False
            opportunity.rejection_reason = "Failed profitability check"
            return opportunity
        
        # ========================================================================
        # STEP 2: OPTIMAL SIZING
        # ========================================================================
        step_start = time.time()
        
        optimal_input_tokens, sizing_profitable = get_optimal_input(
            pool1_reserve_in=pool1_reserve_in,
            pool1_reserve_out=pool1_reserve_out,
            pool1_fee=fee1_decimal,
            pool2_reserve_in=pool2_reserve_in,
            pool2_reserve_out=pool2_reserve_out,
            pool2_fee=fee2_decimal,
            max_size_usd=max_loan_usd / token_price_usd if token_price_usd > 0 else max_loan_usd
        )
        
        optimal_loan_usd = optimal_input_tokens * token_price_usd
        
        trace_sizing = ExecutionTrace(
            timestamp=timestamp,
            step_name="Optimal Sizing",
            formula_used="Angeris-Chitra: x* = (√(γ₁γ₂R₁R₂) - R₁R₂) / (γ₁(R₂ + γ₂R₁))",
            inputs={
                "max_loan_usd": max_loan_usd,
                "token_price_usd": token_price_usd
            },
            outputs={
                "optimal_tokens": optimal_input_tokens,
                "optimal_usd": optimal_loan_usd
            },
            passed=sizing_profitable,
            reason=None if sizing_profitable else "Optimal size calculation failed",
            duration_ms=(time.time() - step_start) * 1000
        )
        opportunity.add_trace(trace_sizing)
        
        if not sizing_profitable or optimal_loan_usd <= 0:
            opportunity.is_executable = False
            opportunity.rejection_reason = "Optimal sizing failed"
            return opportunity
        
        opportunity.optimal_loan_amount = optimal_loan_usd
        opportunity.optimal_loan_token_units = optimal_input_tokens
        
        # ========================================================================
        # STEP 3: DEPTH & HEALTH VALIDATION
        # ========================================================================
        step_start = time.time()
        
        is_valid_path, reason, metrics = self.depth_scorer.validate_two_leg_path(
            pool1_reserve_in=pool1_reserve_in,
            pool1_reserve_out=pool1_reserve_out,
            pool1_fee_bps=pool1_fee_bps,
            pool2_reserve_in=pool2_reserve_in,
            pool2_reserve_out=pool2_reserve_out,
            pool2_fee_bps=pool2_fee_bps,
            trade_size=optimal_input_tokens,
            pool1_tvl=pool1_reserve_in * token_price_usd,
            pool2_tvl=pool2_reserve_in * token_price_usd
        )
        
        opportunity.buy_pool_metrics = metrics["leg1"]
        opportunity.sell_pool_metrics = metrics["leg2"]
        
        if opportunity.buy_pool_metrics and opportunity.sell_pool_metrics:
            opportunity.path_liquidity_factor = self.depth_scorer.calculate_path_liquidity_factor([
                opportunity.buy_pool_metrics.depth_score,
                opportunity.sell_pool_metrics.depth_score
            ])
        
        trace_depth = ExecutionTrace(
            timestamp=timestamp,
            step_name="Depth & Health Validation",
            formula_used="Depth: √(R_in·R_out)·(1-fee), Gates: Slip≤40bps, Depth≥500, Health≥0.75",
            inputs={
                "trade_size": optimal_input_tokens,
                "pool1_tvl_usd": pool1_reserve_in * token_price_usd,
                "pool2_tvl_usd": pool2_reserve_in * token_price_usd
            },
            outputs={
                "leg1_depth": metrics["leg1"].depth_score if metrics["leg1"] else 0,
                "leg2_depth": metrics["leg2"].depth_score if metrics["leg2"] else 0,
                "path_liquidity": opportunity.path_liquidity_factor
            },
            passed=is_valid_path,
            reason=reason if not is_valid_path else None,
            duration_ms=(time.time() - step_start) * 1000
        )
        opportunity.add_trace(trace_depth)
        
        if not is_valid_path:
            opportunity.is_executable = False
            opportunity.rejection_reason = f"Depth validation failed: {reason}"
            return opportunity
        
        # Continue to steps 4-6 with pool reserves
        return self._continue_analysis(
            opportunity=opportunity,
            pool1_reserve_in=pool1_reserve_in,
            pool1_reserve_out=pool1_reserve_out,
            fee1_decimal=fee1_decimal,
            pool2_reserve_in=pool2_reserve_in,
            pool2_reserve_out=pool2_reserve_out,
            fee2_decimal=fee2_decimal,
            min_profit_usd=min_profit_usd
        )
    
    def _continue_analysis(
        self,
        opportunity: InstitutionalOpportunity,
        pool1_reserve_in: float,
        pool1_reserve_out: float,
        fee1_decimal: float,
        pool2_reserve_in: float,
        pool2_reserve_out: float,
        fee2_decimal: float,
        min_profit_usd: float
    ) -> Optional[InstitutionalOpportunity]:
        """Continue analysis (Steps 4-6)"""
        
        # ========================================================================
        # STEP 4: GAS ORACLE + OPTIMAL TIP
        # ========================================================================
        step_start = time.time()
        
        gas_snapshot = self.gas_oracle.get_gas_snapshot()
        opportunity.gas_snapshot = gas_snapshot
        
        # Calculate preliminary profit (before gas)
        # Use simple estimate for tip optimization
        gamma1 = 1 - fee1_decimal
        gamma2 = 1 - fee2_decimal
        preliminary_profit = opportunity.optimal_loan_token_units * (
            (gamma1 * gamma2 - 1) * 0.01  # Rough 1% profit estimate
        ) * self.calculate_token_price(opportunity.token_pair)
        
        # Optimize tip
        tip_rec = self.tip_optimizer.optimal_tip(
            snapshot=gas_snapshot,
            p_net_before_gas=preliminary_profit,
            gas_units=350_000  # 2-leg arb + flash loan
        )
        
        opportunity.tip_recommendation = tip_rec
        opportunity.gas_cost_usd = tip_rec.gas_cost_usd
        
        trace_gas = ExecutionTrace(
            timestamp=opportunity.timestamp,
            step_name="Gas + Tip Optimization",
            formula_used="P(fill) = 1/(1+exp(-(tip-μ)/σ)), EV = P(fill)·max(0, P_net-gas)",
            inputs={
                "base_fee_gwei": gas_snapshot.base_fee_gwei,
                "tip_p50_gwei": gas_snapshot.tip_p50_gwei
            },
            outputs={
                "optimal_tip_gwei": tip_rec.optimal_tip_gwei,
                "p_fill": tip_rec.p_fill,
                "gas_cost_usd": tip_rec.gas_cost_usd
            },
            passed=True,
            duration_ms=(time.time() - step_start) * 1000
        )
        opportunity.add_trace(trace_gas)
        
        # ========================================================================
        # STEP 5: FLASH LOAN PROVIDER SELECTION
        # ========================================================================
        step_start = time.time()
        
        # Select optimal flash loan provider
        providers = self.flash_selector.select_providers(
            borrow_token="0x0000000000000000000000000000000000000000",  # Placeholder
            loan_amount_usd=opportunity.optimal_loan_amount,
            expected_profit_usd=preliminary_profit,
            gas_cost_usd=opportunity.gas_cost_usd
        )
        
        # Use Balancer if available (0% fee)
        if providers:
            best_provider = providers[0]
            opportunity.flash_provider = best_provider.name
            opportunity.flash_fee_bps = best_provider.fee_bps
            opportunity.flash_fee_usd = opportunity.optimal_loan_amount * (best_provider.fee_bps / 10_000)
        else:
            # Fallback to Balancer
            opportunity.flash_provider = "Balancer Vault"
            opportunity.flash_fee_bps = 0
            opportunity.flash_fee_usd = 0
        
        trace_flash = ExecutionTrace(
            timestamp=opportunity.timestamp,
            step_name="Flash Loan Provider Selection",
            formula_used="Select min(fee) provider with token support",
            inputs={
                "loan_amount_usd": opportunity.optimal_loan_amount
            },
            outputs={
                "provider": opportunity.flash_provider,
                "fee_bps": opportunity.flash_fee_bps,
                "fee_usd": opportunity.flash_fee_usd
            },
            passed=True,
            duration_ms=(time.time() - step_start) * 1000
        )
        opportunity.add_trace(trace_flash)
        
        # ========================================================================
        # STEP 6: SSOT PIPELINE VALIDATION
        # ========================================================================
        step_start = time.time()
        
        # Total costs
        c_total_usd = (
            opportunity.flash_fee_usd +
            opportunity.gas_cost_usd
        )
        
        # Run SSOT pipeline for final validation
        pipeline_result = self.ssot_finalizer.run(
            r1_in=pool1_reserve_in,
            r1_out=pool1_reserve_out,
            fee1=fee1_decimal,
            r2_in=pool2_reserve_in,
            r2_out=pool2_reserve_out,
            fee2=fee2_decimal,
            c_total=c_total_usd,
            p_fill=opportunity.tip_recommendation.p_fill,
            n_batch_runs=100
        )
        
        opportunity.pipeline_result = pipeline_result
        opportunity.net_profit_usd = pipeline_result.p_net_det
        opportunity.ev = pipeline_result.ev
        opportunity.c2_decision = pipeline_result.c2_decision.value
        opportunity.gross_profit_usd = pipeline_result.p_net_det + c_total_usd
        
        if opportunity.optimal_loan_amount > 0:
            opportunity.roi_percent = (opportunity.net_profit_usd / opportunity.optimal_loan_amount) * 100
        
        trace_ssot = ExecutionTrace(
            timestamp=opportunity.timestamp,
            step_name="SSOT Pipeline Validation",
            formula_used="4 Invariants (ε=1e-9) + Batch Sim (N=100) + C2 Decision",
            inputs={
                "c_total": c_total_usd,
                "p_fill": opportunity.tip_recommendation.p_fill
            },
            outputs={
                "p_net_det": pipeline_result.p_net_det,
                "ev": pipeline_result.ev,
                "c2_decision": pipeline_result.c2_decision.value,
                "audit_passed": pipeline_result.audit_result.passed if pipeline_result.audit_result else False
            },
            passed=pipeline_result.is_executable,
            reason=pipeline_result.rejection_reason if not pipeline_result.is_executable else None,
            duration_ms=(time.time() - step_start) * 1000
        )
        opportunity.add_trace(trace_ssot)
        
        # Final executability check
        opportunity.is_executable = (
            pipeline_result.is_executable and
            opportunity.net_profit_usd >= min_profit_usd
        )
        
        if not opportunity.is_executable:
            if opportunity.net_profit_usd < min_profit_usd:
                opportunity.rejection_reason = f"Profit ${opportunity.net_profit_usd:.2f} < min ${min_profit_usd}"
            else:
                opportunity.rejection_reason = pipeline_result.rejection_reason
        
        return opportunity
    
    def calculate_token_price(self, token_pair: str) -> float:
        """Quick token price estimate - placeholder"""
        # TODO: Use real price oracle
        if "USDC" in token_pair or "USDT" in token_pair or "DAI" in token_pair:
            return 1.0
        elif "WETH" in token_pair:
            return 2500.0
        elif "WMATIC" in token_pair:
            return 0.85
        return 1.0


# Global instance
_coordinator = None

def get_institutional_coordinator(w3: Web3) -> InstitutionalMathCoordinator:
    """Get or create coordinator singleton"""
    global _coordinator
    if _coordinator is None:
        _coordinator = InstitutionalMathCoordinator(w3)
    return _coordinator
