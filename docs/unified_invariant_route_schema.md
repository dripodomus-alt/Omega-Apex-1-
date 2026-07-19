# Unified Invariant Route Schema

Schema id: `omega_v5.unified_invariant_route.v1`

Purpose: one route schema that can describe discovery, ranking, quote proof,
payload construction, exact-call validation, and post-trade accounting across
all supported invariant families.

The schema is intentionally split into:

- route identity
- capital source
- ordered hop semantics
- protocol-specific invariant state
- quote chain
- USD and raw-unit accounting
- execution gates
- proof and trace metadata

This prevents mixing principal, units, spread, raw delta, expenses, and executor
truth.

## Top-Level Envelope

```json
{
  "schema": "omega_v5.unified_invariant_route.v1",
  "chainId": 137,
  "routeId": "OPP-0001",
  "strategy": "CROSS_POOL_TWO_LEG | PEGGED_STABLE_TWO_LEG | TRIANGLE_ARB | FOUR_LEG_CYCLE | LIQUIDATION_EXIT",
  "authority": "SCANNER_ONLY | C1 | C2 | LIQUIDATION | EXECUTOR_READY",
  "status": "DISCOVERED | RANKED | QUOTE_PROVEN | PAYLOAD_READY | EXACT_CALL_PASSED | REJECTED | SUBMITTED | SETTLED",
  "block": {
    "detected": 0,
    "quoted": 0,
    "validated": 0,
    "maxStalenessBlocks": 1
  },
  "path": ["BASE", "MID", "BASE"],
  "capital": {},
  "hops": [],
  "quoteChain": {},
  "accounting": {},
  "executionGate": {},
  "payload": {},
  "proofs": {},
  "trace": {}
}
```

## Capital Source

```json
{
  "capital": {
    "sourceId": 1,
    "sourceName": "BALANCER_VAULT | AAVE_V3 | V2_FLASH_SWAP | V3_FLASH_CALLBACK",
    "adapter": "0x...",
    "adapterCodeHash": "0x...",
    "asset": {
      "symbol": "USDC.e",
      "address": "0x2791...",
      "decimals": 6,
      "usd": "1.000134"
    },
    "principal": {
      "requestedUsd": "50000",
      "selectedUsd": "9588.57",
      "baseUnits": "9589.855040575437108572548722",
      "raw": "9589855040",
      "sizingPolicy": "min(10pct route depth, requested, max)",
      "routeDepthUsd": "47942.85",
      "routeDepthFraction": "0.10",
      "minimumUsd": "5000"
    },
    "fee": {
      "bps": "0",
      "usd": "0",
      "raw": "0",
      "verified": true,
      "source": "balancer_vault_live"
    }
  }
}
```

## Hop Schema

Each hop has common fields plus an `invariant` object. The common hop shape
never changes.

```json
{
  "hopIndex": 1,
  "kind": "UNISWAP_V2 | UNISWAP_V3 | ALGEBRA_V3 | CURVE_STABLE | BALANCER_V2 | DODO_PMM | UNISWAP_V4",
  "poolId": "V3_USDC_e_USDT_500",
  "poolAddress": "0x...",
  "liquidityKey": "137:V3_CLMM:factory:pool:500",
  "tokenIn": {
    "symbol": "USDC.e",
    "address": "0x...",
    "decimals": 6
  },
  "tokenOut": {
    "symbol": "USDT",
    "address": "0x...",
    "decimals": 6
  },
  "amountInRaw": "9589855040",
  "amountOutRaw": "9595937715",
  "amountInUnits": "9589.855040",
  "amountOutUnits": "9595.937715",
  "effectivePriceUsdPerOutUnit": "0.9992322047913584232763019763",
  "fee": {
    "feeTier": "500",
    "feeBps": "5",
    "source": "factory_or_pool_state"
  },
  "invariant": {},
  "readProof": {
    "blockNumber": 90283753,
    "source": "live_rpc",
    "stateFresh": true,
    "orientationDecimalsPass": true
  }
}
```

## Invariant Families

### Constant Product

Use for QuickSwap/Uniswap V2-style pools.

```json
{
  "family": "CONSTANT_PRODUCT_XY_K",
  "formula": "amountOut = reserveOut * amountInAfterFee / (reserveIn + amountInAfterFee)",
  "reserveInRaw": "0",
  "reserveOutRaw": "0",
  "reserveInUnits": "0",
  "reserveOutUnits": "0",
  "kRaw": "0",
  "feeBps": "30"
}
```

### Concentrated Liquidity

Use for Uniswap V3 and QuickSwap Algebra. Keep Algebra separated by `kind`
because its pool ABI and dynamic fee semantics differ.

```json
{
  "family": "CONCENTRATED_LIQUIDITY",
  "engine": "UNISWAP_V3 | ALGEBRA_V3",
  "sqrtPriceX96": "0",
  "tick": 0,
  "liquidityRaw": "0",
  "tickSpacing": 10,
  "feeTier": 500,
  "feeBps": "5",
  "zeroForOne": true,
  "sqrtPriceLimitX96": "0",
  "quoter": {
    "address": "0x...",
    "method": "quoteExactInputSingle",
    "quotedAmountOutRaw": "0",
    "gasEstimate": "0"
  }
}
```

### Curve StableSwap

Use for Curve math-only discovery and executable Curve routes when the router
and pool semantics are configured.

```json
{
  "family": "CURVE_STABLESWAP",
  "poolType": "plain | meta | crypto | factory",
  "coins": ["0x...", "0x..."],
  "coinIndices": {
    "i": 0,
    "j": 1
  },
  "balancesRaw": ["0", "0"],
  "A": "0",
  "fee": "0",
  "adminFee": "0",
  "quoteMethod": "get_dy | calc_token_amount | router_get_exchange_amount"
}
```

### Balancer V2

Use only Balancer V2 on Polygon. Do not use Balancer V3 on Chain 137 unless
official deployment, bytecode, ABI, and pool registry all pass.

```json
{
  "family": "BALANCER_V2_VAULT",
  "vault": "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
  "poolId": "0x...",
  "poolSpecialization": "GENERAL | MINIMAL_SWAP_INFO | TWO_TOKEN",
  "swapKind": "GIVEN_IN",
  "tokens": ["0x...", "0x..."],
  "balancesRaw": ["0", "0"],
  "weights": ["0.5e18", "0.5e18"],
  "swapFeePercentage": "0",
  "formula": "weighted_out_given_exact_in",
  "fundManagement": {
    "sender": "executor",
    "fromInternalBalance": false,
    "recipient": "executor",
    "toInternalBalance": false
  }
}
```

### DODO PMM

Use for DODO PMM pools when pool ABI and adapter semantics are explicitly
configured.

```json
{
  "family": "DODO_PMM",
  "poolType": "DVM | DPP | DSP",
  "baseToken": "0x...",
  "quoteToken": "0x...",
  "i": "0",
  "k": "0",
  "B": "0",
  "Q": "0",
  "B0": "0",
  "Q0": "0",
  "RStatus": "ONE | ABOVE_ONE | BELOW_ONE",
  "feeBps": "0",
  "quoteMethod": "querySellBase | querySellQuote"
}
```

### Uniswap V4

Use as discovery/ranking only until hook semantics and executor adapter support
are proven. Execution must fail closed unless `hookPolicy.executable=true`.

```json
{
  "family": "UNISWAP_V4_SINGLETON",
  "poolManager": "0x...",
  "poolKey": {
    "currency0": "0x...",
    "currency1": "0x...",
    "fee": 0,
    "tickSpacing": 0,
    "hooks": "0x..."
  },
  "poolId": "0x...",
  "sqrtPriceX96": "0",
  "tick": 0,
  "liquidityRaw": "0",
  "hookPolicy": {
    "hookAddress": "0x...",
    "beforeSwap": false,
    "afterSwap": false,
    "executable": false,
    "reason": "hook behavior not executor-classified"
  }
}
```

## Quote Chain

The quote chain enforces route parity:

```json
{
  "quoteChain": {
    "formula": "R = QuoteFinal(...QuoteLeg2(QuoteLeg1(P)))",
    "principalRaw": "9589855040",
    "legs": [
      {
        "hopIndex": 1,
        "amountInRaw": "9589855040",
        "amountOutRaw": "9595937715"
      },
      {
        "hopIndex": 2,
        "amountInRaw": "9595937715",
        "amountOutRaw": "9585072237"
      }
    ],
    "finalAmountOutRaw": "9585072237",
    "parityChecks": [
      {
        "left": "hop2.amountInRaw",
        "right": "hop1.amountOutRaw",
        "pass": true
      }
    ]
  }
}
```

## Accounting Schema

This is the canonical accounting block. It is independent of protocol family.

```json
{
  "accounting": {
    "schema": "omega_v5.arbitrage_accounting.v2",
    "principal": {
      "usd": "9588.57",
      "baseUnits": "9589.855040575437108572548722",
      "raw": "9589855040"
    },
    "spread": {
      "unitToken": "USDT",
      "unitsPurchased": "9595.937715",
      "buyCostUsdPerUnit": "0.9992322047913584232763019763",
      "sellValueUsdPerUnit": "0.9988677002565969656254693604",
      "spreadUsdPerUnit": "-0.0003645045347614576508326159"
    },
    "delta": {
      "grossOutputUsd": "9585.07223719",
      "rawDeltaUsd": "-3.49776281",
      "rawDeltaFormula1": "RawDeltaUSD = GrossOutputUSD - PrincipalUSD",
      "rawDeltaFormula2": "RawDeltaUSD = SpreadUSDPerUnit * UnitsPurchased",
      "principalAlreadyAccountedFor": true,
      "doNotSubtractPrincipalAgain": true
    },
    "expenses": {
      "flashFeeUsd": "0",
      "gasCostUsd": "0.00833288",
      "relayTipUsd": "0.5",
      "riskBufferUsd": "1",
      "otherCostsUsd": "0",
      "netDeltaUsd": "-5.00609569",
      "formula": "NetDeltaUSD = RawDeltaUSD - ExpensesUSD"
    },
    "rawExecutionGate": {
      "formula": "sellAmountOutRaw > principalRaw + flashFeeRaw + gasCostRaw + relayCostRaw + riskBufferRaw + otherCostsRaw + minimumProfitRaw",
      "sellAmountOutRaw": "9585072237",
      "requiredSellAmountOutRaw": "0",
      "pass": false
    }
  }
}
```

## Execution Gate

Execution is allowed only when all hard gates pass.

```json
{
  "executionGate": {
    "capitalSourceConfigured": true,
    "adapterBytecodePresent": true,
    "flashAssetSupported": true,
    "poolKindsConfigured": true,
    "routeStateFresh": true,
    "orientationDecimalsPass": true,
    "quoteChainParityPass": true,
    "rawExecutionGatePass": false,
    "minProfitPass": false,
    "exactCallPass": false,
    "nonceAvailable": false,
    "emergencyStopInactive": true,
    "liveEligible": false,
    "rejectionClass": "quote_aligned_not_profitable"
  }
}
```

## Payload Block

Payloads are unique by stage. C1, C2, and liquidation payloads do not share
meaning even if they use some common fields.

```json
{
  "payload": {
    "stage": "C1 | C2 | LIQUIDATION",
    "target": "0x409ece3Fd71DFBd8f692B600f36A89301cb37346",
    "selector": "0x626482a3",
    "calldata": "0x...",
    "calldataHash": "0x...",
    "signer": "0x...",
    "deadlineBlock": 0,
    "minProfitRaw": "0",
    "slippageBps": "0",
    "status": "NOT_BUILT | BUILT | EXACT_CALL_PASSED | SUBMITTED | REVERTED | SETTLED"
  }
}
```

## Proofs And Trace

```json
{
  "proofs": {
    "quoteSource": "live_rpc | quoter | vault_read | curve_calc | indexer_plus_rpc",
    "exactCall": {
      "performed": false,
      "rpc": "",
      "block": 0,
      "success": false,
      "returnData": "0x",
      "revertReason": ""
    },
    "forkSimulation": {
      "performed": false,
      "rpc": "http://anvil-fork:8545",
      "success": false,
      "txHash": ""
    }
  },
  "trace": {
    "traceHash": "0x...",
    "parentTraceHash": "",
    "c1TxHash": "",
    "c2TxHash": "",
    "receiptBlock": 0,
    "realizedPnlUsd": "0"
  }
}
```

## Required Invariants

Every route must satisfy:

```text
hop[i + 1].amountInRaw == hop[i].amountOutRaw
finalAmountOutRaw == quoteChain.finalAmountOutRaw
RawDeltaUSD == GrossOutputUSD - PrincipalUSD
RawDeltaUSD == SpreadUSDPerUnit * UnitsPurchased for 2-leg routes
NetDeltaUSD == RawDeltaUSD - ExpensesUSD
sellAmountOutRaw > principalRaw + allCostsRaw + minimumProfitRaw
```

No route is live executable if:

```text
protocol family is discovery-only
adapter bytecode is missing
pool kind is unset
quote chain parity fails
raw execution gate fails
exact-call fails
```

