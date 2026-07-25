#!/usr/bin/env python3
# ==============================================================================
# executable_quotes.py -- on-chain quote alignment before executor eth_call.
#
# The invariant ranker is intentionally broad. This module is intentionally
# narrow: for CLMM legs it asks live Polygon quoters for the exact input amount
# that will be handed to the route adapter, then feeds that amount forward hop by
# hop. If a CLMM quote cannot be proven, the route is not execution-truth
# eligible.
# ==============================================================================

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR
from typing import Any

from web3 import Web3

from .config import normalize_protocol, FULLY_EXECUTABLE_PROTOCOLS
from .contract_deployments import deployment_address
from .math_engine import DeFiEngineMath
from . import rpc_layer
from .rpc_layer import TOKEN_DECIMALS, TOKEN_ADDRESSES


# Canonical CLMM keys only
CLMM_PROTOCOLS = {"V3_CLMM", "QS_V3_ALGEBRA"}
V3_MIN_SQRT_RATIO_PLUS_ONE = 4295128740
V3_MAX_SQRT_RATIO_MINUS_ONE = 1461446703485210103287273052203988822378723970341

_ABI_UNISWAP_V3_QUOTER_V1 = [
    {
        "inputs": [
            {"internalType": "address", "name": "tokenIn", "type": "address"},
            {"internalType": "address", "name": "tokenOut", "type": "address"},
            {"internalType": "uint24", "name": "fee", "type": "uint24"},
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "uint160", "name": "sqrtPriceLimitX96", "type": "uint160"},
        ],
        "name": "quoteExactInputSingle",
        "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]

_ABI_ALGEBRA_QUOTER = [
    {
        "inputs": [
            {"internalType": "address", "name": "tokenIn", "type": "address"},
            {"internalType": "address", "name": "tokenOut", "type": "address"},
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "uint160", "name": "limitSqrtPrice", "type": "uint160"},
        ],
        "name": "quoteExactInputSingle",
        "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]


@dataclass(frozen=True)
class ExecutableQuote:
    amount_out: Decimal
    amount_out_raw: int
    clmm_quoted: int
    clmm_unquoted: int
    hop_proofs: list[dict[str, Any]]

    @property
    def clmm_proven(self) -> bool:
        return self.clmm_unquoted == 0


def _to_raw(symbol: str, amount: Decimal) -> int:
    decimals = int(TOKEN_DECIMALS.get(symbol, 18))
    raw = amount * (Decimal(10) ** decimals)
    return max(0, int(raw.to_integral_value(rounding=ROUND_FLOOR)))


def _from_raw(symbol: str, amount_raw: int) -> Decimal:
    decimals = int(TOKEN_DECIMALS.get(symbol, 18))
    return Decimal(int(amount_raw)) / (Decimal(10) ** decimals)


def _token_addr(symbol: str) -> str:
    value = TOKEN_ADDRESSES.get(symbol, "")
    if not value or not Web3.is_address(value):
        raise ValueError(f"missing token address for {symbol}")
    return Web3.to_checksum_address(value)


def _sqrt_limit_for_direction(pool: dict[str, Any], token_in: str) -> int:
    tokens = pool.get("tokens") or []
    return V3_MIN_SQRT_RATIO_PLUS_ONE if tokens and token_in == tokens[0] else V3_MAX_SQRT_RATIO_MINUS_ONE


def _quote_uniswap_v3(pool: dict[str, Any], token_in: str, token_out: str, amount_in_raw: int) -> int:
    if rpc_layer.w3 is None:
        raise RuntimeError("RPC is not connected")
    quoter = deployment_address("UNISWAP_V3_QUOTER")
    contract = rpc_layer.w3.eth.contract(address=Web3.to_checksum_address(quoter), abi=_ABI_UNISWAP_V3_QUOTER_V1)
    raw_fee_tier = pool.get("fee_tier")
    fee_units = int(raw_fee_tier) if raw_fee_tier is not None else int(Decimal(str(pool.get("fee_bps", 0))) * Decimal("100"))
    return int(
        contract.functions.quoteExactInputSingle(
            _token_addr(token_in),
            _token_addr(token_out),
            fee_units,
            int(amount_in_raw),
            0,
        ).call()
    )


def _quote_algebra(pool: dict[str, Any], token_in: str, token_out: str, amount_in_raw: int) -> int:
    if rpc_layer.w3 is None:
        raise RuntimeError("RPC is not connected")
    quoter = deployment_address("QUICKSWAP_ALGEBRA_QUOTER")
    contract = rpc_layer.w3.eth.contract(address=Web3.to_checksum_address(quoter), abi=_ABI_ALGEBRA_QUOTER)
    return int(
        contract.functions.quoteExactInputSingle(
            _token_addr(token_in),
            _token_addr(token_out),
            int(amount_in_raw),
            _sqrt_limit_for_direction(pool, token_in),
        ).call()
    )


def _math_quote(pool: dict[str, Any], token_in: str, token_out: str, amount_in: Decimal) -> Decimal:
    tokens = pool.get("tokens", [])
    if token_in not in tokens or token_out not in tokens:
        return Decimal("0")
    i = tokens.index(token_in)
    j = tokens.index(token_out)
    proto_raw = pool.get("protocol", "")
    try:
        proto = normalize_protocol(str(proto_raw))
    except Exception:
        proto = str(proto_raw)
    if proto == "V2_CPMM" or proto == "QS_V2_CPMM":
        return DeFiEngineMath.query_uniswap_v2(pool["reserves"][i], pool["reserves"][j], amount_in, pool["fee"])
    if proto == "CURVE_STABLE":
        amounts = [Decimal("0")] * len(pool["reserves"])
        amounts[i] = amount_in
        return DeFiEngineMath.query_curve_stable(pool["reserves"], amounts, i, j, pool["A"])
    if proto == "BAL_WEIGHTED":
        return DeFiEngineMath.query_balancer_weighted(
            pool["reserves"], pool["weights"], amount_in, i, j, pool["swap_fee"]
        )
    return Decimal("0")


def quote_route_for_executor(path: list[str], pool_sequence: list[str], pools: dict[str, dict], amount_in: Decimal) -> ExecutableQuote:
    amount = Decimal(amount_in)
    clmm_quoted = 0
    clmm_unquoted = 0
    proofs: list[dict[str, Any]] = []

    for hop_idx, pool_id in enumerate(pool_sequence):
        if hop_idx + 1 >= len(path) or pool_id not in pools:
            clmm_unquoted += 1
            proofs.append({"hop": hop_idx, "pool_id": pool_id, "status": "fail", "reason": "missing_pool_or_path"})
            return ExecutableQuote(Decimal("0"), 0, clmm_quoted, clmm_unquoted, proofs)

        pool = pools[pool_id]
        proto_raw = str(pool.get("protocol", ""))
        try:
            proto = normalize_protocol(proto_raw)
        except Exception:
            proto = proto_raw
        token_in = path[hop_idx]
        token_out = path[hop_idx + 1]

        if proto in CLMM_PROTOCOLS:
            amount_in_raw = _to_raw(token_in, amount)
            if amount_in_raw <= 0:
                clmm_unquoted += 1
                proofs.append({"hop": hop_idx, "pool_id": pool_id, "protocol": proto, "status": "fail", "reason": "zero_raw_amount_in"})
                return ExecutableQuote(Decimal("0"), 0, clmm_quoted, clmm_unquoted, proofs)
            try:
                if proto == "V3_CLMM":
                    amount_out_raw = _quote_uniswap_v3(pool, token_in, token_out, amount_in_raw)
                else:
                    amount_out_raw = _quote_algebra(pool, token_in, token_out, amount_in_raw)
            except Exception as exc:
                clmm_unquoted += 1
                proofs.append({
                    "hop": hop_idx,
                    "pool_id": pool_id,
                    "protocol": proto,
                    "status": "fail",
                    "reason": f"{type(exc).__name__}: {exc}",
                })
                return ExecutableQuote(Decimal("0"), 0, clmm_quoted, clmm_unquoted, proofs)
            amount = _from_raw(token_out, amount_out_raw)
            clmm_quoted += 1
            proofs.append({
                "hop": hop_idx,
                "pool_id": pool_id,
                "protocol": proto,
                "status": "pass",
                "amount_in_raw": str(amount_in_raw),
                "amount_out_raw": str(amount_out_raw),
            })
            if amount_out_raw <= 0:
                return ExecutableQuote(Decimal("0"), 0, clmm_quoted, clmm_unquoted, proofs)
            continue

        amount = _math_quote(pool, token_in, token_out, amount)
        proofs.append({
            "hop": hop_idx,
            "pool_id": pool_id,
            "protocol": proto,
            "status": "math",
            "amount_out": str(amount),
        })
        if amount <= 0:
            return ExecutableQuote(Decimal("0"), 0, clmm_quoted, clmm_unquoted, proofs)

    return ExecutableQuote(amount, _to_raw(path[-1], amount), clmm_quoted, clmm_unquoted, proofs)
