export enum PoolVariantType {
    ConstantProduct = "ConstantProduct",
    UniV3 = "UniV3",
    BalancerWeighted = "BalancerWeighted",
    CurveStable = "CurveStable"
}

export interface ConstantProductParams {
    reserveIn: bigint;
    reserveOut: bigint;
    feeBps: bigint;
}

export interface UniV3Params {
    liquidity: bigint;
    sqrtPriceX96: bigint;
    feeBps: bigint;
}

export interface BalancerWeightedParams {
    balanceIn: bigint;
    weightIn: bigint;
    balanceOut: bigint;
    weightOut: bigint;
    swapFeeBps: bigint;
}

export interface CurveStableParams {
    balances: bigint[];
    A: bigint;
    fee: bigint;
}

export type PoolVariant =
    | { type: PoolVariantType.ConstantProduct; params: ConstantProductParams }
    | { type: PoolVariantType.UniV3; params: UniV3Params }
    | { type: PoolVariantType.BalancerWeighted; params: BalancerWeightedParams }
    | { type: PoolVariantType.CurveStable; params: CurveStableParams };

const FIXED_ONE = 1_000_000_000_000_000_000n;
const FIXED_TWO = 2n * FIXED_ONE;
const FIXED_HALF = FIXED_ONE / 2n;
const LN_2_FIXED = 693_147_180_559_945_309n;

function absBigint(value: bigint): bigint {
    return value < 0n ? -value : value;
}

function floorDiv(numerator: bigint, denominator: bigint): bigint {
    if (denominator <= 0n) throw new Error("INVALID_FIXED_POINT_DENOMINATOR");
    let quotient = numerator / denominator;
    const remainder = numerator % denominator;
    if (remainder !== 0n && numerator < 0n) quotient -= 1n;
    return quotient;
}

export class InvariantMath {
    static getAmountOutConstantProduct(amountIn: bigint, reserves: ConstantProductParams): bigint {
        if (amountIn <= 0n) return 0n;
        if (reserves.reserveIn <= 0n || reserves.reserveOut <= 0n) {
            throw new Error("INVALID_CONSTANT_PRODUCT_RESERVES");
        }
        if (reserves.feeBps < 0n || reserves.feeBps >= 10000n) {
            throw new Error("INVALID_CONSTANT_PRODUCT_FEE_BPS");
        }

        const amountInWithFee = amountIn * (10000n - reserves.feeBps);
        const numerator = amountInWithFee * reserves.reserveOut;
        const denominator = (reserves.reserveIn * 10000n) + amountInWithFee;
        return numerator / denominator;
    }

    static getAmountOutBalancerWeighted(amountIn: bigint, params: BalancerWeightedParams): bigint {
        if (amountIn <= 0n) return 0n;
        if (params.balanceIn <= 0n || params.balanceOut <= 0n) {
            throw new Error("INVALID_BALANCER_WEIGHTED_BALANCES");
        }
        if (params.weightIn <= 0n || params.weightOut <= 0n) {
            throw new Error("INVALID_BALANCER_WEIGHTED_WEIGHTS");
        }
        if (params.swapFeeBps < 0n || params.swapFeeBps >= 10000n) {
            throw new Error("INVALID_BALANCER_WEIGHTED_FEE_BPS");
        }

        const amountInAfterFee = amountIn * (10000n - params.swapFeeBps) / 10000n;
        if (amountInAfterFee === 0n) return 0n;

        // Balancer weighted out-given-in:
        // amountOut = balanceOut * (1 - (balanceIn / (balanceIn + amountInAfterFee)) ^ (weightIn / weightOut))
        const base = this.toFixed(params.balanceIn, params.balanceIn + amountInAfterFee);
        const exponent = this.toFixed(params.weightIn, params.weightOut);
        const power = this.powFixed(base, exponent);
        if (power >= FIXED_ONE) return 0n;

        return params.balanceOut * (FIXED_ONE - power) / FIXED_ONE;
    }

    static getBalancerWeightedInvariant(params: BalancerWeightedParams): bigint {
        if (params.balanceIn <= 0n || params.balanceOut <= 0n || params.weightIn <= 0n || params.weightOut <= 0n) {
            throw new Error("INVALID_BALANCER_WEIGHTED_INVARIANT_INPUT");
        }

        const totalWeight = params.weightIn + params.weightOut;
        const normalizedWeightIn = this.toFixed(params.weightIn, totalWeight);
        const normalizedWeightOut = this.toFixed(params.weightOut, totalWeight);
        const scaledBalanceIn = params.balanceIn * FIXED_ONE;
        const scaledBalanceOut = params.balanceOut * FIXED_ONE;
        return this.powFixed(scaledBalanceIn, normalizedWeightIn) * this.powFixed(scaledBalanceOut, normalizedWeightOut) / FIXED_ONE;
    }

    private static toFixed(numerator: bigint, denominator: bigint): bigint {
        if (denominator <= 0n) throw new Error("INVALID_FIXED_POINT_DENOMINATOR");
        return numerator * FIXED_ONE / denominator;
    }

    private static powFixed(baseFixed: bigint, exponentFixed: bigint): bigint {
        if (baseFixed <= 0n) throw new Error("INVALID_FIXED_POINT_BASE");
        if (exponentFixed < 0n) throw new Error("INVALID_FIXED_POINT_EXPONENT");
        if (exponentFixed === 0n) return FIXED_ONE;
        const logBase = this.lnFixed(baseFixed);
        return this.expFixed(logBase * exponentFixed / FIXED_ONE);
    }

    private static lnFixed(valueFixed: bigint): bigint {
        if (valueFixed <= 0n) throw new Error("INVALID_LN_INPUT");

        let x = valueFixed;
        let powerOfTwo = 0n;
        while (x >= FIXED_TWO) {
            x /= 2n;
            powerOfTwo += 1n;
        }
        while (x < FIXED_HALF) {
            x *= 2n;
            powerOfTwo -= 1n;
        }

        const z = (x - FIXED_ONE) * FIXED_ONE / (x + FIXED_ONE);
        const zSquared = z * z / FIXED_ONE;
        let term = z;
        let sum = 0n;

        for (let denominator = 1n; denominator <= 159n; denominator += 2n) {
            sum += term / denominator;
            term = term * zSquared / FIXED_ONE;
            if (absBigint(term) <= 1n) break;
        }

        return (2n * sum) + (powerOfTwo * LN_2_FIXED);
    }

    private static expFixed(valueFixed: bigint): bigint {
        if (valueFixed === 0n) return FIXED_ONE;

        const powerOfTwo = floorDiv(valueFixed, LN_2_FIXED);
        const remainder = valueFixed - (powerOfTwo * LN_2_FIXED);
        if (powerOfTwo > 255n || powerOfTwo < -255n) {
            throw new Error("FIXED_POINT_EXP_OUT_OF_RANGE");
        }

        let term = FIXED_ONE;
        let sum = FIXED_ONE;
        for (let i = 1n; i <= 80n; i++) {
            term = term * remainder / (FIXED_ONE * i);
            sum += term;
            if (absBigint(term) <= 1n) break;
        }

        if (powerOfTwo >= 0n) {
            return sum * (2n ** powerOfTwo);
        }
        return sum / (2n ** (-powerOfTwo));
    }
}


