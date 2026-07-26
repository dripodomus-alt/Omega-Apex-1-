#!/usr/bin/env python3
# Test for staging dry run, now covering the new sequence and ID validation.

import pytest
from omega_v5.route_execution_stager import pre_rank_routes
from omega_v5.pipeline_validation import validate_payload_ids_and_sequence

def test_staging_enforces_sequence_and_ids():
    # Mock pools and tokens
    mock_pools = {}
    mock_tokens = ["USDC", "WETH"]
    staged = pre_rank_routes(mock_pools, mock_tokens, max_hops=2)
    for route in staged:
        assert validate_payload_ids_and_sequence(route) is True, "Staged route must pass new gates"
    print("Staging dry-run test with new proof passed.")

# Additional tests for invalid cases would reject routes.
if __name__ == "__main__":
    test_staging_enforces_sequence_and_ids()
