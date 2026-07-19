# Chain Indexer Discovery Plane

## Purpose

The Chain Indexer integration is a read-side accelerator for Polygon Chain 137.
It does not replace exact-call simulation, fork simulation, adapter checks, or
the final profitability gate.

## Data Flow

```text
Polygon WSS/RPC
  -> 0xPolygon chain-indexer BlockPollerProducer
  -> Kafka topic: omega.polygon.blocks.raw
  -> Omega pool-log transformer
  -> Kafka topic: omega.polygon.pool.logs
  -> normalized pool-state writer
  -> cache/omega_indexer_state.sqlite
  -> Omega discovery/ranking state loader
  -> exact-call truth gate
  -> payload queue / live guard
```

## Token Coverage Upgrade

`0xPolygon/polygon-token-list` is used as metadata only. The importer selects
Polygon PoS wrapped tokens where `wrappedNetworkId == -1`, rejects native
sentinel rows, bridge-disabled rows, known address collisions, and symbol
conflicts, then stages candidates for factory discovery.

Candidate tokens are paired first against production base assets:

```text
USDC.e, WETH, WPOL, WBTC, USDT, DAI, USDC
```

That prevents the pair scan from wasting its budget on long-tail token pairs
that cannot easily become flash-capital routes or collateral exits.

## Runtime Controls

```env
ENABLE_POLYGON_TOKEN_LIST_DISCOVERY=true
POLYGON_TOKEN_LIST_MAX_CANDIDATES=160
POLYGON_TOKEN_LIST_BASES=USDC.e,WETH,WPOL,WBTC,USDT,DAI,USDC

ENABLE_INDEXER_STATE_READS=false
INDEXER_SQLITE_PATH=cache/omega_indexer_state.sqlite
INDEXER_STATE_MAX_AGE_BLOCKS=4
```

Keep `ENABLE_INDEXER_STATE_READS=false` until the indexer DB is receiving fresh
pool-state rows. When enabled, the engine accepts indexer state only if it is no
more than `INDEXER_STATE_MAX_AGE_BLOCKS` behind the live block.

## Boot

Start Kafka-compatible Redpanda and Mongo:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\indexer\boot_indexer.ps1 -Install
```

The script reads the Compose definition from
`infra\compose\docker-compose.indexer.yml`.

Run the block producer:

```powershell
cd indexer\omega-polygon-indexer
npm run producer
```

Run the pool-log transformer:

```powershell
cd indexer\omega-polygon-indexer
npm run transformer
```

Import normalized pool-state rows when a transformer emits JSONL:

```powershell
python scripts\indexer\import_pool_state_json.py cache\pool_state.normalized.jsonl
```

## Execution Integrity

Indexer state can make discovery and ranking faster, but an opportunity is not
live-executable until these still pass:

1. Pool bytecode and route kind coverage.
2. Orientation and decimals audit.
3. CLMM quoter and sizing pass.
4. Exact executor `eth_call` at the current block.
5. Profit gate after gas, flash fee, slippage floor, and repayment.
6. Broadcast lane health and runtime live guard.
