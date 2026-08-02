#!/usr/bin/env python3
# ==============================================================================
# apex_live_design.py -- production-safe concepts imported from apex-scan archive.
#
# The archive is treated as design input only. No mock pools, fake hashes, random
# PnL, placeholder invariant math, or simulated reserve paths are imported into
# runtime execution.
# ==============================================================================

from __future__ import annotations

from pathlib import Path
from typing import Any

from .transport_lanes import LANES


ARCHIVE_NAME = "apex-scan-official-live1.zip"
EXTRACTED_ARCHIVE_PATH = Path("out/imports/apex-scan-official-live1")
FINALIZER_SKILL_NAME = "apex-pipeline-mainnet-finalizer.zip"

ACCEPTED_CONCEPTS: list[dict[str, str]] = [
    {
        "concept": "32-lane operations grid",
        "runtime_mapping": "omega_v5.transport_lanes.LANES",
        "integration": "accepted_existing_live_redis_transport",
    },
    {
        "concept": "C1/C2 execution observability",
        "runtime_mapping": "omega_v5.execution_trace and omega_v5.pnl_tracker",
        "integration": "accepted_existing_receipt_trace_pnl_surfaces",
    },
    {
        "concept": "normalized executable quote display",
        "runtime_mapping": "LiveOpportunity.metadata.raw_spread_engine.normalized_quote",
        "integration": "accepted_live_quote_math_only",
    },
    {
        "concept": "liquidation monitor panel",
        "runtime_mapping": "omega_v5.aave_liquidations and liquidation_execution",
        "integration": "accepted_fail_closed_scanner_and_payload_status",
    },
    {
        "concept": "operator configuration surface",
        "runtime_mapping": "omega_v5.runtime_control",
        "integration": "accepted_live_dry_runtime_controls_with_backend_guards",
    },
    {
        "concept": "oracle and RPC health telemetry",
        "runtime_mapping": "omega_v5.oracle_layer and omega_v5.transport_lanes",
        "integration": "accepted_live_status_only",
    },
    {
        "concept": "dynamic pool registry metadata import",
        "runtime_mapping": "omega_v5.external_pool_registry -> omega_v5.rpc_layer.discover_factory_pool_registry",
        "integration": "accepted_metadata_only_live_rpc_state_required",
    },
    {
        "concept": "oracle feed dashboard panel",
        "runtime_mapping": "GET /api/oracles/prices and frontend_integration/OmegaRuntimePanel.tsx",
        "integration": "accepted_backend_live_oracle_snapshot_no_frontend_mock_prices",
    },
    {
        "concept": "mainnet finalizer verdict",
        "runtime_mapping": "omega_v5.mainnet_finalizer and GET /api/finalizer/report",
        "integration": "accepted_consolidated_readiness_report_no_broadcast",
    },
    {
        "concept": "frontend execution manager ergonomics",
        "runtime_mapping": "frontend_integration/ExecutionManager.ts -> Omega backend API",
        "integration": "accepted_api_facade_only_no_browser_signing",
    },
]

REJECTED_ARCHIVE_SURFACES: list[dict[str, str]] = [
    {
        "surface": "ExecutionManager.ts fake transaction hashes",
        "reason": "uses Math.random to create non-retrievable hashes",
    },
    {
        "surface": "server.ts dummy pool generation and fallback reserves",
        "reason": "creates synthetic pools/reserves instead of live on-chain state",
    },
    {
        "surface": "server.ts /api/arbitrage/simulate route",
        "reason": "mixes live reads with fallback reserve execution estimates",
    },
    {
        "surface": "server.ts C2 random profit and random route IDs",
        "reason": "not sourced from C1 receipt or current pool state",
    },
    {
        "surface": "server/engine/invariants.ts Balancer placeholder math",
        "reason": "amountIn fee-only placeholder is not weighted-invariant math",
    },
    {
        "surface": "src components with Math.random charts/PnL/opportunity IDs",
        "reason": "operator UI must display backend proof data only",
    },
    {
        "surface": "config.json hardcoded executor/RPC values",
        "reason": "contains malformed and stale sample configuration; runtime uses .env/config.py",
    },
    {
        "surface": "rust-bridge optimistic Shadow Gate placeholder profits",
        "reason": "returns simulated C1/C2 profit and gas instead of exact fork or eth_call proof",
    },
    {
        "surface": "COMPLETE_SYSTEM_BLUEPRINT static wallet/gas/profit projections",
        "reason": "contains stale and optimistic financial assumptions; runtime uses live gas station and oracle data",
    },
]

NORMALIZED_QUOTE_REQUIRED_FIELDS = [
    "schema",
    "accounting",
    "baseToken",
    "midToken",
    "flashPrincipalRaw",
    "buyAmountInRaw",
    "buyAmountOutRaw",
    "sellAmountInRaw",
    "sellAmountOutRaw",
    "sellAmountInEqualsBuyAmountOut",
    "executableBuyPriceUsdPerMid",
    "executableSellPriceUsdPerMid",
    "priceDeltaUsdPerMid",
    "grossProfitRaw",
    "flashFeeRaw",
    "gasCostRaw",
    "relayCostRaw",
    "safetyBufferRaw",
    "otherCostsRaw",
    "minimumProfitRaw",
    "netProfitRaw",
    "executableInequalityPass",
]

ACCOUNTING_V2_REQUIRED_SECTIONS = [
    "route",
    "principal",
    "leg1_buy",
    "leg2_sell",
    "spread",
    "delta",
    "expenses",
    "raw_execution_gate",
    "raw_profit",
]


def live_design_status() -> dict[str, Any]:
    """Return production-safe design integration status for API/UI use."""
    lane_rows = [
        {
            "lane_id": lane.lane_id,
            "name": lane.name,
            "kind": lane.kind,
            "stream": lane.stream,
            "endpoint_role": lane.endpoint_role,
            "max_rps": lane.max_rps,
        }
        for lane in sorted(LANES.values(), key=lambda item: item.lane_id)
    ]
    return {
        "source_archive": ARCHIVE_NAME,
        "source_finalizer_skill": FINALIZER_SKILL_NAME,
        "integration_policy": {
            "archive_code_executed": False,
            "mock_data_imported": False,
            "synthetic_reserves_allowed": False,
            "random_pnl_allowed": False,
            "fake_hashes_allowed": False,
            "runtime_source_of_truth": "live Polygon RPC state plus exact-call/payload proofs",
            "validation_lane_is_not_mock_data": True,
        },
        "accepted_concepts": ACCEPTED_CONCEPTS,
        "rejected_archive_surfaces": REJECTED_ARCHIVE_SURFACES,
        "normalized_quote_required_fields": NORMALIZED_QUOTE_REQUIRED_FIELDS,
        "accounting_v2_required_sections": ACCOUNTING_V2_REQUIRED_SECTIONS,
        "unified_invariant_route_schema": "docs/unified_invariant_route_schema.md",
        "base_pool_registry_schema": "docs/base_pool_registry_schema.md",
        "transport_lanes": {
            "count": len(lane_rows),
            "lanes": lane_rows,
        },
        "purge_status": {
            "extracted_archive_present": EXTRACTED_ARCHIVE_PATH.exists(),
            "runtime_imports_archive_code": False,
        },
    }
