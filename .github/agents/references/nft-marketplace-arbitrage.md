# NFT Marketplace & Arbitrage Systems

## Scope

Complete NFT marketplace architecture and arbitrage engines.

## Marketplace Design

- Listing, bidding, royalty, collection, and settlement logic
- End-to-end flow including frontend, indexer, and on-chain contracts
- Absolute completeness: edge cases, failed payments, royalty enforcement, metadata handling

## Arbitrage Systems

- Cross-marketplace and cross-chain NFT arbitrage
- Flash-loan funded where capital is required (buy low / sell high atomically)
- Budget-first analysis of gas, fees, and potential profit
- Full automation of detection, execution, and monitoring

## Capital Rules

- Prefer flash-loan capital for any principal needed.
- User funds only native gas.
- Surface all fees (marketplace, royalty, flash-loan, gas) in the four budget tiers.
