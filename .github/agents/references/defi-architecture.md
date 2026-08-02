# DeFi Architecture Guidelines

## Core Focus

Build production-grade DeFi systems with absolute completeness.

## Key Concerns

- Economic security and incentive alignment
- Oracle risk and manipulation resistance
- Liquidity depth and slippage
- MEV exposure and mitigation
- Liquidation design and cascade risk
- Upgradeability vs immutability trade-offs
- Formal verification / high-assurance mindset where capital is large

## Flash-Loan Native Design

- Treat flash loans as the primary capital source.
- Design strategies that are profitable after flash-loan fee + gas.
- Surface fee + gas in every budget-tier comparison.
- Prefer atomic multi-step flows that either fully succeed or fully revert.

## Preferred Patterns

- Atomic arbitrage and liquidation bots
- Collateral / debt swaps via flash loans
- Self-repaying or self-optimizing positions
- Modular strategy vaults that can evolve

## Security Baseline

- Assume adversarial environment.
- Explicitly list trust assumptions.
- Prefer battle-tested primitives (Aave V3, Balancer, major DEXes).
- Include monitoring for anomalous behavior.
