import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arbitrage_engine import ArbitrageEngine


class _MockFlashLoan:
    def __init__(self, net_profit_usd: float, net_profit_after_gas_usd: float, is_executable: bool):
        self.net_profit_usd = net_profit_usd
        self.net_profit_after_gas_usd = net_profit_after_gas_usd
        self.is_executable = is_executable


class _MockSpread:
    def __init__(self, flash_loan: _MockFlashLoan):
        self.flash_loan = flash_loan


def _pool(reserve_usd: float):
    return SimpleNamespace(reserve_usd=reserve_usd)


def test_dynamic_extension_rolls_back_when_extension_turns_unprofitable():
    engine = ArbitrageEngine.__new__(ArbitrageEngine)

    def fake_analyze_spread(_pool1, _pool2, loan):
        if abs(loan - 1000) < 1e-9:
            return _MockSpread(_MockFlashLoan(12.0, 10.0, True))
        if abs(loan - 3000) < 1e-9:
            # Extension attempt degrades to non-executable
            return _MockSpread(_MockFlashLoan(20.0, -2.0, False))
        return None

    engine.analyze_spread = fake_analyze_spread

    best_loan, best_spread = engine.find_optimal_loan_amount(
        _pool(100_000), _pool(100_000), min_loan_usd=1000, max_loan_usd=1_000_000
    )

    assert best_loan == 1000
    assert best_spread is not None
    assert best_spread.flash_loan.net_profit_after_gas_usd == 10.0


def test_dynamic_extension_selects_better_profitable_extension():
    engine = ArbitrageEngine.__new__(ArbitrageEngine)

    def fake_analyze_spread(_pool1, _pool2, loan):
        if abs(loan - 1000) < 1e-9:
            return _MockSpread(_MockFlashLoan(12.0, 10.0, True))
        if abs(loan - 3000) < 1e-9:
            return _MockSpread(_MockFlashLoan(22.0, 18.0, True))
        return None

    engine.analyze_spread = fake_analyze_spread

    best_loan, best_spread = engine.find_optimal_loan_amount(
        _pool(100_000), _pool(100_000), min_loan_usd=1000, max_loan_usd=1_000_000
    )

    assert best_loan == 3000.0
    assert best_spread is not None
    assert best_spread.flash_loan.net_profit_after_gas_usd == 18.0


def test_dynamic_extension_returns_no_candidate_when_none_executable():
    engine = ArbitrageEngine.__new__(ArbitrageEngine)

    def fake_analyze_spread(_pool1, _pool2, loan):
        if abs(loan - 1000) < 1e-9:
            return _MockSpread(_MockFlashLoan(1.0, -1.0, False))
        if abs(loan - 3000) < 1e-9:
            return _MockSpread(_MockFlashLoan(2.0, -0.5, False))
        return None

    engine.analyze_spread = fake_analyze_spread

    best_loan, best_spread = engine.find_optimal_loan_amount(
        _pool(100_000), _pool(100_000), min_loan_usd=1000, max_loan_usd=1_000_000
    )

    assert best_loan == 0
    assert best_spread is None
