export interface JsonRpcResponse<T> {
  jsonrpc: '2.0';
  id: number;
  result?: T;
  error?: {
    code: number;
    message: string;
    data?: unknown;
  };
}

export interface AlchemyTokenMetadata {
  decimals: number | null;
  logo: string | null;
  name: string | null;
  symbol: string | null;
}

export interface AlchemyTokenBalance {
  contractAddress: string;
  tokenBalance: string | null;
  error?: string | null;
}

export interface AlchemyTokenBalancesResult {
  address: string;
  tokenBalances: AlchemyTokenBalance[];
  pageKey?: string;
}

export interface AlchemyAssetTransfer {
  blockNum: string;
  uniqueId: string;
  hash: string;
  from: string;
  to: string | null;
  value: number | null;
  asset: string | null;
  category: string;
  rawContract?: {
    value?: string | null;
    address?: string | null;
    decimal?: string | null;
  };
}

export interface AlchemyAssetTransfersResult {
  transfers: AlchemyAssetTransfer[];
  pageKey?: string;
}

export interface AlchemyBlockReceiptsResult {
  receipts: unknown[];
}

export class AlchemyEnhancedClient {
  readonly httpUrl: string;

  private idCounter = 1;

  constructor(httpUrl: string) {
    if (
      !httpUrl.startsWith('https://') &&
      !httpUrl.startsWith('http://')
    ) {
      throw new Error('Alchemy enhanced APIs require HTTP/HTTPS endpoint');
    }

    this.httpUrl = httpUrl;
  }

  private nextId(): number {
    return this.idCounter++;
  }

  async rpc<T>(
    method: string,
    params: unknown[] = [],
  ): Promise<T> {
    const id = this.nextId();

    const response = await fetch(this.httpUrl, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        accept: 'application/json',
      },
      body: JSON.stringify({
        jsonrpc: '2.0',
        id,
        method,
        params,
      }),
    });

    if (!response.ok) {
      throw new Error(
        `Alchemy HTTP ${response.status} ${response.statusText}`,
      );
    }

    const payload = await response.json() as JsonRpcResponse<T>;

    if (payload.error) {
      throw new Error(
        `Alchemy RPC ${method} failed ${payload.error.code}: ${payload.error.message}`,
      );
    }

    if (payload.result === undefined) {
      throw new Error(`Alchemy RPC ${method} returned no result`);
    }

    return payload.result;
  }

  async getTokenMetadata(
    tokenAddress: string,
  ): Promise<AlchemyTokenMetadata> {
    return this.rpc<AlchemyTokenMetadata>(
      'alchemy_getTokenMetadata',
      [tokenAddress],
    );
  }

  async getTokenBalances(
    owner: string,
    tokenAddresses: string[],
  ): Promise<AlchemyTokenBalancesResult> {
    return this.rpc<AlchemyTokenBalancesResult>(
      'alchemy_getTokenBalances',
      [owner, tokenAddresses],
    );
  }

  async getAssetTransfers(params: {
    fromBlock?: string;
    toBlock?: string;
    fromAddress?: string;
    toAddress?: string;
    contractAddresses?: string[];
    category: string[];
    excludeZeroValue?: boolean;
    withMetadata?: boolean;
    maxCount?: string;
    pageKey?: string;
  }): Promise<AlchemyAssetTransfersResult> {
    return this.rpc<AlchemyAssetTransfersResult>(
      'alchemy_getAssetTransfers',
      [params],
    );
  }

  async getTransactionReceiptsByBlockNumber(
    blockNumberHex: string,
  ): Promise<AlchemyBlockReceiptsResult> {
    return this.rpc<AlchemyBlockReceiptsResult>(
      'alchemy_getTransactionReceipts',
      [{ blockNumber: blockNumberHex }],
    );
  }
}
