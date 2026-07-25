#!/usr/bin/env python3
# ==============================================================================
# dashboard_endpoints.py -- API endpoints to power the high-fidelity UI
#
# This module provides the data structures and API routes necessary to feed
# the visionary "Discovery Card" based dashboard. It serves structured,
# ready-to-render data for pools, routes, and liquidations.
# ==============================================================================

from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

# --- Mock/Placeholder Imports ---
# In a real implementation, these would be the actual engine components
# that hold the live, in-memory state of the system.
from ..engine import get_discovery_engine_instance, get_liquidation_scanner_instance
from ..opportunity_ranker import LiveOpportunity
from ..aave_liquidations import ApexLiquidationCandidatePacket


router = APIRouter()

# ==============================================================================
# 1. Pydantic Models for "Discovery ID Cards"
# These models define the exact structure of the data for each card in the UI.
# ==============================================================================

class PoolDiscoveryCard(BaseModel):
    """Data for a single liquidity pool card in the UI."""
    pool_id: str = Field(..., description="Unique identifier for the pool.")
    protocol: str = Field(..., description="AMM protocol (e.g., UniswapV3, Curve).")
    asset_x: str = Field(..., description="Symbol of the first token in the pair.")
    asset_y: str = Field(..., description="Symbol of the second token in the pair.")
    fee_tier_bps: Optional[int] = Field(None, description="Fee tier in basis points (for V3 pools).")
    tvl_usd: Decimal = Field(..., description="Total value locked in the pool, in USD.")
    volume_24h_usd: Decimal = Field(..., description="Trading volume in the last 24 hours, in USD.")
    is_stable: bool = Field(False, description="Indicates if this is a stable-swap pool.")

    class Config:
        orm_mode = True
        json_encoders = {Decimal: lambda v: f"{v:.4f}"}


class RouteDiscoveryCard(BaseModel):
    """Data for a single arbitrage route card in the UI."""
    route_signature: str = Field(..., description="A unique, human-readable signature for the route.")
    path: List[str] = Field(..., description="The sequence of tokens in the arbitrage path.")
    protocols: List[str] = Field(..., description="The sequence of protocols used in the path.")
    estimated_profit_usd: Decimal = Field(..., description="Estimated net profit for this route in USD.")
    vqc_score: float = Field(..., description="The VQC model's probability score for successful execution.")
    optimal_size_usd: Decimal = Field(..., description="The dynamically calculated optimal trade size in USD.")

    class Config:
        orm_mode = True
        json_encoders = {Decimal: lambda v: f"{v:.2f}"}


class LiquidationDiscoveryCard(BaseModel):
    """Data for a single Aave liquidation candidate card in the UI."""
    borrower: str = Field(..., description="The address of the account being liquidated.")
    health_factor: Decimal = Field(..., description="The borrower's health factor (below 1.0 is liquidatable).")
    debt_asset: str = Field(..., description="The asset being repaid.")
    collateral_asset: str = Field(..., description="The collateral asset being seized.")
    net_profit_usd: Decimal = Field(..., description="The estimated net profit from this liquidation in USD.")
    exit_route: List[str] = Field(..., description="The swap path to exit the seized collateral.")

    class Config:
        orm_mode = True
        json_encoders = {Decimal: lambda v: f"{v:.2f}"}


# ==============================================================================
# 2. API Endpoints
# These endpoints will be called by the frontend to fetch data for the dashboard.
# ==============================================================================

@router.get("/dashboard/pools", response_model=List[PoolDiscoveryCard], tags=["Dashboard"])
async def get_pool_discovery_cards(
    engine = Depends(get_discovery_engine_instance) # Dependency injection to get live engine state
):
    """
    Provides a list of all active, discovered liquidity pools, formatted for the
    high-fidelity "Pool Discovery Card" UI component.
    """
    # This is a placeholder for fetching real data from the discovery engine's pool registry.
    # In a real implementation, you would iterate through `engine.pool_registry.values()`.
    mock_pools = [
        PoolDiscoveryCard(pool_id="0x123-USDC-WETH", protocol="UniswapV3", asset_x="USDC", asset_y="WETH", fee_tier_bps=5, tvl_usd=Decimal("12.5e6"), volume_24h_usd=Decimal("30.1e6")),
        PoolDiscoveryCard(pool_id="curve-tripool", protocol="Curve", asset_x="DAI", asset_y="USDC", tvl_usd=Decimal("88.2e6"), volume_24h_usd=Decimal("45.6e6"), is_stable=True),
    ]
    return mock_pools


@router.get("/dashboard/routes", response_model=List[RouteDiscoveryCard], tags=["Dashboard"])
async def get_route_discovery_cards(
    engine = Depends(get_discovery_engine_instance)
):
    """
    Provides a list of the top-ranked arbitrage opportunities, formatted for
    the "Route Discovery Card" UI component.
    """
    # Placeholder for fetching real, VQC-reranked opportunities from the engine.
    # In a real implementation, you would access `engine.get_ranked_opportunities()`.
    mock_routes = [
        RouteDiscoveryCard(route_signature="USDC-WETH-USDC_UniV3-Sushi", path=["USDC", "WETH", "USDC"], protocols=["UniswapV3", "Sushiswap"], estimated_profit_usd=Decimal("25.50"), vqc_score=0.92, optimal_size_usd=Decimal("50000")),
        RouteDiscoveryCard(route_signature="DAI-CRV-DAI_Curve-Balancer", path=["DAI", "CRV", "DAI"], protocols=["Curve", "Balancer"], estimated_profit_usd=Decimal("12.75"), vqc_score=0.85, optimal_size_usd=Decimal("25000")),
    ]
    return mock_routes


@router.get("/dashboard/liquidations", response_model=List[LiquidationDiscoveryCard], tags=["Dashboard"])
async def get_liquidation_discovery_cards(
    scanner = Depends(get_liquidation_scanner_instance)
):
    """
    Provides a list of the most profitable Aave liquidation candidates, formatted
    for the "Liquidation Discovery Card" UI component.
    """
    # Placeholder for fetching real liquidation candidates from the scanner.
    # In a real implementation, you would call `scanner.scan()` and format the results.
    mock_liquidations = [
        LiquidationDiscoveryCard(borrower="0x...baddebt", health_factor=Decimal("0.94"), debt_asset="USDC", collateral_asset="WETH", net_profit_usd=Decimal("125.30"), exit_route=["WETH", "USDC"]),
    ]
    return mock_liquidations