"""
APEX_OMEGA Unified Strategy API Endpoints
Exposes all MEV strategies through unified interface

Strategies:
- /api/unified/arbitrage - Cross-DEX arbitrage (C1)
- /api/unified/dual-punch - Dual-Punch recursive (C2 + Shadow Gate)
- /api/unified/liquidation - Aave liquidations (C2)
- /api/unified/sandwich - Mempool sandwich
- /api/unified/status - Overall system status
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal, Optional, Dict, List
import logging

from unified_strategy_controller import get_unified_controller, StrategyType, Opportunity
from mempool_monitor import get_mempool_monitor
from liquidation_hunter import get_liquidation_hunter
from execution_governance import get_minimum_net_profit_usd

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/unified", tags=["Unified Strategies"])


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class ArbitrageRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    pair: str
    dex_in: str
    dex_out: str
    amount_in: float
    reserve_in_dex1: float
    reserve_out_dex1: float
    reserve_in_dex2: float
    reserve_out_dex2: float
    fee_dex1: float = 0.003
    fee_dex2: float = 0.003
    flash_loan: Optional[Dict] = Field(default=None, alias='flashLoan')
    execution_mode: Literal['accepted', 'confirmed'] = 'confirmed'


class DualPunchRequest(BaseModel):
    pair: str
    amount_in: float
    entry_price: float
    target_price: float
    liquidity: float
    current_price: float = 1.0
    volatility_1h: float = 0.01
    volatility_24h: float = 0.02


class LiquidationRequest(BaseModel):
    borrower: str
    health_factor: float
    collateral_value_usd: float
    debt_value_usd: float
    collateral_asset: str
    debt_asset: str
    min_profit_bps: int = Field(default=50, ge=0, le=10_000)
    execution_mode: Literal['accepted', 'confirmed'] = 'confirmed'


# ============================================================================
# RESPONSE HELPERS
# ============================================================================

def _raise_if_execution_failed(result: Dict) -> Dict:
    """Only let execution endpoints return success=true after real acceptance/confirmation."""
    if result.get("success") is True:
        return result

    detail = {
        "success": False,
        "error": result.get("error") or result.get("reason") or "execution failed",
        "tx_hash": result.get("tx_hash"),
        "receipt_status": result.get("receipt_status"),
        "gas_used": result.get("gas_used"),
        "revert_reason": result.get("revert_reason"),
    }
    raise HTTPException(status_code=502, detail=detail)


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("/status")
async def get_unified_status():
    """
    Get overall system status for all strategies.
    """
    controller = get_unified_controller()
    mempool = get_mempool_monitor()
    hunter = get_liquidation_hunter()
    
    stats = controller.get_stats()
    mempool_stats = mempool.get_stats()
    liquidation_stats = hunter.get_stats()
    
    return {
        "unified_controller": {
            "strategies": stats['strategies'],
            "total_executed": stats['total_executed'],
            "total_profit_usd": stats['total_profit'],
            "total_failed": stats['total_failed']
        },
        "mempool_monitor": {
            "total_txs_seen": mempool_stats['total_txs_seen'],
            "swap_txs_seen": mempool_stats['swap_txs_seen'],
            "sandwich_candidates": mempool_stats['sandwich_candidates']
        },
        "liquidation_hunter": {
            "positions_scanned": liquidation_stats['positions_scanned'],
            "unhealthy_positions": liquidation_stats['unhealthy_positions'],
            "liquidation_candidates": liquidation_stats['liquidation_candidates'],
            "total_value_at_risk": liquidation_stats['total_value_at_risk']
        },
        "deployed_contracts": {
            "c1_primary": controller.c1_primary,
            "c1_secondary": controller.c1_secondary,
            "c2_liquidation": controller.c2_liquidation
        }
    }


@router.post("/arbitrage/evaluate")
async def evaluate_arbitrage(request: ArbitrageRequest):
    """
    Evaluate cross-DEX arbitrage opportunity.
    
    Routes to C1 contract if profitable.
    """
    controller = get_unified_controller()
    
    pool_data = {
        'pair': request.pair,
        'dex_in': request.dex_in,
        'dex_out': request.dex_out,
        'reserve_in_dex1': request.reserve_in_dex1,
        'reserve_out_dex1': request.reserve_out_dex1,
        'reserve_in_dex2': request.reserve_in_dex2,
        'reserve_out_dex2': request.reserve_out_dex2,
        'fee_dex1': request.fee_dex1,
        'fee_dex2': request.fee_dex2,
        'liquidity': min(request.reserve_in_dex1 + request.reserve_out_dex1,
                        request.reserve_in_dex2 + request.reserve_out_dex2)
    }
    
    opportunity = await controller.evaluate_opportunity(
        StrategyType.CROSS_DEX_ARB,
        pool_data,
        request.amount_in
    )
    
    if opportunity is None:
        return {
            "profitable": False,
            "reason": f"Net profit after costs below ${get_minimum_net_profit_usd():.2f} threshold"
        }
    
    return {
        "profitable": True,
        "opportunity": {
            "pair": opportunity.pair,
            "dex_in": opportunity.dex_in,
            "dex_out": opportunity.dex_out,
            "amount_in": opportunity.amount_in,
            "expected_profit": opportunity.expected_profit,
            "spread_bps": opportunity.spread_bps,
            "gas_cost": opportunity.gas_cost
        }
    }


@router.post("/arbitrage/execute")
async def execute_arbitrage(request: ArbitrageRequest):
    """
    Execute cross-DEX arbitrage via C1 contract.
    """
    controller = get_unified_controller()
    
    # First evaluate
    pool_data = {
        'pair': request.pair,
        'dex_in': request.dex_in,
        'dex_out': request.dex_out,
        'reserve_in_dex1': request.reserve_in_dex1,
        'reserve_out_dex1': request.reserve_out_dex1,
        'reserve_in_dex2': request.reserve_in_dex2,
        'reserve_out_dex2': request.reserve_out_dex2,
        'fee_dex1': request.fee_dex1,
        'fee_dex2': request.fee_dex2,
        'liquidity': min(request.reserve_in_dex1 + request.reserve_out_dex1,
                        request.reserve_in_dex2 + request.reserve_out_dex2)
    }
    
    opportunity = await controller.evaluate_opportunity(
        StrategyType.CROSS_DEX_ARB,
        pool_data,
        request.amount_in
    )
    
    if opportunity is None:
        raise HTTPException(status_code=400, detail="Opportunity not profitable")
    
    opportunity.metadata['flash_loan'] = request.flash_loan
    opportunity.metadata['execution_mode'] = request.execution_mode

    # Execute
    result = await controller.execute_opportunity(opportunity)
    
    return _raise_if_execution_failed(result)


@router.post("/dual-punch/evaluate")
async def evaluate_dual_punch(request: DualPunchRequest):
    """
    Evaluate dual-punch opportunity.
    
    Uses Phase 3 dual-punch manager with Shadow Gate.
    """
    controller = get_unified_controller()
    
    pool_data = {
        'pair': request.pair,
        'entry_price': request.entry_price,
        'target_price': request.target_price,
        'liquidity': request.liquidity,
        'current_price': request.current_price,
        'volatility_1h': request.volatility_1h,
        'volatility_24h': request.volatility_24h
    }
    
    opportunity = await controller.evaluate_opportunity(
        StrategyType.DUAL_PUNCH,
        pool_data,
        request.amount_in
    )
    
    if opportunity is None:
        return {
            "profitable": False,
            "reason": "Dual-punch evaluation aborted"
        }
    
    evaluation = opportunity.metadata['evaluation']
    
    return {
        "profitable": True,
        "decision": evaluation['decision'],
        "opportunity": {
            "c1_profit": evaluation.get('c1_profit', 0),
            "c2_profit": evaluation.get('c2_profit', 0),
            "total_profit": evaluation.get('total_profit', 0),
            "c2_optimal_size": evaluation.get('c2_optimal_size', 0)
        }
    }


@router.post("/dual-punch/execute")
async def execute_dual_punch(request: DualPunchRequest):
    """
    Execute dual-punch via C2 contract + Shadow Gate.
    
    MANDATORY: Shadow Gate simulation before execution.
    """
    controller = get_unified_controller()
    
    pool_data = {
        'pair': request.pair,
        'entry_price': request.entry_price,
        'target_price': request.target_price,
        'liquidity': request.liquidity,
        'current_price': request.current_price,
        'volatility_1h': request.volatility_1h,
        'volatility_24h': request.volatility_24h
    }
    
    opportunity = await controller.evaluate_opportunity(
        StrategyType.DUAL_PUNCH,
        pool_data,
        request.amount_in
    )
    
    if opportunity is None:
        raise HTTPException(status_code=400, detail="Dual-punch not profitable")
    
    # Execute with Shadow Gate enforcement
    result = await controller.execute_opportunity(opportunity)
    
    return _raise_if_execution_failed(result)


@router.get("/liquidation/scan")
async def scan_liquidations():
    """
    Scan Aave V3 for liquidation opportunities.
    """
    hunter = get_liquidation_hunter()
    
    await hunter.scan_positions()
    
    stats = hunter.get_stats()
    
    return {
        "scan_complete": True,
        "positions_scanned": stats['positions_scanned'],
        "unhealthy_positions": stats['unhealthy_positions'],
        "liquidation_candidates": stats['liquidation_candidates'],
        "total_value_at_risk": stats['total_value_at_risk']
    }


@router.post("/liquidation/execute")
async def execute_liquidation(request: LiquidationRequest):
    """
    Execute liquidation via C2 liquidation contract.
    """
    controller = get_unified_controller()
    
    pool_data = {
        'borrower': request.borrower,
        'health_factor': request.health_factor,
        'collateral_value_usd': request.collateral_value_usd,
        'debt_value_usd': request.debt_value_usd,
        'collateral_asset': request.collateral_asset,
        'debt_asset': request.debt_asset,
        'min_profit_bps': request.min_profit_bps,
        'execution_mode': request.execution_mode
    }
    
    opportunity = await controller.evaluate_opportunity(
        StrategyType.LIQUIDATION,
        pool_data,
        0  # amount_in not used for liquidations
    )
    
    if opportunity is None:
        raise HTTPException(status_code=400, detail="Liquidation not profitable")
    
    opportunity.metadata['min_profit_bps'] = request.min_profit_bps
    opportunity.metadata['execution_mode'] = request.execution_mode

    # Execute
    result = await controller.execute_opportunity(opportunity)
    
    return _raise_if_execution_failed(result)


@router.get("/mempool/stats")
async def get_mempool_stats():
    """
    Get mempool monitoring statistics.
    """
    mempool = get_mempool_monitor()
    
    return mempool.get_stats()


@router.get("/strategies/stats")
async def get_strategy_stats():
    """
    Get execution statistics for all strategies.
    """
    controller = get_unified_controller()
    
    return controller.get_stats()
