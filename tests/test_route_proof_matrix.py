from decimal import Decimal

from omega_v5 import route_proof_matrix


def test_profile_settings_are_ordered_fastest_to_slowest():
    report = route_proof_matrix.profile_settings_report()

    names = [row["name"] for row in report["profiles"]]
    ranks = [row["rank_fast_to_slow"] for row in report["profiles"]]

    assert names[0] == "fastest_low_latency"
    assert names[-1] == "maximum_precision_slowest"
    assert ranks == sorted(ranks)
    assert report["config_semantics"]["max_quote_options_per_pair"].startswith("0 = use every")


def test_metadata_proof_requires_onchain_addresses_and_decimals():
    pool = {
        "protocol": "UniswapV2",
        "address": "0xpool",
        "tokens": ["USDC.e", "WETH"],
        "_meta": {
            "registered_tokens": ["USDC.e", "WETH"],
            "onchain_addresses": ["0xusdc", "0xweth"],
            "onchain_decimals": [6, 18],
        },
    }

    proof = route_proof_matrix._pool_metadata_proof("QS_WETH_USDC_e", pool)

    assert proof["metadata_complete"] is True
    assert proof["missing_or_reject_reasons"] == []


def test_equation_identity_uses_staged_cost_components(monkeypatch):
    row = {
        "path": ["USDC.e", "WETH", "USDC.e"],
        "pool_sequence": ["P1", "P2"],
        "selected_base_amount_in": "100",
        "selected_principal_usd": "100",
        "base_token": "USDC.e",
        "base_token_usd": "1",
        "net_gain_usd": "1.5",
        "net_formula": {
            "flashloan_fee_usd": "0.1",
            "gas_cost_usd": "0.2",
            "relay_or_private_submit_cost_usd": "0.3",
            "risk_buffer_usd": "0.4",
            "extra_slippage_buffer_usd": "0.5",
        },
    }
    pools = {
        "P1": {"protocol": "UniswapV2"},
        "P2": {"protocol": "UniswapV2"},
    }

    monkeypatch.setattr(
        route_proof_matrix,
        "_route_hop_trace",
        lambda path, pool_sequence, pools, amount_in: [
            {"amount_out": Decimal("50"), "positive": True, "clmm_unquoted": 0},
            {"amount_out": Decimal("103"), "positive": True, "clmm_unquoted": 0},
        ],
    )

    proof = route_proof_matrix._route_equation_proof(row, pools)

    assert proof["raw_delta_usd"] == Decimal("3")
    assert proof["net_gain_usd_recomputed"] == Decimal("1.5")
    assert proof["net_identity_pass"] is True
