"""Tests for TVL-capped peak-delta flash injection sizing."""

from decimal import Decimal

from omega_v5.sizing.optimal_flash_sizer import (
    apply_injection_to_route_dict,
    build_size_ladder,
    find_peak_delta_injection,
    optimal_flash_injection,
    snapshot_route_tvl,
)
from omega_v5.flash_loan import FlashSource


def _pools_deep() -> dict:
    # $1M TVL each via explicit executable liquidity
    return {
        "P1": {
            "tokens": ["USDC", "WETH"],
            "total_executable_liquidity_usd": Decimal("1000000"),
            "tvl_usd": Decimal("1000000"),
        },
        "P2": {
            "tokens": ["WETH", "USDC"],
            "total_executable_liquidity_usd": Decimal("800000"),
            "tvl_usd": Decimal("800000"),
        },
    }


def test_snapshot_uses_bottleneck_tvl():
    snap = snapshot_route_tvl(["P1", "P2"], _pools_deep(), requested_principal_usd=Decimal("50000"))
    assert snap is not None
    assert snap.min_pool_tvl_usd == Decimal("800000")
    assert snap.bottleneck_pool_id == "P2"
    # hard cap <= min(route_cap, max_flash, requested)
    assert snap.hard_cap_usd <= Decimal("50000")
    assert snap.hard_cap_usd <= snap.min_pool_tvl_usd * snap.max_fraction


def test_ladder_respects_hard_cap():
    ladder = build_size_ladder(
        hard_cap_usd=Decimal("10000"),
        min_tvl_usd=Decimal("100000"),
        min_principal_usd=Decimal("0"),
    )
    assert ladder
    assert max(ladder) <= Decimal("10000")
    assert all(x > 0 for x in ladder)


def test_peak_delta_stops_after_declination():
    # Synthetic π(x) = x*(0.02) - (x/10000)^2 * 50  → peaks then declines
    def gross_fn(x: Decimal) -> Decimal:
        # gross slightly above principal early, crushed later
        edge = Decimal("1.02") - (x / Decimal("50000"))
        if edge < Decimal("0.9"):
            edge = Decimal("0.9")
        return x * edge

    ladder = [Decimal(str(v)) for v in (1000, 2500, 5000, 10000, 20000, 40000, 80000)]
    best_x, best_pi, best_i, samples = find_peak_delta_injection(
        ladder,
        gross_fn=gross_fn,
        hops=2,
        flash_source=FlashSource.BALANCER,
        asset="USDC",
        stop_on_decline=True,
    )
    assert best_x > 0
    assert len(samples) >= 2
    # Peak should not be the absolute largest size if impact crushes edge
    assert best_x <= Decimal("40000")


def test_optimal_injection_capped_by_tvl_and_payload_fields():
    opt = optimal_flash_injection(
        pool_sequence=["P1", "P2"],
        pools=_pools_deep(),
        base_asset="USDC",
        hops=2,
        flash_source=FlashSource.BALANCER,
        requested_principal_usd=Decimal("100000"),
        base_rate=Decimal("1.005"),
        base_usd_price=Decimal("1"),
        base_decimals=6,
    )
    assert opt.injection_usd > 0
    assert opt.injection_usd <= opt.hard_cap_usd
    assert opt.min_pool_tvl_usd == Decimal("800000")
    assert opt.method in {
        "peak_delta_tvl_bellman_curve",
        "fallback_mid_ladder_no_peak",
        "fixed_no_dynamic",
    }

    route: dict = {"path": ["USDC", "WETH", "USDC"], "pool_sequence": ["P1", "P2"]}
    apply_injection_to_route_dict(route, opt)
    assert Decimal(str(route["flash_principal_usd"])) == opt.injection_usd
    assert route["principal_usd"] == str(opt.injection_usd)
    assert "sizing" in route
    fields = opt.as_payload_fields()
    assert "flash_injection_usd" in fields
    assert fields["flash_principal_usd"] == str(opt.injection_usd)


def test_missing_pool_tvl_rejects():
    pools = {
        "P1": {"tokens": ["USDC", "WETH"], "tvl_usd": Decimal("0")},
    }
    opt = optimal_flash_injection(
        pool_sequence=["P1"],
        pools=pools,
        base_asset="USDC",
        base_rate=Decimal("1.01"),
    )
    assert opt.injection_usd == 0
    assert opt.method == "rejected"
