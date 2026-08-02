import { describe, expect, it } from 'vitest';
import RedisRouteGuard from '../server/engine/RedisRouteGuard.js';

describe('RedisRouteGuard', () => {
  it('acquires and releases route locks for C1 and C2 execution flows', async () => {
    const guard = new RedisRouteGuard(null, { mode: 'memory' });

    const c1First = await guard.acquireC1Lock('0xabc', [{ id: 'step-1' }]);
    expect(c1First.acquired).toBe(true);
    expect(c1First.key).toContain('c1');

    const c1Second = await guard.acquireC1Lock('0xabc', [{ id: 'step-1' }]);
    expect(c1Second.acquired).toBe(false);

    await guard.releaseLock(c1First.key);

    const c1Third = await guard.acquireC1Lock('0xabc', [{ id: 'step-1' }]);
    expect(c1Third.acquired).toBe(true);

    const c2First = await guard.acquireC2Lock('c1-hash');
    expect(c2First.acquired).toBe(true);
    expect(c2First.key).toContain('c2');

    const c2Second = await guard.acquireC2Lock('c1-hash');
    expect(c2Second.acquired).toBe(false);
  });
});
