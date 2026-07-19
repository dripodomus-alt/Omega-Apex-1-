from omega_v5.protocol_update_watcher import diff_snapshots, stable_digest


def test_diff_snapshots_detects_new_changed_unchanged_and_removed_sources():
    old = {
        "source_fingerprints": {
            "deployment_catalog": "old-deploy",
            "curve_pool_registry": "same-curve",
            "removed_source": "gone",
        }
    }
    current = {
        "source_fingerprints": {
            "deployment_catalog": "new-deploy",
            "curve_pool_registry": "same-curve",
            "polygon_token_list": "new-source",
        }
    }

    diff = diff_snapshots(current, old)

    changed = {item["source"]: item["change_type"] for item in diff["changed_sources"]}
    removed = {item["source"] for item in diff["removed_sources"]}
    assert changed == {
        "deployment_catalog": "changed",
        "polygon_token_list": "new",
    }
    assert removed == {"removed_source"}
    assert diff["unchanged_sources"] == ["curve_pool_registry"]
    assert diff["changed_count"] == 3


def test_stable_digest_is_order_insensitive_for_dict_keys():
    left = {"b": 2, "a": {"d": 4, "c": 3}}
    right = {"a": {"c": 3, "d": 4}, "b": 2}

    assert stable_digest(left) == stable_digest(right)
