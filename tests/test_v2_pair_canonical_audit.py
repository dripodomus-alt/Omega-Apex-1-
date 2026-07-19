from decimal import Decimal

from omega_v5.pool_quality import V2_AUDIT_KEY, filter_rankable_pools, route_quality_metadata, route_quality_passed
from omega_v5.rpc_layer import TOKEN_ADDRESSES, _audit_v2_pair_canonical


def _pool(audit: dict) -> dict:
    return {
        "protocol": "UniswapV2",
        "tokens": ["QUICK", "WPOL"],
        "reserves": [Decimal("1000"), Decimal("1000")],
        "fee": Decimal("0.003"),
        "_meta": {V2_AUDIT_KEY: audit},
    }


def test_v2_audit_passes_only_canonical_token_addresses():
    audit = _audit_v2_pair_canonical(
        pool_id="QS_QUICK_WPOL",
        pool_meta={"token0": "QUICK", "token1": "WPOL"},
        toks=["QUICK", "WPOL"],
        token_addrs=[TOKEN_ADDRESSES["QUICK"].lower(), TOKEN_ADDRESSES["WPOL"].lower()],
        onchain_decimals=[18, 18],
        reserves_raw=[10**21, 10**21],
    )

    assert audit["status"] == "pass"
    assert audit["reject_reasons"] == []


def test_v2_audit_rejects_symbol_fallback_for_mismatched_quick_variant():
    stale_quick_variant = "0x831753dd7087cac61ab5644b308642cc1c33dc13"
    audit = _audit_v2_pair_canonical(
        pool_id="QS_QUICK_WPOL_STALE",
        pool_meta={"token0": "QUICK", "token1": "WPOL"},
        toks=["QUICK", "WPOL"],
        token_addrs=[stale_quick_variant.lower(), TOKEN_ADDRESSES["WPOL"].lower()],
        onchain_decimals=[18, 18],
        reserves_raw=[10**21, 10**21],
    )

    assert audit["status"] == "fail"
    assert "token0_unknown_onchain_address" in audit["reject_reasons"]
    assert "token0_address_symbol_mismatch" in audit["reject_reasons"]


def test_rankable_pool_filter_and_route_quality_reject_failed_v2_audit():
    failed_audit = _audit_v2_pair_canonical(
        pool_id="QS_QUICK_WPOL_STALE",
        pool_meta={"token0": "QUICK", "token1": "WPOL"},
        toks=["QUICK", "WPOL"],
        token_addrs=["0x831753dd7087cac61ab5644b308642cc1c33dc13", TOKEN_ADDRESSES["WPOL"].lower()],
        onchain_decimals=[18, 18],
        reserves_raw=[10**21, 10**21],
    )
    pools = {"QS_QUICK_WPOL_STALE": _pool(failed_audit)}

    filtered, summary = filter_rankable_pools(pools)
    route_quality = route_quality_metadata(["QS_QUICK_WPOL_STALE"], pools)

    assert filtered == {}
    assert summary["v2_pair_canonical"]["v2_failed"] == 1
    assert route_quality["v2_pair_canonical"] == "fail"
    assert route_quality_passed(["QS_QUICK_WPOL_STALE"], pools) is False
