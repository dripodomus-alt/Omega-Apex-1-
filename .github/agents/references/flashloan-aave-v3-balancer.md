# Flash-Loan Capital Engines — Aave V3 + Balancer Vault

## Core Principle

All strategy capital is sourced via flash loans.  
User supplies only native gas (POL on Polygon 137, ETH on Ethereum/Arbitrum, etc.).  
No principal is ever required from the user.

## Aave V3 Flash Loans

### Methods

- `flashLoanSimple(address receiverAddress, address asset, uint256 amount, bytes params, uint16 referralCode)`
  - Single asset, gas-efficient, fee always charged.
- `flashLoan(address receiverAddress, address[] assets, uint256[] amounts, uint256[] interestRateModes, address onBehalfOf, bytes params, uint16 referralCode)`
  - Multi-asset. Can open variable debt (modes 1/2) instead of immediate repayment. Fee can be waived for approved flashBorrowers.

### Execution Flow

1. Call Pool → transfer funds to receiver → call `executeOperation`.
2. Inside `executeOperation` perform arbitrary logic.
3. Approve Pool for `amount + premium`.
4. Pool pulls repayment. Failure → full revert.

### Fee

- Initialized at 0.05% (`FLASHLOAN_PREMIUM_TOTAL`).
- Query live value on-chain. Do not hard-code.
- Split between LPs and protocol treasury.

### Receiver Requirements

Implement `IFlashLoanSimpleReceiver` or `IFlashLoanReceiver`.  
`executeOperation` must return `true`.  
Never leave significant funds on the receiver long-term (griefing risk).

## Balancer Vault Flash Loans

- Useful for multi-asset atomic capital in one call.
- Different fee structure and liquidity sources.
- Combine with Aave V3 when strategy benefits from both pools.

## Design Rules

- Always calculate and surface the flash-loan fee in budget-tier comparisons.
- Prefer Aave V3 `flashLoanSimple` for single-asset strategies.
- Use Balancer when multi-token atomicity or lower effective cost is required.
- Design the entire strategy so that flash-loan capital is the only capital used for the core logic.
- Gas (native token) is the only user-funded resource.

## Polygon (Chain 137) Priority

Primary deployment target. Use correct Aave V3 Pool address for Polygon.  
User funds POL for gas only.
