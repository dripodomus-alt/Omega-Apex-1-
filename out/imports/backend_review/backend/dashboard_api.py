"""
DASHBOARD API ENDPOINTS
Real-time opportunity tracking, execution traces, network status

Routes:
- GET  /api/opportunities           - List all opportunities (paginated)
- GET  /api/opportunities/:ssn      - Get single opportunity detail
- GET  /api/execution-trace/:ssn    - Get execution trace (formula firing logs)
- GET  /api/network-status          - Get network status (gas, block, RPC)
- GET  /api/pnl-summary             - Get PnL summary (timeframe-based)
- GET  /api/strategies              - Get active strategies (C1, C2, Liquidation)
"""

from fastapi import APIRouter, Query, HTTPException
from typing import Optional, List
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# Create router
dashboard_router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


# ============================================================================
# OPPORTUNITIES ENDPOINTS
# ============================================================================

@dashboard_router.get("/opportunities")
async def get_opportunities(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    status: Optional[str] = Query(None),
    strategy: Optional[str] = Query(None),
    min_profit: Optional[float] = Query(None)
):
    """
    Get paginated list of opportunities
    
    Query params:
    - page: Page number (default 1)
    - limit: Items per page (default 50, max 500)
    - status: Filter by status (SCANNING, VALIDATED, EXECUTING, COMPLETED, REJECTED)
    - strategy: Filter by strategy (C1, C2, LIQUIDATION)
    - min_profit: Minimum profit USD
    
    Returns:
        {
            "opportunities": [...],
            "total": int,
            "page": int,
            "pages": int
        }
    """
    
    try:
        # Get arbitrage engine instance
        from arbitrage_engine import get_arbitrage_engine
        engine = get_arbitrage_engine()
        
        # Get all stored execution traces
        if not hasattr(engine, '_execution_traces'):
            return {
                "opportunities": [],
                "total": 0,
                "page": 1,
                "pages": 0
            }
        
        # Convert OrderedDict to list
        all_opps = list(engine._execution_traces.values())
        
        # Apply filters
        filtered = all_opps
        
        if status:
            filtered = [opp for opp in filtered if getattr(opp, 'status', 'UNKNOWN') == status]
        
        if strategy:
            filtered = [opp for opp in filtered if getattr(opp, 'strategy', 'C1') == strategy]
        
        if min_profit is not None:
            filtered = [opp for opp in filtered if opp.net_profit_usd >= min_profit]
        
        # Sort by timestamp (newest first)
        filtered.sort(key=lambda x: x.timestamp, reverse=True)
        
        # Pagination
        total = len(filtered)
        start = (page - 1) * limit
        end = start + limit
        paginated = filtered[start:end]
        
        # Convert to dict
        opportunities = [opp.to_dict() for opp in paginated]
        
        return {
            "opportunities": opportunities,
            "total": total,
            "page": page,
            "pages": (total + limit - 1) // limit
        }
        
    except Exception as e:
        logger.error(f"Error fetching opportunities: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@dashboard_router.get("/opportunities/{ssn}")
async def get_opportunity(ssn: str):
    """
    Get single opportunity by SSN
    
    Returns complete opportunity with execution trace
    """
    
    try:
        from arbitrage_engine import get_arbitrage_engine
        engine = get_arbitrage_engine()
        
        # Get from execution traces
        opp = engine.get_execution_trace(ssn)
        
        if not opp:
            raise HTTPException(status_code=404, detail=f"Opportunity {ssn} not found")
        
        return opp.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching opportunity {ssn}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@dashboard_router.get("/execution-trace/{ssn}")
async def get_execution_trace(ssn: str):
    """
    Get detailed execution trace for opportunity
    
    Returns:
        {
            "ssn": str,
            "formulas": [...],  # Formula execution logs
            "gates": [...],     # Gate results
            "mermaidSource": str  # Mermaid diagram source
        }
    """
    
    try:
        from arbitrage_engine import get_arbitrage_engine
        engine = get_arbitrage_engine()
        
        opp = engine.get_execution_trace(ssn)
        
        if not opp:
            raise HTTPException(status_code=404, detail=f"Opportunity {ssn} not found")
        
        # Build execution trace response
        formulas = [
            {
                "step": trace.step_name,
                "formula": trace.formula_used,
                "inputs": trace.inputs,
                "outputs": trace.outputs,
                "passed": trace.passed,
                "reason": trace.reason,
                "duration_ms": trace.duration_ms
            }
            for trace in opp.execution_trace
        ]
        
        # Generate Mermaid diagram
        mermaid_source = generate_mermaid_diagram(opp)
        
        return {
            "ssn": ssn,
            "formulas": formulas,
            "gates": [],  # TODO: Extract gate results
            "mermaidSource": mermaid_source
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching execution trace {ssn}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# NETWORK STATUS ENDPOINT
# ============================================================================

@dashboard_router.get("/network-status")
async def get_network_status():
    """
    Get current network status
    
    Returns:
        {
            "blockNumber": int,
            "baseFeeGwei": float,
            "gasPrice": float,
            "rpcLatency": int,
            "mempoolSize": int,
            "networkHealth": float
        }
    """
    
    try:
        from arbitrage_engine import get_arbitrage_engine
        engine = get_arbitrage_engine()
        
        # Get cached gas snapshot
        gas_snapshot = engine.get_cached_gas_snapshot()
        
        if not gas_snapshot:
            # Fallback values
            return {
                "blockNumber": 0,
                "baseFeeGwei": 0,
                "gasPrice": 0,
                "rpcLatency": 0,
                "mempoolSize": 0,
                "networkHealth": 0
            }
        
        # Get current block
        block_number = engine.w3.eth.block_number
        
        return {
            "blockNumber": block_number,
            "baseFeeGwei": gas_snapshot.base_fee_gwei,
            "gasPrice": gas_snapshot.base_fee_gwei + gas_snapshot.tip_p50_gwei,
            "rpcLatency": 12,  # TODO: Measure actual RPC latency
            "mempoolSize": 0,  # TODO: Get mempool size if available
            "networkHealth": 98.0  # TODO: Calculate network health score
        }
        
    except Exception as e:
        logger.error(f"Error fetching network status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# PNL SUMMARY ENDPOINT
# ============================================================================

@dashboard_router.get("/pnl-summary")
async def get_pnl_summary(
    timeframe: str = Query("24h", regex="^(24h|7d|30d|all)$")
):
    """
    Get PnL summary for timeframe
    
    Returns:
        {
            "opportunitiesScanned": int,
            "passedGates": int,
            "executed": int,
            "grossProfit": float,
            "netProfit": float,
            "avgDegradation": float,
            "strategyBreakdown": {...}
        }
    """
    
    try:
        from arbitrage_engine import get_arbitrage_engine
        engine = get_arbitrage_engine()
        
        # Calculate timeframe
        now = datetime.now()
        if timeframe == "24h":
            start_time = now - timedelta(hours=24)
        elif timeframe == "7d":
            start_time = now - timedelta(days=7)
        elif timeframe == "30d":
            start_time = now - timedelta(days=30)
        else:  # all
            start_time = datetime.fromtimestamp(0)
        
        # Get opportunities in timeframe
        if not hasattr(engine, '_execution_traces'):
            return {
                "opportunitiesScanned": 0,
                "passedGates": 0,
                "executed": 0,
                "grossProfit": 0,
                "netProfit": 0,
                "avgDegradation": 0,
                "strategyBreakdown": {}
            }
        
        all_opps = list(engine._execution_traces.values())
        opps_in_timeframe = [
            opp for opp in all_opps
            if datetime.fromtimestamp(opp.timestamp) >= start_time
        ]
        
        # Calculate stats
        passed_gates = sum(1 for opp in opps_in_timeframe if opp.is_executable)
        executed = sum(1 for opp in opps_in_timeframe if hasattr(opp, 'tx_hash') and opp.tx_hash)
        
        gross_profit = sum(opp.gross_profit_usd for opp in opps_in_timeframe if executed)
        net_profit = sum(opp.net_profit_usd for opp in opps_in_timeframe if executed)
        
        # Strategy breakdown
        strategy_breakdown = {}
        for opp in opps_in_timeframe:
            strategy = getattr(opp, 'strategy', 'C1')
            if strategy not in strategy_breakdown:
                strategy_breakdown[strategy] = 0
            if hasattr(opp, 'tx_hash') and opp.tx_hash:
                strategy_breakdown[strategy] += opp.net_profit_usd
        
        return {
            "opportunitiesScanned": len(opps_in_timeframe),
            "passedGates": passed_gates,
            "executed": executed,
            "grossProfit": gross_profit,
            "netProfit": net_profit,
            "avgDegradation": 0.72,  # TODO: Calculate actual degradation
            "strategyBreakdown": strategy_breakdown
        }
        
    except Exception as e:
        logger.error(f"Error calculating PnL: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# STRATEGIES ENDPOINT
# ============================================================================

@dashboard_router.get("/strategies")
async def get_strategies():
    """
    Get active strategies and their stats
    
    Returns:
        {
            "c1": {"enabled": bool, "stats": {...}},
            "c2": {"enabled": bool, "stats": {...}},
            "liquidation": {"enabled": bool, "stats": {...}}
        }
    """
    
    return {
        "c1": {
            "enabled": True,
            "stats": {
                "opportunities_found": 0,
                "executed": 0,
                "success_rate": 0
            }
        },
        "c2": {
            "enabled": True,
            "stats": {
                "opportunities_found": 0,
                "executed": 0,
                "success_rate": 0
            }
        },
        "liquidation": {
            "enabled": True,
            "stats": {
                "opportunities_found": 0,
                "executed": 0,
                "success_rate": 0
            }
        }
    }


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def generate_mermaid_diagram(opp) -> str:
    """Generate Mermaid diagram showing execution flow"""
    
    steps = []
    steps.append("graph TD")
    steps.append("    A[Opportunity Detected] --> B{Profitability Check}")
    
    # Add steps from execution trace
    prev_node = "B"
    node_id = ord('C')
    
    for i, trace in enumerate(opp.execution_trace):
        current_node = chr(node_id)
        node_id += 1
        
        if trace.passed:
            steps.append(f"    {prev_node} -->|Pass| {current_node}[{trace.step_name}]")
            prev_node = current_node
        else:
            reject_node = chr(node_id)
            node_id += 1
            steps.append(f"    {prev_node} -->|Fail| {reject_node}[REJECTED: {trace.reason}]")
            break
    
    # Add final result
    if opp.is_executable:
        final_node = chr(node_id)
        steps.append(f"    {prev_node} --> {final_node}[EXECUTE]")
    
    return "\n".join(steps)
