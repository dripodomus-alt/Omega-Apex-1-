import { ethers } from 'ethers';

export const MULTICALL3_ADDRESS =
  '0xcA11bde05977b3631167028862bE2a173976CA11';

export interface Multicall3Call {
  target: string;
  allowFailure?: boolean;
  callData: string;
}

export interface Multicall3Result {
  success: boolean;
  returnData: string;
}

export interface Multicall3BatchOptions {
  batchSize?: number;
  blockTag?: ethers.BlockTag;
}

const MULTICALL3_ABI = [
  'function aggregate3((address target,bool allowFailure,bytes callData)[] calls) payable returns ((bool success,bytes returnData)[] returnData)',
] as const;

function chunk<T>(values: T[], size: number): T[][] {
  const output: T[][] = [];
  for (let index = 0; index < values.length; index += size) {
    output.push(values.slice(index, index + size));
  }
  return output;
}

export class Multicall3Client {
  readonly address: string;
  readonly provider: ethers.Provider;

  constructor(
    provider: ethers.Provider,
    address = MULTICALL3_ADDRESS,
  ) {
    this.provider = provider;
    this.address = ethers.getAddress(address);
  }

  async assertDeployed(): Promise<void> {
    const code = await this.provider.getCode(this.address);

    if (!code || code === '0x') {
      throw new Error(
        `Multicall3 contract not deployed at ${this.address}`,
      );
    }
  }

  async aggregate(
    calls: Multicall3Call[],
    options: Multicall3BatchOptions = {},
  ): Promise<Multicall3Result[]> {
    if (calls.length === 0) {
      return [];
    }

    const batchSize = Math.max(
      1,
      Math.min(
        Number(options.batchSize ?? process.env.MULTICALL_BATCH_SIZE ?? 128),
        500,
      ),
    );

    const contract = new ethers.Contract(
      this.address,
      MULTICALL3_ABI,
      this.provider,
    );

    const batches = chunk(calls, batchSize);
    const output: Multicall3Result[] = [];

    for (const batch of batches) {
      const normalized = batch.map((call) => ({
        target: ethers.getAddress(call.target),
        allowFailure: call.allowFailure ?? true,
        callData: call.callData,
      }));

      const result = await contract.aggregate3.staticCall(
        normalized,
        options.blockTag !== undefined
          ? { blockTag: options.blockTag }
          : {},
      );

      for (const row of result) {
        output.push({
          success: Boolean(row.success),
          returnData: row.returnData,
        });
      }
    }

    return output;
  }

  async readMany<T>(
    requests: Array<{
      target: string;
      iface: ethers.Interface;
      functionName: string;
      args?: readonly unknown[];
      allowFailure?: boolean;
    }>,
    options: Multicall3BatchOptions = {},
  ): Promise<Array<{
    success: boolean;
    value?: T;
    returnData: string;
    error?: string;
  }>> {
    const calls: Multicall3Call[] = requests.map((request) => ({
      target: request.target,
      allowFailure: request.allowFailure ?? true,
      callData: request.iface.encodeFunctionData(
        request.functionName,
        request.args ?? [],
      ),
    }));

    const results = await this.aggregate(calls, options);

    return results.map((result, index) => {
      if (!result.success) {
        return {
          success: false,
          returnData: result.returnData,
          error: 'CALL_FAILED',
        };
      }

      try {
        const request = requests[index];
        const decoded = request.iface.decodeFunctionResult(
          request.functionName,
          result.returnData,
        );

        return {
          success: true,
          value: (
            decoded.length === 1
              ? decoded[0]
              : decoded
          ) as T,
          returnData: result.returnData,
        };
      } catch (error) {
        return {
          success: false,
          returnData: result.returnData,
          error: error instanceof Error ? error.message : String(error),
        };
      }
    });
  }
}
