export type NetworkRole =
  | 'PRIMARY_READ'
  | 'PRIMARY_SUBSCRIPTION'
  | 'HIGH_THROUGHPUT_GRPC'
  | 'FALLBACK_READ'
  | 'FALLBACK_SUBSCRIPTION';

export type NetworkTransport =
  | 'HTTP_JSON_RPC'
  | 'WSS_JSON_RPC'
  | 'GRPC';

export interface NetworkEndpoint {
  id: string;
  provider: 'ALCHEMY' | 'GETBLOCK' | 'PUBLICNODE';
  role: NetworkRole;
  transport: NetworkTransport;
  url: string;
  chainId: 137;
  region?: string;
  enabled: boolean;
  priority: number;
  notes?: string;
}

function requiredUrl(
  keys: string[],
  prefix: 'http' | 'wss',
): string {
  for (const key of keys) {
    const value = process.env[key]?.trim();
    if (!value) continue;

    if (prefix === 'http' && /^https?:\/\//i.test(value)) {
      return value;
    }

    if (prefix === 'wss' && /^wss:\/\//i.test(value)) {
      return value;
    }
  }

  throw new Error(
    `Missing required network endpoint: ${keys.join(' | ')}`,
  );
}

function optionalUrl(
  keys: string[],
): string {
  for (const key of keys) {
    const value = process.env[key]?.trim();
    if (value) return value;
  }
  return '';
}

export interface PolygonNetworkConfig {
  chainId: 137;
  endpoints: NetworkEndpoint[];
  policy: {
    standardReads: 'ALCHEMY_HTTP';
    subscriptions: 'ALCHEMY_WSS';
    denseContractReads: 'MULTICALL3_OVER_ALCHEMY_HTTP';
    grpcLane: 'GETBLOCK_GRPC';
    readFallback: 'PUBLICNODE_HTTP';
    subscriptionFallback: 'PUBLICNODE_WSS';
  };
}

export function buildPolygonNetworkConfig(): PolygonNetworkConfig {
  const alchemyHttp = requiredUrl(
    [
      'ALCHEMY_POLYGON_HTTP_URL',
      'POLYGON_RPC_URL',
      'DISCOVERY_RPC_URL',
    ],
    'http',
  );

  const alchemyWss = requiredUrl(
    [
      'ALCHEMY_POLYGON_WSS_URL',
      'POLYGON_WSS_URL',
      'DISCOVERY_RPC_WSS',
    ],
    'wss',
  );

  const getBlockGrpc = optionalUrl([
    'GETBLOCK_POLYGON_GRPC_URL',
  ]);

  const publicHttp =
    process.env.POLYGON_FALLBACK_HTTP_URL?.trim() ||
    'https://polygon-bor-rpc.publicnode.com';

  const publicWss =
    process.env.POLYGON_FALLBACK_WSS_URL?.trim() ||
    'wss://polygon-bor-rpc.publicnode.com';

  return {
    chainId: 137,
    endpoints: [
      {
        id: 'alchemy-polygon-http',
        provider: 'ALCHEMY',
        role: 'PRIMARY_READ',
        transport: 'HTTP_JSON_RPC',
        url: alchemyHttp,
        chainId: 137,
        enabled: true,
        priority: 10,
        notes:
          'Primary standard JSON-RPC and Enhanced API lane; Multicall3 executes over this provider.',
      },
      {
        id: 'alchemy-polygon-wss',
        provider: 'ALCHEMY',
        role: 'PRIMARY_SUBSCRIPTION',
        transport: 'WSS_JSON_RPC',
        url: alchemyWss,
        chainId: 137,
        enabled: true,
        priority: 10,
        notes:
          'Primary newHeads and narrowly filtered log subscriptions.',
      },
      {
        id: 'getblock-polygon-grpc',
        provider: 'GETBLOCK',
        role: 'HIGH_THROUGHPUT_GRPC',
        transport: 'GRPC',
        url: getBlockGrpc,
        chainId: 137,
        region: 'ap-southeast-1',
        enabled: Boolean(getBlockGrpc),
        priority: 20,
        notes:
          'Dedicated Polygon gRPC lane. Kept separate from ethers JSON-RPC transports; requires GetBlock Polygon gRPC protobuf/service bindings for invocation.',
      },
      {
        id: 'publicnode-polygon-http',
        provider: 'PUBLICNODE',
        role: 'FALLBACK_READ',
        transport: 'HTTP_JSON_RPC',
        url: publicHttp,
        chainId: 137,
        enabled: true,
        priority: 90,
      },
      {
        id: 'publicnode-polygon-wss',
        provider: 'PUBLICNODE',
        role: 'FALLBACK_SUBSCRIPTION',
        transport: 'WSS_JSON_RPC',
        url: publicWss,
        chainId: 137,
        enabled: true,
        priority: 90,
      },
    ],
    policy: {
      standardReads: 'ALCHEMY_HTTP',
      subscriptions: 'ALCHEMY_WSS',
      denseContractReads: 'MULTICALL3_OVER_ALCHEMY_HTTP',
      grpcLane: 'GETBLOCK_GRPC',
      readFallback: 'PUBLICNODE_HTTP',
      subscriptionFallback: 'PUBLICNODE_WSS',
    },
  };
}

export function maskedNetworkConfig(
  config: PolygonNetworkConfig,
): PolygonNetworkConfig {
  return {
    ...config,
    endpoints: config.endpoints.map((endpoint) => ({
      ...endpoint,
      url: maskEndpoint(endpoint.url),
    })),
  };
}

function maskEndpoint(url: string): string {
  if (!url) return 'not-configured';

  try {
    const parsed = new URL(url);
    return `${parsed.protocol}//${parsed.host}/...`;
  } catch {
    return 'configured';
  }
}
