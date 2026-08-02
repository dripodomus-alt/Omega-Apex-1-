# Solana Patterns

## Role

Strong support for high-throughput, low-fee strategies.

## Key Differences from EVM

- Account model (not account + storage like EVM)
- Programs instead of smart contracts
- Parallel execution potential
- Different fee and prioritization model (compute units + priority fees)

## Flash-Loan / Capital Notes

- Solana has its own flash-loan and lending primitives (and DEXes).
- When operating on Solana, adapt the “flash-loan capital only, user funds only SOL gas” principle to the local primitives.
- Still apply budget-first tiers and absolute completeness.

## Design Guidance

- Prefer programs that can be fully automated via keepers or on-chain logic.
- Account for rent-exemption and account lifecycle costs in budget analysis.
- High throughput enables strategies that would be gas-prohibitive on L1.
