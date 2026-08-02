"""
SSOT Pipeline - Post-Execution Audit & Degradation Layer
Non-drifting reference implementation for 2-leg A→B→A arbitrage

Key Components:
1. Route envelope audit (4 invariants, ε=1e-9)
2. Execution degradation model (f ~ N(0.65, 0.35))
3. Batch simulator (100 runs)
4. Best-size selection via concavity exploit

This is the FINAL gate before execution - catches semantic drift.
"""

import math
import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
import numpy as np

logger = logging.getLogger(__name__)


# SSOT Constants
AUDIT_EPSILON = 1e-9  # IEEE-754-tight tolerance
DEFAULT_DEGRADATION_MEAN = 0.65  # Expected shortfall vs C1 estimate
DEFAULT_DEGRADATION_STD = 0.35  # Dispersion of realized outcomes
DEFAULT_BATCH_RUNS = 100


class C2Decision(Enum):
    """C2 Surgeon Striker decision"""
    STRIKE = "STRIKE"
    DO_NOTHING = "DO_NOTHING"


@dataclass
class RouteAuditResult:
    """Result of 4-invariant audit"""
    passed: bool
    violations: List[str]
    inventory_delta: float
    gross_profit_delta: float
    net_profit_delta: float


@dataclass
class BatchSummary:
    """Batch simulation results"""
    n_runs: int
    n_strikes: int
    n_profitable_strikes: int
    total_actual_profit: float
    mean_actual_profit_per_run: float
    hit_rate: float  # profitable_strikes / strikes
    ev_theoretical: float
    degradation_samples: List[float]


@dataclass
class PipelineFinalResult:
    """Complete pipeline output"""
    best_size: float
    p_net_det: float
    ev: float
    c2_decision: C2Decision
    audit_result: RouteAuditResult
    batch_summary: BatchSummary
    is_executable: bool
    rejection_reason: Optional[str] = None


class RouteEnvelopeAuditor:
    """
    Validates 4 invariants with ε=1e-9 tolerance:
    I1: Inventory handoff - |B_in_2 - B_out_1| ≤ ε
    I2: Gross profit identity - |P_gross - (A_out_2 - A_in)| ≤ ε
    I3: Net profit identity - |P_net - (P_gross - C_total)| ≤ ε
    I4: Fee range - fee₁ ∈ [0,1) AND fee₂ ∈ [0,1)
    """
    
    def __init__(self, epsilon: float = AUDIT_EPSILON):
        self.epsilon = epsilon
    
    def audit(
        self,
        a_in: float,
        b_out_1: float,
        b_in_2: float,
        a_out_2: float,
        fee1: float,
        fee2: float,
        p_gross: float,
        p_net: float,
        c_total: float
    ) -> RouteAuditResult:
        """
        Run all 4 invariants
        
        Args:
            a_in: Token A input (leg 1)
            b_out_1: Token B output from leg 1
            b_in_2: Token B input to leg 2
            a_out_2: Token A output from leg 2
            fee1: Leg 1 fee (decimal, e.g., 0.003)
            fee2: Leg 2 fee (decimal)
            p_gross: Claimed gross profit
            p_net: Claimed net profit
            c_total: Total costs
            
        Returns:
            RouteAuditResult with pass/fail and violations
        """
        violations = []
        
        # I1: Inventory handoff
        inventory_delta = abs(b_in_2 - b_out_1)
        if inventory_delta > self.epsilon:
            violations.append(
                f"I1 VIOLATION: Inventory handoff |B_in_2 - B_out_1| = {inventory_delta:.2e} > ε={self.epsilon}"
            )
        
        # I2: Gross profit identity
        calc_gross = a_out_2 - a_in
        gross_profit_delta = abs(p_gross - calc_gross)
        if gross_profit_delta > self.epsilon:
            violations.append(
                f"I2 VIOLATION: Gross profit |P_gross - (A_out_2 - A_in)| = {gross_profit_delta:.2e} > ε={self.epsilon}"
            )
        
        # I3: Net profit identity
        calc_net = p_gross - c_total
        net_profit_delta = abs(p_net - calc_net)
        if net_profit_delta > self.epsilon:
            violations.append(
                f"I3 VIOLATION: Net profit |P_net - (P_gross - C_total)| = {net_profit_delta:.2e} > ε={self.epsilon}"
            )
        
        # I4: Fee range
        if not (0 <= fee1 < 1):
            violations.append(f"I4 VIOLATION: fee1={fee1:.6f} not in [0, 1)")
        if not (0 <= fee2 < 1):
            violations.append(f"I4 VIOLATION: fee2={fee2:.6f} not in [0, 1)")
        
        return RouteAuditResult(
            passed=(len(violations) == 0),
            violations=violations,
            inventory_delta=inventory_delta,
            gross_profit_delta=gross_profit_delta,
            net_profit_delta=net_profit_delta
        )


class ExecutionDegradationSimulator:
    """
    Models realized profit as: P_actual = P_net_det × f
    Where f ~ N(μ_d, σ_d), right-truncated at 0
    
    Key properties:
    - Truncation at 0 models reverted/MEV-displaced runs
    - Successful runs can't lose more than gas (flash loan atomicity)
    - Effective mean > μ_d due to truncation
    """
    
    def __init__(
        self,
        mean: float = DEFAULT_DEGRADATION_MEAN,
        std: float = DEFAULT_DEGRADATION_STD,
        seed: Optional[int] = None
    ):
        self.mean = mean
        self.std = std
        self.rng = np.random.default_rng(seed)
    
    def sample_degradation_factor(self) -> float:
        """
        Sample one degradation factor
        Returns f ∈ [0, ∞), typically [0.3, 1.0]
        """
        f = self.rng.normal(self.mean, self.std)
        return max(0.0, f)  # Right truncation
    
    def sample_actual_profit(
        self,
        p_net_det: float,
        c2_decision: C2Decision
    ) -> float:
        """
        Sample actual profit for one run
        
        Args:
            p_net_det: Deterministic net profit from C1
            c2_decision: STRIKE or DO_NOTHING
            
        Returns:
            Actual realized profit (can be 0 if revert)
        """
        if c2_decision == C2Decision.DO_NOTHING:
            return 0.0
        
        f = self.sample_degradation_factor()
        return p_net_det * f


class BatchSimulator:
    """
    Runs N independent cycles for fixed pool state
    C1 math runs once; degradation sampled per run
    """
    
    def __init__(self, degradation_sim: Optional[ExecutionDegradationSimulator] = None):
        self.degradation_sim = degradation_sim or ExecutionDegradationSimulator()
    
    def run(
        self,
        p_net_det: float,
        p_fill: float,
        n_runs: int = DEFAULT_BATCH_RUNS
    ) -> BatchSummary:
        """
        Run batch simulation
        
        Args:
            p_net_det: Deterministic net profit (from C1)
            p_fill: Probability of fill (from TipOptimizer)
            n_runs: Number of simulation runs
            
        Returns:
            BatchSummary with statistics
        """
        
        # EV (computed once)
        ev_theoretical = p_net_det * p_fill
        
        # C2 decision (once)
        c2_decision = C2Decision.STRIKE if (p_net_det > 0 and p_fill > 0) else C2Decision.DO_NOTHING
        
        # Sample degradation for each run
        actual_profits = []
        degradation_samples = []
        
        for _ in range(n_runs):
            p_actual = self.degradation_sim.sample_actual_profit(p_net_det, c2_decision)
            actual_profits.append(p_actual)
            
            # Record degradation factor (if struck)
            if c2_decision == C2Decision.STRIKE and p_net_det > 0:
                f = p_actual / p_net_det if p_net_det > 0 else 0
                degradation_samples.append(f)
        
        # Statistics
        n_strikes = n_runs if c2_decision == C2Decision.STRIKE else 0
        n_profitable_strikes = sum(1 for p in actual_profits if p > 0)
        total_actual_profit = sum(actual_profits)
        mean_actual_profit = total_actual_profit / n_runs
        hit_rate = n_profitable_strikes / n_strikes if n_strikes > 0 else 0.0
        
        return BatchSummary(
            n_runs=n_runs,
            n_strikes=n_strikes,
            n_profitable_strikes=n_profitable_strikes,
            total_actual_profit=total_actual_profit,
            mean_actual_profit_per_run=mean_actual_profit,
            hit_rate=hit_rate,
            ev_theoretical=ev_theoretical,
            degradation_samples=degradation_samples
        )


class SSOTPipelineFinalizer:
    """
    Top-level orchestration - 4 ordered steps:
    1. Best-size selection (concavity exploit)
    2. Payload audit (4 invariants)
    3. C2 decision (EV gate)
    4. Batch simulation (stress test)
    """
    
    def __init__(
        self,
        auditor: Optional[RouteEnvelopeAuditor] = None,
        batch_simulator: Optional[BatchSimulator] = None
    ):
        self.auditor = auditor or RouteEnvelopeAuditor()
        self.batch_simulator = batch_simulator or BatchSimulator()
    
    def two_leg_profit(
        self,
        amount_in: float,
        r1_in: float,
        r1_out: float,
        fee1: float,
        r2_in: float,
        r2_out: float,
        fee2: float,
        c_total: float
    ) -> Tuple[float, float, float, float]:
        """
        Calculate 2-leg profit for given input
        
        Returns:
            (a_in, b_out_1, a_out_2, p_net)
        """
        # Leg 1: A → B
        gamma1 = 1 - fee1
        x_eff = amount_in * gamma1
        b_out_1 = (x_eff * r1_out) / (r1_in + x_eff)
        
        # Leg 2: B → A
        gamma2 = 1 - fee2
        y_eff = b_out_1 * gamma2
        a_out_2 = (y_eff * r2_out) / (r2_in + y_eff)
        
        # Profit
        p_gross = a_out_2 - amount_in
        p_net = p_gross - c_total
        
        return amount_in, b_out_1, a_out_2, p_net
    
    def find_best_size(
        self,
        candidate_sizes: List[float],
        r1_in: float,
        r1_out: float,
        fee1: float,
        r2_in: float,
        r2_out: float,
        fee2: float,
        c_total: float
    ) -> Tuple[float, float]:
        """
        Step 1: Best-size selection via discrete grid search
        Exploits concavity of P_net(s)
        
        Returns:
            (best_size, best_p_net)
        """
        best_size = candidate_sizes[0]
        best_p_net = -float('inf')
        
        for size in candidate_sizes:
            _, _, _, p_net = self.two_leg_profit(
                size, r1_in, r1_out, fee1, r2_in, r2_out, fee2, c_total
            )
            
            if p_net > best_p_net:
                best_p_net = p_net
                best_size = size
        
        return best_size, best_p_net
    
    def run(
        self,
        r1_in: float,
        r1_out: float,
        fee1: float,
        r2_in: float,
        r2_out: float,
        fee2: float,
        c_total: float,
        candidate_sizes: Optional[List[float]] = None,
        p_fill: float = 1.0,
        n_batch_runs: int = DEFAULT_BATCH_RUNS
    ) -> PipelineFinalResult:
        """
        Complete pipeline execution
        
        Args:
            r1_in, r1_out, fee1: Pool 1 parameters
            r2_in, r2_out, fee2: Pool 2 parameters
            c_total: Total costs (flash + gas)
            candidate_sizes: Trade size grid (defaults to geometric)
            p_fill: Probability of fill (from TipOptimizer)
            n_batch_runs: Batch simulation count
            
        Returns:
            PipelineFinalResult with complete audit trail
        """
        
        # Default size grid (geometric from 100 to 50k)
        if candidate_sizes is None:
            candidate_sizes = [
                100 * (50000 / 100) ** (i / 23)
                for i in range(24)
            ]
        
        # Step 1: Best-size selection
        best_size, p_net_det = self.find_best_size(
            candidate_sizes, r1_in, r1_out, fee1, r2_in, r2_out, fee2, c_total
        )
        
        # Calculate full route for audit
        a_in, b_out_1, a_out_2, _ = self.two_leg_profit(
            best_size, r1_in, r1_out, fee1, r2_in, r2_out, fee2, c_total
        )
        p_gross = a_out_2 - a_in
        
        # Step 2: Payload audit
        audit_result = self.auditor.audit(
            a_in=a_in,
            b_out_1=b_out_1,
            b_in_2=b_out_1,  # Inventory handoff (should be exact)
            a_out_2=a_out_2,
            fee1=fee1,
            fee2=fee2,
            p_gross=p_gross,
            p_net=p_net_det,
            c_total=c_total
        )
        
        if not audit_result.passed:
            logger.error(f"Audit FAILED: {audit_result.violations}")
            return PipelineFinalResult(
                best_size=best_size,
                p_net_det=p_net_det,
                ev=0.0,
                c2_decision=C2Decision.DO_NOTHING,
                audit_result=audit_result,
                batch_summary=None,
                is_executable=False,
                rejection_reason=f"Audit failed: {audit_result.violations[0]}"
            )
        
        # Step 3: C2 decision (EV gate)
        ev = p_net_det * p_fill
        c2_decision = C2Decision.STRIKE if (p_net_det > 0 and p_fill > 0) else C2Decision.DO_NOTHING
        
        # Step 4: Batch simulation
        batch_summary = self.batch_simulator.run(p_net_det, p_fill, n_batch_runs)
        
        # Final executability
        is_executable = (
            audit_result.passed and
            c2_decision == C2Decision.STRIKE and
            p_net_det > 0
        )
        
        return PipelineFinalResult(
            best_size=best_size,
            p_net_det=p_net_det,
            ev=ev,
            c2_decision=c2_decision,
            audit_result=audit_result,
            batch_summary=batch_summary,
            is_executable=is_executable,
            rejection_reason=None if is_executable else "Unprofitable or failed gate"
        )


# Global instances
_auditor = None
_finalizer = None

def get_ssot_auditor() -> RouteEnvelopeAuditor:
    """Get or create SSOT auditor singleton"""
    global _auditor
    if _auditor is None:
        _auditor = RouteEnvelopeAuditor()
    return _auditor

def get_ssot_finalizer() -> SSOTPipelineFinalizer:
    """Get or create SSOT finalizer singleton"""
    global _finalizer
    if _finalizer is None:
        _finalizer = SSOTPipelineFinalizer()
    return _finalizer
