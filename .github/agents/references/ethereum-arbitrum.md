# Ethereum + Arbitrum Patterns

## Role

Strong secondary environments after Polygon.

## Ethereum L1

- Highest security and liquidity.
- Highest gas costs → budget tiers become critical.
- Prefer only when liquidity or security requirements demand it.
- Flash loans still primary capital source; user funds only ETH gas.

## Arbitrum

- Optimistic rollup benefits (lower fees than L1, good EVM compatibility).
- Aave V3 and major DeFi protocols available.
- Bridging costs and finality considerations must appear in budget analysis.
- Useful for strategies that need Ethereum ecosystem liquidity at reduced gas.

## Cross-Chain Notes

- Explicitly budget bridge fees and time.
- Prefer staying on one chain when possible (Polygon first).
- Design atomic flows carefully; cross-chain atomicity is harder.
