# Superior Arbitrage Equation With SPLS

This is the canonical execution-grade equation for Omega V5 route scoring.
It is designed to rank raw opportunity first, then prove that the route remains
profitable after state, price, liquidity, and slippage constraints.

SPLS means:

- `S`: live state integrity: block, reserves, ticks, liquidity, balances, pool metadata
- `P`: executable price: exact quote at selected size, not midpoint or stale spot
- `L`: liquidity depth: size bounded by active liquidity and pool quality
- `S`: slippage/revert safety: min-outs, buffers, gas, relay, and risk reserves

## Route Definition

For a closed atomic route:

```text
R = T0 -> T1 -> ... -> Tn
T0 = Tn
P = [p1, p2, ... pn]
F_i = executable invariant quote function for pool p_i
x0 = selected base-token input amount
```

Each hop is composed exactly:

```text
x1 = F_1(x0 | S_1, P_1, L_1)
x2 = F_2(x1 | S_2, P_2, L_2)
...
xn = F_n(x(n-1) | S_n, P_n, L_n)
```

The route is only comparable if:

```text
T0 = Tn
all pool liquidity keys are distinct
all token addresses and decimals are verified on-chain
all pool state reads are fresh within the allowed block age
every CLMM/V3/Algebra leg has an exact quoter proof or exact simulator proof
```

## Superior Net Equation

```text
gross_base_delta = xn - x0
gross_usd_out = xn * USD(T0)
principal_usd = x0 * USD(T0)
raw_delta_usd = gross_usd_out - principal_usd

spls_deduction_usd =
    state_staleness_penalty_usd
  + price_confidence_penalty_usd
  + liquidity_depth_penalty_usd
  + slippage_buffer_usd

net_gain_usd =
    raw_delta_usd
  - flashloan_fee_usd
  - gas_cost_usd
  - relay_or_private_submit_cost_usd
  - risk_buffer_usd
  - spls_deduction_usd
```

For route candidates where pool swap fees are embedded in the executable quote,
do not subtract swap fees twice. V2, V3, Algebra, Curve, and Balancer quote
functions must return fee-adjusted output amounts.

## Two-Leg Price Identity

For a two-leg base-to-mid-to-base route:

```text
mid_units = F_buy(x0)
base_out = F_sell(mid_units)

buy_price_base_per_mid = x0 / mid_units
sell_price_base_per_mid = base_out / mid_units
raw_spread_base_per_mid = sell_price_base_per_mid - buy_price_base_per_mid
```

The route is directionally valid only when:

```text
buy_price_base_per_mid < sell_price_base_per_mid
base_out > x0
raw_delta_usd > 0
```

## SPLS Components

### State

```text
state_fresh = current_block - state_block <= max_state_age_blocks
state_staleness_penalty_usd =
    0 if state_fresh
    else raw_delta_usd * stale_state_penalty_bps / 10000
```

State proof must include:

```text
pool address
token0/token1 or token list
on-chain token addresses
on-chain decimals
reserves, sqrtPriceX96, liquidity, balances, weights, amplification, or equivalent
block number
audit status
```

### Price

```text
executable_price_i = amount_in_i / amount_out_i
price_confidence_penalty_usd =
    raw_delta_usd * price_uncertainty_bps / 10000
```

Price proof must come from one of:

```text
exact on-chain quoter call
exact invariant quote over live state
executor eth_call simulation
fork simulation using the same calldata path
```

Spot-only or midpoint-only pricing is not execution truth.

### Liquidity

```text
size_fraction_i = input_value_usd_i / effective_liquidity_usd_i
liquidity_depth_penalty_usd =
    raw_delta_usd * max(size_fraction_i across route) * depth_penalty_multiplier
```

Hard fail when:

```text
selected_size_usd > max_route_tvl_fraction * weakest_effective_liquidity_usd
duplicate_liquidity_key exists
pool quality audit fails
quote output is zero or negative
```

### Slippage

For every hop:

```text
amount_out_min_i = floor_to_token_decimals(
    exact_amount_out_i * (1 - slippage_bps_i / 10000)
)
```

Route-level slippage buffer:

```text
slippage_buffer_usd =
    gross_usd_out * route_slippage_bps / 10000
```

Integer conversion rule:

```text
raw_amount = floor(decimal_amount * 10^token_decimals)
```

Never round up input, repayment, or min-profit raw units. Rounding up can create
a transaction that asks for more than the proven route can deliver.

## Pass Gate

A route can move from staged to executor truth only if:

```text
net_gain_usd >= min_net_profit_usd
net_gain_usd / gas_cost_usd >= min_profit_to_gas_ratio
raw_delta_usd > 0
all SPLS proofs pass
all amount_out_min_i > 0
all calldata targets are valid contracts
calldata selector is present
executor eth_call or fork simulation succeeds
```

## Ranking Objective

Rank candidates by executable surplus, not raw spread alone:

```text
score =
    net_gain_usd
  * state_confidence
  * price_confidence
  * liquidity_confidence
  * calldata_success_confidence
  / max(route_latency_ms, 1)
```

Tie breakers:

```text
1. higher executor eth_call profit
2. lower route impact
3. lower gas cost
4. fresher state block
5. fewer external assumptions
```

## Minimal Artifact Per Route

Every opportunity DNA card should include:

```text
route path
pool sequence
protocol sequence
block number
metadata proof
live state proof
hop-by-hop exact quote proof
raw_delta_usd
flashloan_fee_usd
gas_cost_usd
relay_or_private_submit_cost_usd
risk_buffer_usd
spls_deduction_usd
net_gain_usd
amount_out_min per hop
calldata target, selector, byte length, and calldata hash
final gate decision and rejection reason if failed
```
