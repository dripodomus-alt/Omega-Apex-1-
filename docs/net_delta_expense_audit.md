# Net Delta Expense Audit - APEX-OMEGA Pipeline

## Executive Summary
This document audits every expense in the opportunity pipeline for dimensional correctness, embedding status, and double-counting.

**Key Finding (pre-audit):** The legacy gross delta calculation `RAW_SPREAD_USD_PER_M × FLASHLOAN_USD` was dimensionally invalid (USD/M * USD). Corrected to use MID_UNITS_ACQUIRED or SPREAD_RATIO.

All formulas now use:
- Exact executable round-trip (FLASH_BASE_RAW → buy min_out → sell using min_out → BASE_MIN_OUT_RAW)
- Raw integer accounting for execution
- Decimal only for reporting

## Expense Classification

### A. Flash Capital Expenses
| Expense | Origin | Embedded? | Deducted Separately? | Denomination | Status |
|---------|--------|-----------|----------------------|--------------|--------|
| flashloan provider fee | flash_loan.py:compute_flash_params | No | Yes (repayment_usd) | USD then raw | DEDUCT_SEPARATELY |
| variable premium | Aave/Balancer live read | No | Yes | bps → USD | DEDUCT_SEPARATELY |
| protocol-specific fee | Balancer collector | No | Yes | raw pct | DEDUCT_SEPARATELY |
| callback overhead | executor adapters | Partially in gas | Yes (in gas model) | gas units | DEDUCT_SEPARATELY |
| repayment rounding reserve | sizing.py + units | No | Yes (in min_out) | raw | DEDUCT_SEPARATELY |

### B. Swap Execution Expenses
| Expense | Origin | Embedded? | Deducted Separately? | Status |
|---------|--------|-----------|----------------------|--------|
| fee embedded in buy quote | executable_quotes.py + math_engine | Yes (in quote) | No (never double) | EMBEDDED_IN_EXECUTABLE_QUOTE |
| fee embedded in sell quote | same | Yes | No | EMBEDDED_IN_EXECUTABLE_QUOTE |
| tick crossing / CLMM impact | V3 quoter | Yes | No | EMBEDDED_IN_EXECUTABLE_QUOTE |
| Curve invariant impact | query_curve_stable | Yes | No | EMBEDDED_IN_EXECUTABLE_QUOTE |
| Balancer weight impact | query_balancer_weighted | Yes | No | EMBEDDED_IN_EXECUTABLE_QUOTE |
| DODO PMM impact | amm_adapters | Yes (if quoted) | No | EMBEDDED_IN_EXECUTABLE_QUOTE |
| transfer-fee tokens | token_calibration + filter | N/A | Filtered pre-quote | TOKEN_BEHAVIOR_FILTER |
| decimal/rounding losses | _to_raw / _from_raw | Yes (floor) | Reconciled post | EMBEDDED + RECONCILE_FROM_RECEIPT |

### C. Transaction Expenses
| Expense | Origin | Embedded? | Deducted Separately? | Status |
|---------|--------|-----------|----------------------|--------|
| gas limit | route_tx_gas_limit | No | Yes (gas_cost_usd) | DEDUCT_SEPARATELY |
| EIP-1559 base + priority | gas_oracle.py | No | Yes | DEDUCT_SEPARATELY |
| calldata cost | build_tx_payload | No | In gas estimate | DEDUCT_SEPARATELY |
| L1 data (if any) | Polygon zk not active | N/A | N/A | N/A |

### D. Submission Expenses
| Expense | Origin | Embedded? | Deducted Separately? | Status |
|---------|--------|-----------|----------------------|--------|
| builder payment | mev.py / submission_router | No | Yes (in net) | DEDUCT_SEPARATELY |
| relay payment | same | No | Yes | DEDUCT_SEPARATELY |
| private premium | submission_router | No | Yes | DEDUCT_SEPARATELY |
| failed-attempt reserve | RISK_BUFFER_USD | No | Yes | DEDUCT_SEPARATELY |

### E. Risk Reserves
| Expense | Origin | Embedded? | Deducted Separately? | Status |
|---------|--------|-----------|----------------------|--------|
| state drift reserve | adaptive slippage | No | In min_out + risk_buffer | DEDUCT_SEPARATELY |
| quote-age reserve | preflight | No | In simulation gate | ESTIMATE_ONLY |
| slippage reserve | slippage_model.py (new) | No | In SELL_MIN_OUT | DEDUCT_SEPARATELY |
| rounding reserve | units.py | Yes (floor) | Reconciled | EMBEDDED + RECONCILE |
| oracle conversion | oracle_layer | No | In USD normalization | DEDUCT_SEPARATELY |

## Double-Counted Expenses Removed
- Legacy: subtracting swap fee again after using executable quote output.
- Legacy: using optimistic quoted buy output for sell leg instead of BUY_MIN_OUT.
- Legacy: `RAW_SPREAD_USD_PER_M × FLASHLOAN_USD` (dimensional error).

## Previously Omitted Expenses Added
- Explicit BUILDER_FEE_IN_BASE_RAW
- RELAY_FEE_IN_BASE_RAW
- EXPLICIT_EXECUTION_RESERVE_RAW
- Full raw-integer round-trip accounting in net_delta.py

## Canonical Net Delta Formula (New)
```python
GROSS_BASE_SURPLUS_RAW = BASE_MIN_OUT_RAW - FLASH_BASE_RAW
NET_BASE_SURPLUS_RAW = GROSS_BASE_SURPLUS_RAW \
    - FLASH_FEE_RAW \
    - GAS_COST_IN_BASE_RAW \
    - BUILDER_FEE_IN_BASE_RAW \
    - RELAY_FEE_IN_BASE_RAW \
    - EXPLICIT_EXECUTION_RESERVE_RAW
```

All new modules (pricing/net_delta.py, pricing/expense_ledger.py) enforce this.

## Verification
- All calculations use Decimal for reporting, int for raw execution.
- Sell leg always consumes BUY_MIN_OUT_RAW.
- No embedded fee is subtracted twice.
- Tests added in tests/test_net_delta.py (see below).

Status: CORRECTED. All formulas now dimensionally valid.