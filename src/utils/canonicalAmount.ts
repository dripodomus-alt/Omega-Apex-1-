/**
 * OMEGA V5 — Canonical Amount Value Object
 *
 * This class encapsulates a token amount, its decimals, and its normalized
 * representation (as an 18-decimal fixed-point number). It enforces the
 * "correct by construction" principle: an instance of CanonicalAmount is
 * always normalized upon creation.
 *
 * This prevents the accidental use of raw, decimal-dependent values in
 * contexts that expect a standardized 18-decimal format, enhancing type
 * safety and reducing boilerplate throughout the application.
 *
 * Inspired by the "Value Object" pattern, this class is immutable after
 * creation.
 */

import { ethers } from 'ethers';

/**
 * Represents a token amount in a standardized, 18-decimal fixed-point format.
 * This is a nominal type to prevent accidental mixing with standard bigints.
 */
export type X18 = bigint & { readonly _X18: unique symbol };

const TEN_POW_18 = 10n ** 18n;

/**
 * A value object representing a token amount with its decimal context.
 */
export class CanonicalAmount {
  public readonly raw: bigint;
  public readonly decimals: number;
  public readonly normalized: X18;

  /**
   * Creates a new CanonicalAmount, normalizing the raw amount to 18 decimals.
   * @param raw The raw token amount in its native decimal precision (e.g., from a contract call).
   * @param decimals The number of decimals for the token.
   */
  constructor(raw: bigint, decimals: number) {
    this.raw = raw;
    this.decimals = decimals;
    this.normalized = CanonicalAmount.rawToX18(raw, decimals);
  }

  /**
   * Normalizes a raw bigint amount to a standard 18-decimal fixed-point representation (X18).
   * @param rawValue The raw amount.
   * @param decimals The decimals of the raw amount.
   * @returns The amount normalized to 18 decimals as an X18 type.
   */
  public static rawToX18(rawValue: bigint, decimals: number): X18 {
    if (decimals === 18) {
      return rawValue as X18;
    }
    if (decimals < 18) {
      return (rawValue * 10n ** BigInt(18 - decimals)) as X18;
    }
    // decimals > 18
    return (rawValue / 10n ** BigInt(decimals - 18)) as X18;
  }
}