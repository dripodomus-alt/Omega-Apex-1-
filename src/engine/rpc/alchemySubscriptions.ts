import { ethers } from 'ethers';

export interface NewHeadEvent {
  blockNumber: number;
  observedAtMs: number;
}

export interface LogSubscriptionConfig {
  address?: string | string[];
  topics?: Array<string | string[] | null>;
}

export class AlchemySubscriptionManager {
  readonly provider: ethers.WebSocketProvider;

  private blockListener?: (blockNumber: number) => void;
  private logListeners: Array<{
    filter: ethers.Filter;
    listener: ethers.Listener;
  }> = [];

  constructor(provider: ethers.WebSocketProvider) {
    this.provider = provider;
  }

  subscribeNewHeads(
    onHead: (event: NewHeadEvent) => void,
  ): () => void {
    if (this.blockListener) {
      throw new Error('newHeads subscription already active');
    }

    this.blockListener = (blockNumber: number) => {
      onHead({
        blockNumber,
        observedAtMs: Date.now(),
      });
    };

    this.provider.on('block', this.blockListener);

    return () => {
      if (this.blockListener) {
        this.provider.off('block', this.blockListener);
        this.blockListener = undefined;
      }
    };
  }

  subscribeLogs(
    config: LogSubscriptionConfig,
    onLog: (log: ethers.Log) => void,
  ): () => void {
    const filter: ethers.Filter = {
      ...(config.address
        ? { address: config.address }
        : {}),
      ...(config.topics
        ? { topics: config.topics }
        : {}),
    };

    const listener: ethers.Listener = (log: ethers.Log) => {
      onLog(log);
    };

    this.provider.on(filter, listener);
    this.logListeners.push({ filter, listener });

    return () => {
      this.provider.off(filter, listener);
      this.logListeners = this.logListeners.filter(
        (entry) => entry.listener !== listener,
      );
    };
  }

  clear(): void {
    if (this.blockListener) {
      this.provider.off('block', this.blockListener);
      this.blockListener = undefined;
    }

    for (const entry of this.logListeners) {
      this.provider.off(entry.filter, entry.listener);
    }

    this.logListeners = [];
  }
}
