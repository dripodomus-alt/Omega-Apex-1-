#!/usr/bin/env python3
# ==============================================================================
# omega_v5/mev.py -- MEV/private relay submission adapter.
#
# This module is a fail-closed adapter. It provides the execution interface for
# private submission and returns an unavailable status until a relay backend is
# explicitly implemented and configured. The execution engine decides whether
# public fallback is allowed by runtime configuration.
# ==============================================================================
from typing import Any, Dict


def submit_and_poll_for_receipt(tx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fail closed when no private relay backend is configured.

    This function provides a compatible interface for the execution loop but
    never fabricates private submission success.

    :param tx: The transaction payload dictionary.
    :return: A dictionary indicating the MEV relay is unavailable.
    """
    return {
        "ok": False,
        "status": "MEV_RELAY_UNAVAILABLE",
        "detail": "No private relay backend is configured.",
        "receipt": None,
        "tx_hash": None,
    }
