#!/usr/bin/env python3
# ==============================================================================
# sourced_layers.py -- Optional external intelligence and permissioning surfaces.
#
# These layers may enrich discovery, accounting, and operator workflows. They are
# not execution-truth sources. Route executability still comes from canonical RPC
# reads, exact eth_call, fork simulation, and isolated broadcast.
# ==============================================================================

from __future__ import annotations

from typing import Any

from .config import (
    BALANCER_API_URL,
    DRPC_DATA_API_KEY,
    DRPC_DATA_API_URL,
    DRPC_DATA_CACHE_TTL_SECONDS,
    ENABLE_DRPC_DATA_API,
    ENABLE_NODECORE,
    ENABLE_SMART_SESSIONS,
    MORALIS_API,
    MORALIS_API_KEY,
    NODECORE_HTTP_URL,
    NODECORE_WSS_URL,
    SESSION_PROOF_SAMPLES,
    SESSION_SIGNER_ENABLED,
    SESSION_SIGNER_MODE,
    SMART_SESSIONS_ALLOWED_SELECTORS,
    SMART_SESSIONS_ALLOWED_TARGETS,
    SMART_SESSIONS_CREDENTIAL_ID,
    SMART_SESSIONS_MAX_VALUE_WEI,
    SMART_SESSIONS_WAAS_API_URL,
    SMART_SESSIONS_WALLET_ID,
    WAAS_BROADCAST_ADAPTER_ENABLED,
    WAAS_BROADCAST_ADAPTER_MODE,
)
from .session_proof import load_latest_proof
from .ml_alpha import ml_alpha_status
from .transport_lanes import _mask_url


def _masked_present(value: str) -> bool:
    return bool(str(value or "").strip())


def sourced_layer_status() -> dict[str, Any]:
    return {
        "execution_truth_policy": {
            "indexed_data_authoritative_for_execution": False,
            "smart_sessions_in_hot_path": False,
            "broadcast_isolated_from_read_rotation": True,
        },
        "nodecore": {
            "enabled": ENABLE_NODECORE,
            "http_url": _mask_url(NODECORE_HTTP_URL),
            "wss_url": _mask_url(NODECORE_WSS_URL),
            "role": "optional local RPC gateway; safe for read/WSS/fork lanes when healthy",
            "broadcast_policy": "enabled only through BROADCAST_RPC_URL or BROADCAST_RPC_FALLBACK_URLS after Chain 137 and eth_sendRawTransaction method probes",
        },
        "drpc_data_api": {
            "enabled": ENABLE_DRPC_DATA_API,
            "api_url": _mask_url(DRPC_DATA_API_URL),
            "api_key_present": _masked_present(DRPC_DATA_API_KEY),
            "cache_ttl_seconds": DRPC_DATA_CACHE_TTL_SECONDS,
            "role": "indexed wallet/portfolio/position enrichment",
            "execution_authority": False,
        },
        "moralis": {
            "api_url": _mask_url(MORALIS_API),
            "api_key_present": _masked_present(MORALIS_API_KEY),
            "role": "indexed wallet/token/position enrichment and cross-checking",
            "execution_authority": False,
        },
        "balancer_api": {
            "api_url": _mask_url(BALANCER_API_URL),
            "role": "off-chain pool metadata enrichment; on-chain vault reads remain execution truth",
            "execution_authority": False,
        },
        "smart_sessions": {
            "enabled": ENABLE_SMART_SESSIONS,
            "session_signer_enabled": SESSION_SIGNER_ENABLED,
            "session_signer_mode": SESSION_SIGNER_MODE,
            "waas_broadcast_adapter_enabled": WAAS_BROADCAST_ADAPTER_ENABLED,
            "waas_broadcast_adapter_mode": WAAS_BROADCAST_ADAPTER_MODE,
            "waas_api_url": _mask_url(SMART_SESSIONS_WAAS_API_URL),
            "credential_configured": _masked_present(SMART_SESSIONS_CREDENTIAL_ID),
            "wallet_configured": _masked_present(SMART_SESSIONS_WALLET_ID),
            "allowed_target_count": len(SMART_SESSIONS_ALLOWED_TARGETS),
            "allowed_selector_count": len(SMART_SESSIONS_ALLOWED_SELECTORS),
            "max_value_wei": SMART_SESSIONS_MAX_VALUE_WEI,
            "proof_samples": SESSION_PROOF_SAMPLES,
            "latest_proof": {
                key: value
                for key, value in load_latest_proof().items()
                if key in {"ok", "status", "generated_at_unix", "latency_summary", "definition_of_done"}
            },
            "role": "optional delegated wallet permissioning; not C1/C2 execution truth",
            "execution_authority": False,
            "hot_path_enabled": False,
        },
        "ml_alpha": {
            **ml_alpha_status(),
            "role": "optional ranking, sizing, and gas/MEV policy intelligence",
            "execution_authority": False,
            "hot_path_policy": "ML may prioritize candidates only after model-card proof; exact-call and runtime guards remain authoritative",
        },
    }
