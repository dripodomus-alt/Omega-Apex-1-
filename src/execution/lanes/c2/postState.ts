import type { StateProvenance } from '../../types';
import type { C1Commit } from '../c1/types';
import type { PostC1Snapshot } from './types';

export function buildPostC1Snapshot(parent: C1Commit, state: StateProvenance): PostC1Snapshot {
  if (state.blockNumber <= parent.confirmedBlock) {
    throw new Error('[C2_POST_STATE] observed block must be greater than C1 confirmed block');
  }
  if (state.stateHash === parent.preStateHash) {
    throw new Error('[C2_POST_STATE] post-C1 state hash must differ from pre-C1 state hash');
  }
  return {
    ...state,
    parentC1Id: parent.identity.executionId,
    parentConfirmedBlock: parent.confirmedBlock,
  };
}
