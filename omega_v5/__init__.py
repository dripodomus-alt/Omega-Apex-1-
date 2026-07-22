# ==============================================================================
# __init__.py -- Omega V5 Arbitrage Engine
#
# This file acts as the central index for the Omega V5 package. It makes key
# components available for import at the top level, simplifying access for
# scripts and external tools and ensuring a single source of truth.
# ==============================================================================

# --- Core Modules ---
from . import arbitrage
from . import accounting
from . import adapter_registry
from . import amm_adapters
from . import config
from . import execution
from . import execution_truth
from . import flash_loan
from . import gas_oracle
from . import ml_alpha_ranker
from . import ml_alpha
from . import math_engine
from . import opportunity_ranker
from . import oracle_layer
from . import pool_quality
from . import ranker
from . import rpc_layer
from . import route_execution_stager
from . import state_machine
from . import stable_strategies
from . import sizing

# --- Deferred Imports (to avoid circular dependencies) ---
from . import liquidation_watcher

# --- Key Class & Function Exports ---
from .arbitrage import ArbitrageGraphEngine
from .config import get_config_value
from .execution_truth import final_truth_rank, truth_summary
from .gas_oracle import base_fee_gwei
from .ml_alpha_ranker import rerank_with_vqc as rerank_by_ml_alpha
from .opportunity_ranker import (
    LiveOpportunity,
    print_live_opportunities,
    score_cross_pool_spreads,
    score_opportunities,
    score_pegged_stable_spreads,
)
from .payload_envelope import (
    UNIFIED_ROUTE_SCHEMA_VERSION,
    UnifiedRouteEnvelope,
    add_payload_to_unified_envelope,
    add_staging_to_unified_envelope,
    build_unified_route_envelope,
    unified_envelope_from_live_opportunity,
    unified_envelope_from_pre_ranked,
)
from .ranker import compute_all_pool_rates, detect_cross_pool_two_leg_spreads
from .route_execution_stager import build_route_identity, freeze_staged_opportunity_id
from .rpc_layer import DEEP_POOL_REGISTRY
from .stable_strategies import detect_pegged_stable_spreads