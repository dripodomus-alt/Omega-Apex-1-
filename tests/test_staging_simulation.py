from unittest.mock import MagicMock
from typing import Tuple

from tests.dry_run_25_cycles import simulate_staging


def create_mock_opp(pool_sequence: Tuple[str, ...]) -> MagicMock:
    """Creates a mock opportunity with a specific pool sequence."""
    opp = MagicMock()
    # The simulate_staging function only depends on the pool_sequence attribute
    opp.pool_sequence = pool_sequence
    # Add a name for easier debugging of test failures
    opp.name = f"Opp({','.join(pool_sequence)})"
    opp.__repr__ = lambda self: self.name
    return opp


def test_no_conflicts_stages_all():
    """If there are no pool conflicts, all opportunities should be staged up to the limit."""
    ranked_opps = [
        create_mock_opp(("P1", "P2")),
        create_mock_opp(("P3", "P4")),
        create_mock_opp(("P5", "P6")),
    ]
    staged = simulate_staging(ranked_opps, max_staged=3)
    assert len(staged) == 3
    assert staged == ranked_opps


def test_simple_conflict_is_skipped():
    """An opportunity that conflicts with a higher-ranked staged one should be skipped."""
    opp1 = create_mock_opp(("P1", "P2"))
    opp2_conflict = create_mock_opp(("P3", "P1"))  # Conflicts with opp1 on P1
    opp3_no_conflict = create_mock_opp(("P4", "P5"))

    ranked_opps = [opp1, opp2_conflict, opp3_no_conflict]
    staged = simulate_staging(ranked_opps, max_staged=3)

    assert len(staged) == 2
    assert opp1 in staged
    assert opp2_conflict not in staged
    assert opp3_no_conflict in staged
    # Check that the order of non-conflicting routes is preserved
    assert staged == [opp1, opp3_no_conflict]


def test_identical_pool_sequence_is_a_conflict():
    """
    If two opportunities have the exact same pool sequence, the second one
    should be considered a conflict and be skipped.
    """
    opp1 = create_mock_opp(("P1", "P2", "P3"))
    opp2_identical = create_mock_opp(("P1", "P2", "P3"))
    opp3_no_conflict = create_mock_opp(("P4", "P5"))

    ranked_opps = [opp1, opp2_identical, opp3_no_conflict]
    staged = simulate_staging(ranked_opps, max_staged=3)

    assert len(staged) == 2
    assert opp1 in staged
    assert opp2_identical not in staged
    assert opp3_no_conflict in staged
    assert staged == [opp1, opp3_no_conflict]


def test_max_staged_limit_is_respected():
    """Staging should stop once max_staged is reached, even if more non-conflicting opps exist."""
    ranked_opps = [
        create_mock_opp(("P1", "P2")),
        create_mock_opp(("P3", "P4")),
        create_mock_opp(("P5", "P6")),
        create_mock_opp(("P7", "P8")),
    ]
    staged = simulate_staging(ranked_opps, max_staged=2)
    assert len(staged) == 2
    assert staged == [ranked_opps[0], ranked_opps[1]]


def test_complex_conflict_resolution():
    """
    Tests a more complex scenario with multiple conflicts to ensure the
    highest-ranked non-conflicting opportunities are selected.
    """
    # Ranked opportunities by profitability
    opp1 = create_mock_opp(("P1", "P2"))  # Should be staged
    opp2 = create_mock_opp(("P3", "P1"))  # SKIPPED (conflicts with opp1 on P1)
    opp3 = create_mock_opp(("P4", "P5"))  # Should be staged
    opp4 = create_mock_opp(("P6", "P2"))  # SKIPPED (conflicts with opp1 on P2)
    opp5 = create_mock_opp(("P5", "P7"))  # SKIPPED (conflicts with opp3 on P5)
    opp6 = create_mock_opp(("P8", "P9"))  # Should be staged
    opp7 = create_mock_opp(("P10", "P11"))  # Should be staged (if max_staged allows)

    ranked_opps = [opp1, opp2, opp3, opp4, opp5, opp6, opp7]

    staged = simulate_staging(ranked_opps, max_staged=4)

    expected_staged = [opp1, opp3, opp6, opp7]
    assert len(staged) == 4
    # Using list comprehension on names for a more readable failure message
    assert [o.name for o in staged] == [o.name for o in expected_staged]


def test_all_conflicting_stages_only_the_first():
    """If all subsequent opportunities conflict with the first, only the first is staged."""
    opp1 = create_mock_opp(("P1", "P2"))
    opp2 = create_mock_opp(("P1", "P3"))
    opp3 = create_mock_opp(("P4", "P2"))

    ranked_opps = [opp1, opp2, opp3]
    staged = simulate_staging(ranked_opps, max_staged=8)

    assert len(staged) == 1
    assert staged == [opp1]


def test_empty_input_returns_empty_list():
    """An empty list of opportunities should result in an empty staged list."""
    staged = simulate_staging([], max_staged=8)
    assert staged == []