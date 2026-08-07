export const X18 = 10n ** 18n;
export const BPS = 10_000n;

export function asBigInt(value: string | bigint, field = 'value'): bigint {
  try {
    return typeof value === 'bigint' ? value : BigInt(value);
  } catch {
    throw new Error(`Invalid bigint ${field}: ${String(value)}`);
  }
}

export function ratioBps(numerator: bigint, denominator: bigint): bigint {
  if (denominator <= 0n) {
    throw new Error('ratio denominator must be > 0');
  }
  return (numerator * BPS) / denominator;
}

export function spreadBps(buyPriceX18: bigint, sellPriceX18: bigint): bigint {
  if (buyPriceX18 <= 0n) {
    throw new Error('buy price must be > 0');
  }
  if (sellPriceX18 <= buyPriceX18) {
    return 0n;
  }
  return ((sellPriceX18 - buyPriceX18) * BPS) / buyPriceX18;
}

export function usdToX18(value: number): bigint {
  if (!Number.isFinite(value) || value < 0) {
    throw new Error(`Invalid USD amount: ${value}`);
  }

  // Configuration boundary only. Trading comparisons remain bigint.
  return BigInt(Math.round(value * 1_000_000)) * 10n ** 12n;
}

export function x18ToDecimalString(value: bigint, decimals = 6): string {
  const negative = value < 0n;
  const absolute = negative ? -value : value;

  const whole = absolute / X18;
  const fraction = absolute % X18;

  const fractionString = fraction
    .toString()
    .padStart(18, '0')
    .slice(0, decimals)
    .replace(/0+$/, '');

  const body = fractionString.length > 0
    ? `${whole}.${fractionString}`
    : whole.toString();

  return negative ? `-${body}` : body;
}

export function x18ToNumber(value: string | bigint): number {
  const parsed = typeof value === 'bigint' ? value : BigInt(value);
  const whole = Number(parsed / X18);
  const fraction = Number(parsed % X18) / 1e18;
  return whole + fraction;
}
