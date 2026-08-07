import { ethers } from 'ethers';

export const POLYGON_CHAIN_ID = 137;

export const PUBLICNODE_HTTP =
  'https://polygon-bor-rpc.publicnode.com';

export const PUBLICNODE_WSS =
  'wss://polygon-bor-rpc.publicnode.com';

export interface AlchemyTransportOptions {
  httpUrl?: string;
  wssUrl?: string;
  fallbackHttpUrl?: string;
  fallbackWssUrl?: string;
  chainId?: number;
}

function requiredAlchemyUrl(
  explicit: string | undefined,
  envKeys: string[],
  kind: 'HTTP' | 'WSS',
): string {
  const candidates = [
    explicit,
    ...envKeys.map((key) => process.env[key]),
  ];

  for (const value of candidates) {
    const normalized = value?.trim();
    if (!normalized) continue;

    if (
      kind === 'HTTP' &&
      (normalized.startsWith('https://') ||
        normalized.startsWith('http://'))
    ) {
      return normalized;
    }

    if (kind === 'WSS' && normalized.startsWith('wss://')) {
      return normalized;
    }
  }

  throw new Error(
    `Missing Alchemy ${kind} endpoint. Configure ${
      kind === 'HTTP'
        ? 'ALCHEMY_POLYGON_HTTP_URL'
        : 'ALCHEMY_POLYGON_WSS_URL'
    }.`,
  );
}

export class AlchemyPolygonTransport {
  readonly expectedChainId: number;
  readonly httpUrl: string;
  readonly wssUrl: string;
  readonly fallbackHttpUrl: string;
  readonly fallbackWssUrl: string;

  private httpProvider: ethers.JsonRpcProvider | null = null;
  private fallbackHttpProvider: ethers.JsonRpcProvider | null = null;
  private wssProvider: ethers.WebSocketProvider | null = null;
  private fallbackWssProvider: ethers.WebSocketProvider | null = null;

  constructor(options: AlchemyTransportOptions = {}) {
    this.expectedChainId =
      options.chainId ??
      Number(process.env.CHAIN_ID ?? POLYGON_CHAIN_ID);

    this.httpUrl = requiredAlchemyUrl(
      options.httpUrl,
      [
        'ALCHEMY_POLYGON_HTTP_URL',
        'POLYGON_RPC_URL',
        'DISCOVERY_RPC_URL',
      ],
      'HTTP',
    );

    this.wssUrl = requiredAlchemyUrl(
      options.wssUrl,
      [
        'ALCHEMY_POLYGON_WSS_URL',
        'POLYGON_WSS_URL',
        'DISCOVERY_RPC_WSS',
      ],
      'WSS',
    );

    this.fallbackHttpUrl =
      options.fallbackHttpUrl?.trim() ||
      process.env.POLYGON_FALLBACK_HTTP_URL?.trim() ||
      PUBLICNODE_HTTP;

    this.fallbackWssUrl =
      options.fallbackWssUrl?.trim() ||
      process.env.POLYGON_FALLBACK_WSS_URL?.trim() ||
      PUBLICNODE_WSS;
  }

  private static network(chainId: number): ethers.Networkish {
    return {
      chainId,
      name: 'polygon',
    };
  }

  async getHttpProvider(): Promise<ethers.JsonRpcProvider> {
    if (this.httpProvider) return this.httpProvider;

    const provider = new ethers.JsonRpcProvider(
      this.httpUrl,
      AlchemyPolygonTransport.network(this.expectedChainId),
      {
        staticNetwork: false,
      },
    );

    const network = await provider.getNetwork();
    const actual = Number(network.chainId);

    if (actual !== this.expectedChainId) {
      provider.destroy();
      throw new Error(
        `Alchemy HTTP wrong chain: expected=${this.expectedChainId} actual=${actual}`,
      );
    }

    this.httpProvider = provider;
    return provider;
  }

  async getFallbackHttpProvider(): Promise<ethers.JsonRpcProvider> {
    if (this.fallbackHttpProvider) {
      return this.fallbackHttpProvider;
    }

    const provider = new ethers.JsonRpcProvider(
      this.fallbackHttpUrl,
      AlchemyPolygonTransport.network(this.expectedChainId),
      {
        staticNetwork: false,
      },
    );

    const network = await provider.getNetwork();

    if (Number(network.chainId) !== this.expectedChainId) {
      provider.destroy();
      throw new Error(
        `Fallback HTTP wrong chain: expected=${this.expectedChainId} actual=${Number(network.chainId)}`,
      );
    }

    this.fallbackHttpProvider = provider;
    return provider;
  }

  async getWssProvider(): Promise<ethers.WebSocketProvider> {
    if (this.wssProvider) return this.wssProvider;

    const provider = new ethers.WebSocketProvider(
      this.wssUrl,
      AlchemyPolygonTransport.network(this.expectedChainId),
      {
        staticNetwork: false,
      },
    );

    const network = await provider.getNetwork();
    const actual = Number(network.chainId);

    if (actual !== this.expectedChainId) {
      await provider.destroy();
      throw new Error(
        `Alchemy WSS wrong chain: expected=${this.expectedChainId} actual=${actual}`,
      );
    }

    this.wssProvider = provider;
    return provider;
  }

  async getFallbackWssProvider(): Promise<ethers.WebSocketProvider> {
    if (this.fallbackWssProvider) {
      return this.fallbackWssProvider;
    }

    const provider = new ethers.WebSocketProvider(
      this.fallbackWssUrl,
      AlchemyPolygonTransport.network(this.expectedChainId),
      {
        staticNetwork: false,
      },
    );

    const network = await provider.getNetwork();

    if (Number(network.chainId) !== this.expectedChainId) {
      await provider.destroy();
      throw new Error(
        `Fallback WSS wrong chain: expected=${this.expectedChainId} actual=${Number(network.chainId)}`,
      );
    }

    this.fallbackWssProvider = provider;
    return provider;
  }

  async withHttpFailover<T>(
    action: (provider: ethers.JsonRpcProvider) => Promise<T>,
  ): Promise<T> {
    try {
      return await action(await this.getHttpProvider());
    } catch (primaryError) {
      try {
        return await action(await this.getFallbackHttpProvider());
      } catch (fallbackError) {
        throw new AggregateError(
          [primaryError, fallbackError],
          'Alchemy HTTP and PublicNode fallback both failed',
        );
      }
    }
  }

  async health(): Promise<{
    ok: boolean;
    chainId?: number;
    latestBlock?: number;
    httpEndpoint: string;
    wssEndpoint: string;
    fallbackHttpEndpoint: string;
    fallbackWssEndpoint: string;
    error?: string;
  }> {
    try {
      const http = await this.getHttpProvider();
      const wss = await this.getWssProvider();

      const [httpNetwork, wssNetwork, latestBlock] = await Promise.all([
        http.getNetwork(),
        wss.getNetwork(),
        http.getBlockNumber(),
      ]);

      const httpChainId = Number(httpNetwork.chainId);
      const wssChainId = Number(wssNetwork.chainId);

      if (
        httpChainId !== this.expectedChainId ||
        wssChainId !== this.expectedChainId
      ) {
        throw new Error(
          `Chain mismatch HTTP=${httpChainId} WSS=${wssChainId}`,
        );
      }

      return {
        ok: true,
        chainId: httpChainId,
        latestBlock,
        httpEndpoint: this.mask(this.httpUrl),
        wssEndpoint: this.mask(this.wssUrl),
        fallbackHttpEndpoint: this.mask(this.fallbackHttpUrl),
        fallbackWssEndpoint: this.mask(this.fallbackWssUrl),
      };
    } catch (error) {
      return {
        ok: false,
        httpEndpoint: this.mask(this.httpUrl),
        wssEndpoint: this.mask(this.wssUrl),
        fallbackHttpEndpoint: this.mask(this.fallbackHttpUrl),
        fallbackWssEndpoint: this.mask(this.fallbackWssUrl),
        error: error instanceof Error ? error.message : String(error),
      };
    }
  }

  mask(url: string): string {
    try {
      const parsed = new URL(url);
      return `${parsed.protocol}//${parsed.host}/...`;
    } catch {
      return 'configured';
    }
  }

  async destroy(): Promise<void> {
    this.httpProvider?.destroy();
    this.fallbackHttpProvider?.destroy();

    if (this.wssProvider) {
      await this.wssProvider.destroy();
    }

    if (this.fallbackWssProvider) {
      await this.fallbackWssProvider.destroy();
    }

    this.httpProvider = null;
    this.fallbackHttpProvider = null;
    this.wssProvider = null;
    this.fallbackWssProvider = null;
  }
}
