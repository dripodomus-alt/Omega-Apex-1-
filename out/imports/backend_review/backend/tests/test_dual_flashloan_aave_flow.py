from pathlib import Path

CONTRACT = Path(__file__).resolve().parents[1] / "contracts" / "DualFlashLoanArbitrage.sol"
SOURCE = CONTRACT.read_text()


def function_body(name: str) -> str:
    marker = f"function {name}"
    start = SOURCE.rindex(marker)
    brace = SOURCE.index("{", start)
    depth = 0
    for index in range(brace, len(SOURCE)):
        char = SOURCE[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return SOURCE[brace + 1:index]
    raise AssertionError(f"could not find end of {name} body")


def test_aave_pool_interface_exposes_real_flashloan_requests():
    assert "interface IAavePool" in SOURCE
    assert "function flashLoan(" in SOURCE
    assert "function flashLoanSimple(" in SOURCE


def test_execute_aave_arbitrage_requests_pool_flashloan_not_callback():
    execute_body = function_body("executeAaveArbitrage")
    internal_body = function_body("_executeAaveArbitrage")
    request_flow = execute_body + internal_body

    assert "_executeAaveArbitrage(asset, amount, minProfit, deadline, params)" in execute_body
    assert "IAavePool(AAVE_POOL).flashLoan(" in internal_body
    assert "IFlashLoanReceiver(AAVE_POOL).executeOperation" not in request_flow
    assert "executeOperation(" not in internal_body
    assert "abi.encodeWithSignature" not in internal_body


def test_execute_operation_remains_aave_only_callback():
    callback_body = function_body("executeOperation")

    assert 'require(msg.sender == AAVE_POOL, "Only Aave Pool")' in callback_body
    assert 'require(initiator == address(this), "Invalid initiator")' in callback_body
    assert "emit FlashLoanReceived(assets[0], amounts[0], AAVE_POOL)" in callback_body
    assert "return true" in callback_body
