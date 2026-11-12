'use strict';

// A deterministic renderer-cache model, NOT a browser localStorage implementation.
// Writes reach the durable backend and the originating renderer. Other renderer
// views stay stale until explicitly refreshed; Web Lock release does not refresh.
function createStorageOrigin(initial = []) {
  const durable = new Map(initial), traces = [];
  let sequence = 0;
  function tab(name, snapshot = durable) {
    const cache = new Map(snapshot);
    function record(op, key, value) {
      traces.push({ sequence: ++sequence, tab: name, op, key,
        value: value ?? null, durableValue: durable.get(key) ?? null });
    }
    const view = {
      get size() { return cache.size; },
      has(key) { return cache.has(key); },
      get(key) { const value = cache.get(key); record('get', key, value); return value; },
      set(key, value) { durable.set(key, value); cache.set(key, value); record('set', key, value); return view; },
      delete(key) { durable.delete(key); const result = cache.delete(key); record('delete', key); return result; },
      clear() { durable.clear(); cache.clear(); record('clear', null); },
      entries() { return cache.entries(); },
      keys() { return cache.keys(); },
      values() { return cache.values(); },
      [Symbol.iterator]() { return cache[Symbol.iterator](); },
      refresh() { cache.clear(); for (const entry of durable) cache.set(...entry); },
      snapshot() { return new Map(cache); }
    };
    return view;
  }
  return { durable, traces, tab };
}

function createWebLocks() {
  let queue = Promise.resolve();
  const traces = [];
  return {
    traces,
    request(name, options, callback) {
      const fn = typeof options === 'function' ? options : callback;
      traces.push({ event: 'request', name });
      const run = queue.then(async () => {
        traces.push({ event: 'enter', name });
        try { return await fn({ name }); }
        finally { traces.push({ event: 'exit', name }); }
      });
      queue = run.catch(() => {});
      return run;
    }
  };
}

module.exports = { createStorageOrigin, createWebLocks };
