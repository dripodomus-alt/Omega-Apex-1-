# Polygon (Chain ID 137) — Primary Environment

## Priority

Polygon is the primary execution environment for this skill.

## Key Characteristics

- Low native gas costs (POL)
- Mature Aave V3 deployment
- Strong DeFi and NFT ecosystem
- Fast finality relative to Ethereum L1

## Design Implications

- User funds only POL for gas.
- All strategy capital via Aave V3 (or Balancer) flash loans on Polygon.
- Optimize for Polygon gas model and common token addresses.
- When multi-chain is required, treat Polygon as the home base and bridge only when necessary (budget the bridge cost explicitly).

## Addresses & Tooling

- Always resolve current Aave V3 Pool and related addresses via official sources or on-chain lookups.
- Prefer Foundry / Hardhat + viem / ethers for development.
- Monitor POL gas price and include it in budget-tier analysis.
