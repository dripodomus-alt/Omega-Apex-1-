export default class RedisRouteGuard {
  constructor(client = null, options = {}) {
    this.client = client;
    this.options = options;
    this.memoryLocks = new Map();
    this.namespace = options.namespace || 'omega:locks';
  }

  _buildKey(type, identifier) {
    return `${this.namespace}:${type}:${String(identifier).toLowerCase()}`;
  }

  async acquireC1Lock(flashloanAsset, steps = []) {
    const key = this._buildKey('c1', `${String(flashloanAsset || 'default')}:${(steps || []).map((step) => step?.id || step?.venue || step?.tokenIn || '').join('|')}`);
    if (this.memoryLocks.has(key)) {
      return { acquired: false, key, reason: 'lock already held' };
    }

    this.memoryLocks.set(key, {
      type: 'c1',
      asset: flashloanAsset,
      steps: steps || [],
      acquiredAt: Date.now(),
    });
    return { acquired: true, key };
  }

  async acquireC2Lock(c1InternalId) {
    const key = this._buildKey('c2', String(c1InternalId || 'default'));
    if (this.memoryLocks.has(key)) {
      return { acquired: false, key, reason: 'lock already held' };
    }

    this.memoryLocks.set(key, {
      type: 'c2',
      c1InternalId,
      acquiredAt: Date.now(),
    });
    return { acquired: true, key };
  }

  async releaseLock(key) {
    if (!key) return true;
    this.memoryLocks.delete(String(key));
    return true;
  }

  async isAllowed(route) {
    const key = this._buildKey('route', route?.id || route?.routeId || 'default');
    return !this.memoryLocks.has(key);
  }

  async mark(route, status) {
    const key = this._buildKey('route', route?.id || route?.routeId || 'default');
    if (status === 'locked') {
      this.memoryLocks.set(key, { type: 'route', status, updatedAt: Date.now() });
    } else {
      this.memoryLocks.delete(key);
    }
    return true;
  }
}
