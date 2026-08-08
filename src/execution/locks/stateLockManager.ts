import type { ApprovedExecutionEnvelope, ResourceLock } from '../types';

export interface StateLockClaim {
  executionId: string;
  resources: ResourceLock[];
  claimedAtMs: number;
}

function resourceKey(resource: ResourceLock): string {
  return `${resource.kind}:${resource.id.toLowerCase()}`;
}

export class StateLockManager {
  private readonly held = new Map<string, StateLockClaim>();

  acquire(envelope: ApprovedExecutionEnvelope): StateLockClaim {
    const conflicting = envelope.resources.find((resource) => this.held.has(resourceKey(resource)));
    if (conflicting) {
      throw new Error(`[STATE_LOCK] conflicting mutable resource ${resourceKey(conflicting)}`);
    }
    const claim: StateLockClaim = {
      executionId: envelope.identity.executionId,
      resources: envelope.resources,
      claimedAtMs: Date.now(),
    };
    for (const resource of envelope.resources) {
      this.held.set(resourceKey(resource), claim);
    }
    return claim;
  }

  release(executionId: string): void {
    for (const [key, claim] of this.held.entries()) {
      if (claim.executionId === executionId) this.held.delete(key);
    }
  }
}
