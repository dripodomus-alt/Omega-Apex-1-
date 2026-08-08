import type { ApprovedExecutionEnvelope } from '../types';

export type NonceLane = 'c1_lane' | 'c2_lane' | 'liquidation_lane';

export interface NonceReservation {
  lane: NonceLane;
  nonce: number;
  executionId: string;
  reservedAtMs: number;
}

export class LaneNonceManager {
  private nextNonce: number;
  private readonly reservations = new Map<number, NonceReservation>();

  constructor(startingNonce: number) {
    this.nextNonce = startingNonce;
  }

  reserve(envelope: ApprovedExecutionEnvelope): NonceReservation {
    const nonce = this.nextNonce;
    this.nextNonce += 1;
    const reservation: NonceReservation = {
      lane: envelope.nonceOwner,
      nonce,
      executionId: envelope.identity.executionId,
      reservedAtMs: Date.now(),
    };
    this.reservations.set(nonce, reservation);
    return reservation;
  }

  get(nonce: number): NonceReservation | undefined {
    return this.reservations.get(nonce);
  }
}
