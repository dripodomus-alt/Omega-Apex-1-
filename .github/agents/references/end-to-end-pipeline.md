# End-to-End Pipeline Architecture

## Definition

A complete pipeline covers the full lifecycle from trigger to final state, including failure and evolution.

## Required Stages

1. **Trigger / Entry** — how the system starts (keeper, user, event, schedule)
2. **Capital Acquisition** — flash loan (Aave V3 / Balancer)
3. **Core Logic** — the actual strategy or business logic
4. **Repayment & Settlement** — return flash-loan capital + fee
5. **State Update & Accounting** — on-chain and off-chain records
6. **Monitoring & Alerting** — continuous health and performance
7. **Recovery** — automatic handling of common failures
8. **Evolution** — path for improvement (parameters, logic, architecture)

## Design Rules

- Every stage must be designed, not left as “TODO”.
- Prefer atomic on-chain segments where possible.
- Explicitly budget gas and fees across the whole pipeline.
- Document residual risks and assumptions at the end of the design.
- Automate as much as possible; remaining manual steps must be justified and minimal.
