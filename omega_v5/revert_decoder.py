#!/usr/bin/env python3
# ==============================================================================
# revert_decoder.py -- local custom-error selector decoding for fork simulations.
# ==============================================================================

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


CUSTOM_ERROR_SELECTORS = {
    "0x30cd7471": "NotOwner()",
    "0x118cdaa7": "OwnableUnauthorizedAccount(address)",
    "0x82b42900": "Unauthorized()",
    "0x5fc483c5": "OnlyOwner()",
    "0xc5f2be51": "ReentrancyDetected()",
    "0xfbf66df1": "InvalidAdapter()",
    "0x1138620d": "InvalidFlashSource()",
    "0xd433008b": "MinProfitNotMet()",
    "0x08c379a0": "Error(string)",
    "0x51e221b9": "AdapterNotOwner()",
    "0x9e818648": "AdapterNotExecutor()",
    "0x75cb5815": "AdapterBadAddress()",
    "0x039b98f8": "AdapterBadRoute()",
    "0xf798ac34": "AdapterBadPoolKind()",
    "0xa505f6a3": "AdapterPoolKindUnset(address)",
    "0x5544ebcb": "AdapterUnsupportedPool(address)",
    "0x01ecd1cc": "AdapterSlippageOrProfit()",
    "0xb11a1c46": "AdapterCallbackSender()",
    "0xb8ea4ff1": "AdapterCallbackToken()",
    "0x6fe13205": "AdapterTransferFailed()",
    "0x58f3dbd7": "AdapterAmountTooLarge()",
    "0x291b2e4f": "BalancerCallbackSender()",
    "0x78274d70": "BalancerCallbackState()",
    "0x43f84f96": "BalancerCallbackAsset()",
}


@dataclass(frozen=True)
class DecodedRevert:
    selector: str
    signature: str
    raw: str


def extract_selector(value: object) -> Optional[str]:
    text = str(value)
    match = re.search(r"0x[0-9a-fA-F]{8}", text)
    return match.group(0).lower() if match else None


def decode_revert(value: object) -> Optional[DecodedRevert]:
    selector = extract_selector(value)
    if not selector:
        return None
    signature = CUSTOM_ERROR_SELECTORS.get(selector, "unknown_custom_error")
    return DecodedRevert(selector=selector, signature=signature, raw=str(value))


def format_revert(value: object) -> str:
    decoded = decode_revert(value)
    if decoded is None:
        return str(value)
    return f"{decoded.signature} selector={decoded.selector}"
