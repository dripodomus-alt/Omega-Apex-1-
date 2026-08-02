"""
APEX_OMEGA Phase 3 API Endpoints
Dual-Punch Strategy, Shadow Gate, ML Retraining
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, Dict
import logging

from dual_punch_manager import get_dual_punch_manager
from rust_bridge_client import get_rust_bridge_client
from execution_logger import get_execution_logger
from slippage_sentinel import get_slippage_sentinel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/phase3", tags=["Phase 3"])


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class DualPunchEvaluationRequest(BaseModel):
    pair: str
    c1_size_usd: float
    c1_entry_price: float
    c1_target_price: float
    pool_liquidity_usd: float
    pool_current_price: float
    volatility_1h: float = 0.01
    volatility_24h: float = 0.02
    gas_cost_usd: float = 0.02


class DualPunchExecutionRequest(BaseModel):
    evaluation: Dict
    pool_address: str
    token0: str
    token1: str
    volatility_1h: float = 0.01
    volatility_24h: float = 0.02
    gas_price_gwei: float = 50


class MLRetrainingRequest(BaseModel):
    force_retrain: bool = False


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("/status")
async def get_phase3_status():
    """
    Get Phase 3 system status.
    """
    try:
        manager = get_dual_punch_manager()
        bridge = get_rust_bridge_client()
        logger_instance = get_execution_logger()
        
        # Check Anvil Shadow Gate
        anvil_status = await bridge.check_anvil_fork()
        
        # Get execution stats
        exec_stats = await logger_instance.get_execution_stats()
        
        # Get strategy stats
        strategy_stats = manager.get_statistics()
        
        return {
            "phase3_enabled": True,
            "anvil_shadow_gate": anvil_status,
            "rust_bridge": {
                "binary_path": "/app/rust-bridge/target/release/apex-omega-bridge",
                "compiled": True,
                "rpc_endpoint": "http://127.0.0.1:9000"
            },
            "ml_pipeline": {
                "total_executions": exec_stats['total_executions'],
                "total_profit_usd": exec_stats['total_profit_usd'],
                "avg_slippage": exec_stats['avg_slippage'],
                "model_trained": True
            },
            "strategy_stats": strategy_stats,
            "thresholds": {
                "min_c1_profit": manager.min_c1_profit,
                "min_dual_profit": manager.min_dual_profit
            }
        }
    
    except Exception as e:
        logger.error(f"Error fetching Phase 3 status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/evaluate")
async def evaluate_dual_punch(request: DualPunchEvaluationRequest):
    """
    Evaluate dual-punch opportunity.
    
    Returns decision: EXECUTE_C1_ONLY, EXECUTE_DUAL_PUNCH, or ABORT
    """
    try:
        manager = get_dual_punch_manager()
        
        evaluation = await manager.evaluate_dual_punch_opportunity(
            pair=request.pair,
            c1_size_usd=request.c1_size_usd,
            c1_entry_price=request.c1_entry_price,
            c1_target_price=request.c1_target_price,
            pool_liquidity_usd=request.pool_liquidity_usd,
            pool_current_price=request.pool_current_price,
            volatility_1h=request.volatility_1h,
            volatility_24h=request.volatility_24h,
            gas_cost_usd=request.gas_cost_usd
        )
        
        return evaluation
    
    except Exception as e:
        logger.error(f"Error evaluating dual-punch: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/execute")
async def execute_dual_punch(request: DualPunchExecutionRequest):
    """
    Execute dual-punch strategy via Rust Bridge + Shadow Gate.
    
    MANDATORY: Shadow Gate simulation must pass before execution.
    """
    try:
        manager = get_dual_punch_manager()
        
        result = await manager.execute_dual_punch(
            evaluation=request.evaluation,
            pool_address=request.pool_address,
            token0=request.token0,
            token1=request.token1,
            volatility_1h=request.volatility_1h,
            volatility_24h=request.volatility_24h,
            gas_price_gwei=request.gas_price_gwei
        )
        
        return result
    
    except Exception as e:
        logger.error(f"Error executing dual-punch: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ml/stats")
async def get_ml_stats():
    """
    Get ML model statistics and execution history.
    """
    try:
        logger_instance = get_execution_logger()
        exec_stats = await logger_instance.get_execution_stats()
        
        return exec_stats
    
    except Exception as e:
        logger.error(f"Error fetching ML stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_execution_history(
    limit: int = Query(50, ge=1, le=500),
    strategy: Optional[str] = Query(None),
    status: Optional[str] = Query(None)
):
    """
    Get persisted execution lifecycle history from MongoDB.
    """
    try:
        logger_instance = get_execution_logger()
        history = await logger_instance.get_execution_history(
            limit=limit,
            strategy=strategy,
            status=status
        )
        return {
            "count": len(history),
            "history": history
        }
    except Exception as e:
        logger.error(f"Error fetching execution history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trace/{execution_id}")
async def get_execution_trace(execution_id: str):
    """
    Get full persisted lifecycle trace for a specific execution ID.
    """
    try:
        logger_instance = get_execution_logger()
        trace = await logger_instance.get_execution_lifecycle_trace(execution_id)
        if not trace:
            raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")
        return trace
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching execution trace {execution_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ml/retrain")
async def trigger_ml_retraining(request: MLRetrainingRequest):
    """
    Trigger ML model retraining on execution history.
    """
    try:
        logger_instance = get_execution_logger()
        sentinel = get_slippage_sentinel()
        
        # Get training data
        training_data = await logger_instance.get_training_data()
        
        if training_data.empty:
            return {
                "retrained": False,
                "reason": "No execution history available"
            }
        
        # Retrain model
        sentinel.retrain_on_execution_data(training_data)
        
        return {
            "retrained": True,
            "executions_used": len(training_data),
            "model_path": str(sentinel.model_path)
        }
    
    except Exception as e:
        logger.error(f"Error retraining ML model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/shadow-gate/status")
async def get_shadow_gate_status():
    """
    Check Anvil Shadow Gate status.
    """
    try:
        bridge = get_rust_bridge_client()
        anvil_status = await bridge.check_anvil_fork()
        
        return anvil_status
    
    except Exception as e:
        logger.error(f"Error checking Shadow Gate: {e}")
        raise HTTPException(status_code=500, detail=str(e))
