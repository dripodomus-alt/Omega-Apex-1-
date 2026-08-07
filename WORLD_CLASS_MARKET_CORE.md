# Apex-Omega Market Core — Polygon WSS + Multicall3

Canonical live read transport:

```text
wss://polygon-bor-rpc.publicnode.com
```

Canonical Polygon Multicall3:

```text
0xcA11bde05977b3631167028862bE2a173976CA11
```

The market service now verifies:

1. the WSS endpoint connects,
2. the connected network is Chain 137,
3. a current block can be read,
4. Multicall3 has deployed bytecode,
5. all batched read paths use `aggregate3`,
6. each failed inner call is isolated by `allowFailure`,
7. batches are bounded by `MULTICALL_BATCH_SIZE`.

Default:

```text
MULTICALL_BATCH_SIZE=128
```

The transport is read-only discovery infrastructure. Transaction broadcast remains a separate execution concern.

## Complete files added

```text
src/engine/rpc/polygonTransport.ts
src/engine/rpc/multicall3.ts
scripts/probe-polygon-wss-multicall.ts
```

## Complete file replaced

```text
services/market-api.ts
```

## Runtime

```bash
npx tsx scripts/probe-polygon-wss-multicall.ts
npx tsx services/market-api.ts
```

Environment:

```bash
POLYGON_WSS_URL=wss://polygon-bor-rpc.publicnode.com
DISCOVERY_RPC_WSS=wss://polygon-bor-rpc.publicnode.com
MULTICALL_BATCH_SIZE=128
```

The protocol scanners should encode individual pool/factory reads and submit them through `Multicall3Client.readMany()` rather than issuing one RPC request per contract read.
