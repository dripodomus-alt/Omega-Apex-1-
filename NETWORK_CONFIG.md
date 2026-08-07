# Apex-Omega Polygon 137 Network Configuration

## Provider lanes

```text
Alchemy HTTP
  → primary JSON-RPC
  → Alchemy Enhanced APIs
  → Multicall3 dense contract reads

Alchemy WSS
  → newHeads
  → filtered log subscriptions

GetBlock gRPC (ap-southeast-1)
  → dedicated high-throughput gRPC lane

PublicNode HTTP/WSS
  → independent failover
```

## Important protocol boundary

GetBlock confirms Polygon gRPC support. The configured GetBlock endpoint is therefore retained as a **gRPC transport**, not passed into ethers as a JSON-RPC URL.

A gRPC URL alone is not sufficient to safely invent method names or wire formats. Invocation requires the Polygon/GetBlock gRPC protobuf/service definitions exposed for the endpoint. Until those bindings are present in the repository, the network config exposes and prioritizes the lane but does not masquerade it as JSON-RPC.

## Environment

```text
GETBLOCK_POLYGON_GRPC_URL=<credentialed GetBlock endpoint>
GETBLOCK_POLYGON_GRPC_REGION=ap-southeast-1
```

Use `scripts/configure-network.ps1` to create the complete local `.env.network` file without hardcoding provider credentials into source.
