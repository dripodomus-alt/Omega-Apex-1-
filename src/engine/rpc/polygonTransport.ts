import { ethers } from 'ethers';

export const POLYGON_CHAIN_ID = 137;
export const POLYGON_PUBLICNODE_WSS =
  'wss://polygon-bor-rpc.publicnode.com';

export interface PolygonTransportOptions {
  wssUrl?: string;
  chainId?: number;
}

export class PolygonWssTransport {
  readonly wssUrl: string;
  readonly expectedChainId: number;

  private provider: ethers.WebSocketProvider | null = null;

  constructor(options: PolygonTransportOptions = {}) {
    this.wssUrl =
      options.wssUrl?.trim() ||
      process.env.POLYGON_WSS_URL?.trim() ||
      process.env.DISCOVERY_RPC_WSS?.trim() ||
      POLYGON_PUBLICNODE_WSS;

    this.expectedChainId =
      options.chainId ??
      Number(process.env.CHAIN_ID ?? POLYGON_CHAIN_ID);
  }

  async connect(): Promise<ethers.WebSocketProvider> {
    if (this.provider) {
      return this.provider;
    }

    const provider = new ethers.WebSocketProvider(
      this.wssUrl,
      {
        chainId: this.expectedChainId,
        name: 'polygon',
      },
      {
        staticNetwork: false,
      },
    );

    const network = await provider.getNetwork();
    const actualChainId = Number(network.chainId);

    if (actualChainId !== this.expectedChainId) {
      await provider.destroy();
      throw new Error(
        `Wrong chain on WSS endpoint: expected=${this.expectedChainId} actual=${actualChainId}`,
      );
    }

    this.provider = provider;
    return provider;
  }

  async health(): Promise<{
    ok: boolean;
    chainId?: number;
    latestBlock?: number;
    endpoint: string;
    error?: string;
  }> {
    try {
      const provider = await this.connect();
      const [network, latestBlock] = await Promise.all([
        provider.getNetwork(),
        provider.getBlockNumber(),
      ]);

      return {
        ok: Number(network.chainId) === this.expectedChainId,
        chainId: Number(network.chainId),
        latestBlock,
        endpoint: this.maskedEndpoint(),
      };
    } catch (error) {
      return {
        ok: false,
        endpoint: this.maskedEndpoint(),
        error: error instanceof Error ? error.message : String(error),
      };
    }
  }

  async destroy(): Promise<void> {
    if (this.provider) {
      await this.provider.destroy();
      this.provider = null;
    }
  }

  maskedEndpoint(): string {
    try {
      const parsed = new URL(this.wssUrl);
      return `${parsed.protocol}//${parsed.host}`;
    } catch {
      return 'configured-wss';
    }
  }
}

export const polygonWssTransport = new PolygonWssTransport();
