import { ethers } from 'ethers';
import {
  AlchemyPolygonTransport,
} from './alchemyTransport';
import {
  AlchemyEnhancedClient,
} from './alchemyEnhanced';
import {
  AlchemySubscriptionManager,
} from './alchemySubscriptions';
import {
  MULTICALL3_ADDRESS,
  Multicall3Client,
} from './multicall3';

export interface PolygonRuntimeOptions {
  httpUrl?: string;
  wssUrl?: string;
  fallbackHttpUrl?: string;
  fallbackWssUrl?: string;
  multicallBatchSize?: number;
}

export class PolygonRuntime {
  readonly transport: AlchemyPolygonTransport;
  readonly multicallBatchSize: number;

  private enhanced: AlchemyEnhancedClient | null = null;
  private multicall: Multicall3Client | null = null;
  private subscriptions: AlchemySubscriptionManager | null = null;

  constructor(options: PolygonRuntimeOptions = {}) {
    this.transport = new AlchemyPolygonTransport({
      httpUrl: options.httpUrl,
      wssUrl: options.wssUrl,
      fallbackHttpUrl: options.fallbackHttpUrl,
      fallbackWssUrl: options.fallbackWssUrl,
      chainId: 137,
    });

    this.multicallBatchSize = Math.max(
      1,
      Math.min(
        options.multicallBatchSize ??
          Number(process.env.MULTICALL_BATCH_SIZE ?? 128),
        500,
      ),
    );
  }

  get enhancedClient(): AlchemyEnhancedClient {
    if (!this.enhanced) {
      this.enhanced = new AlchemyEnhancedClient(
        this.transport.httpUrl,
      );
    }
    return this.enhanced;
  }

  async multicallClient(): Promise<Multicall3Client> {
    if (this.multicall) return this.multicall;

    const httpProvider = await this.transport.getHttpProvider();

    const client = new Multicall3Client(
      httpProvider,
      MULTICALL3_ADDRESS,
    );

    await client.assertDeployed();
    this.multicall = client;

    return client;
  }

  async subscriptionManager(): Promise<AlchemySubscriptionManager> {
    if (this.subscriptions) {
      return this.subscriptions;
    }

    const wss = await this.transport.getWssProvider();
    this.subscriptions = new AlchemySubscriptionManager(wss);
    return this.subscriptions;
  }

  async currentBlock(): Promise<number> {
    return this.transport.withHttpFailover(
      (provider) => provider.getBlockNumber(),
    );
  }

  async batchRead<T>(
    requests: Array<{
      target: string;
      iface: ethers.Interface;
      functionName: string;
      args?: readonly unknown[];
      allowFailure?: boolean;
    }>,
    blockTag?: ethers.BlockTag,
  ): Promise<Array<{
    success: boolean;
    value?: T;
    returnData: string;
    error?: string;
  }>> {
    const client = await this.multicallClient();

    return client.readMany<T>(
      requests,
      {
        batchSize: this.multicallBatchSize,
        blockTag,
      },
    );
  }

  async health(): Promise<{
    ok: boolean;
    transport: Awaited<ReturnType<AlchemyPolygonTransport['health']>>;
    multicallReady: boolean;
    multicallAddress: string;
    multicallBatchSize: number;
    enhancedApiReady: boolean;
    subscriptionsReady: boolean;
    error?: string;
  }> {
    try {
      const transport = await this.transport.health();

      if (!transport.ok) {
        return {
          ok: false,
          transport,
          multicallReady: false,
          multicallAddress: MULTICALL3_ADDRESS,
          multicallBatchSize: this.multicallBatchSize,
          enhancedApiReady: false,
          subscriptionsReady: false,
          error: transport.error,
        };
      }

      await this.multicallClient();
      await this.subscriptionManager();

      return {
        ok: true,
        transport,
        multicallReady: true,
        multicallAddress: MULTICALL3_ADDRESS,
        multicallBatchSize: this.multicallBatchSize,
        enhancedApiReady: true,
        subscriptionsReady: true,
      };
    } catch (error) {
      return {
        ok: false,
        transport: await this.transport.health(),
        multicallReady: false,
        multicallAddress: MULTICALL3_ADDRESS,
        multicallBatchSize: this.multicallBatchSize,
        enhancedApiReady: false,
        subscriptionsReady: false,
        error: error instanceof Error ? error.message : String(error),
      };
    }
  }

  async destroy(): Promise<void> {
    this.subscriptions?.clear();
    await this.transport.destroy();
    this.enhanced = null;
    this.multicall = null;
    this.subscriptions = null;
  }
}
