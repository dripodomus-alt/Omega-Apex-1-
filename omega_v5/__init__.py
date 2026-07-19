# omega_v5 package
from .config import (
    STABLE_MIN_NET_PROFIT_USD,
    STABLE_RISK_BUFFER_USD,
    ENABLE_STABLE_SWAP_STRATEGIES,
)
from .cycle_shape import (
    FlashCycleShape,
    expand_cycle_shape,
    normalized_cycle_surplus,
    tag_cycle_dict,
)
from .sizing import (
    RouteSizing,
    dynamic_size_optimizer,
    estimate_route_tvl_usd,
    optimal_flash_for_route,
    optimize_principal_with_dynamic,
)
from .flash_loan import evaluate_profitability
from .opportunity_ranker import (
    LiveOpportunity,
    opportunity_to_payload_route,
    score_cross_pool_spreads,
    score_opportunities,
    score_pegged_stable_spreads,
)
from .stable_strategies import PeggedStableSpread, detect_pegged_stable_spreads

SHAPE_FORMULA = (
    "FLASHLOAN_ASSET -> BUY_ANY_MID(ANY_INVARIANT) "
    "[-> ANY_MID(ANY_INVARIANT)]* -> SELL_TO_FLASH(ANY_INVARIANT) -> SURPLUS"
)

__all__ = [
    "dynamic_size_optimizer",
    "estimate_route_tvl_usd",
    "optimal_flash_for_route",
    "optimize_principal_with_dynamic",
    "opportunity_to_payload_route",
    "score_opportunities",
    "score_cross_pool_spreads",
    "score_pegged_stable_spreads",
    "detect_pegged_stable_spreads",
    "expand_cycle_shape",
    "normalized_cycle_surplus",
    "tag_cycle_dict",
    "FlashCycleShape",
    "LiveOpportunity",
    "PeggedStableSpread",
    "RouteSizing",
    "SHAPE_FORMULA",
    "STABLE_MIN_NET_PROFIT_USD",
    "STABLE_RISK_BUFFER_USD",
    "ENABLE_STABLE_SWAP_STRATEGIES",
    "evaluate_profitability",
]
