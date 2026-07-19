# C1/C2 Payload Target Assignment

Canonical on-chain executor on Polygon Chain 137:

```text
0x409ece3Fd71DFBd8f692B600f36A89301cb37346
```

This address is assigned as:

- `PRIMARY_ATOMIC_EXECUTOR`
- `C1_PAYLOAD_TARGET`
- `C2_PAYLOAD_TARGET`
- `ADAPTER_CONFIGURATION_TARGET`
- `CAPITAL_SOURCE_DISPATCHER`
- `ROUTE_CONSUMPTION_GUARD`
- `MINIMUM_PROFIT_ENFORCER`

The C1 payload uses:

```solidity
executeFlashArb(uint8,address,uint256,address[],address[],uint256)
```

The C2 payload uses:

```solidity
executeC2Arb((uint8,address,uint256,address[],address[],uint256,uint64,uint64,bytes32))
```

Adapter configuration is by capital source, not by DEX:

```solidity
configureAdapter(uint8 flashSource, address adapter)
adapterForSource(uint8 flashSource)
```

Source IDs:

```text
0 = Aave V3 capital adapter
1 = Balancer Vault capital adapter
2 = V2 flash-swap adapter
3 = V3 flash-callback adapter
```

`poolSequence` remains the executable pool route. Public routers, quoters,
factories, Aave Pool, Balancer Vault, and Multicall3 are infrastructure
contracts and must not be configured as source adapters.

Current live read on the canonical executor:

```text
adapterForSource[0] = 0x0000000000000000000000000000000000000000
adapterForSource[1] = 0x0000000000000000000000000000000000000000
adapterForSource[2] = 0x0000000000000000000000000000000000000000
adapterForSource[3] = 0x0000000000000000000000000000000000000000
```

Live execution remains blocked until verified source adapter contracts are
configured by the owner and the contract-level safety defects are corrected or
explicitly accepted in the deployment plan.
