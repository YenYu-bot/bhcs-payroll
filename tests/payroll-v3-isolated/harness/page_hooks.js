/* BSDK page instrumentation v2 (test-only). Never replaces IndexedDB or the Firebase SDK; only wraps.
 * Guard: window.FB_BASE points to a deliberately missing LOCAL path so the candidate's own fbLoad()
 * can never import an SDK nor run initializeApp(FB_CONFIG) for the production project.
 * Candidate globals (cloudRequest, ensureStorageCurrent, beginCloudWrite, persistSnapshot) are classic-script
 * function declarations, so reassigning window.<name> changes the binding the candidate itself calls.
 */
(() => {
  if (!window.__BSDK_NO_FB_GUARD) window.FB_BASE = location.origin + '/__candidate_fbLoad_forbidden__/';
  const DB = 'bhcs-payroll-safe-storage';
  const T = window.__bsdk = {tx: [], sdk: {runTransaction: 0, txAttempts: 0, getDocFromServer: 0, onSnapshot: 0}, events: [], gates: {},
    reqs: [], staged: [], settled: {callbacks: 0, transactions: 0}};
  T.ev = (what, extra) => T.events.push(Object.assign({what, t: performance.now()}, extra || {}));
  const origTx = IDBDatabase.prototype.transaction;
  IDBDatabase.prototype.transaction = function (...a) {
    const t = origTx.apply(this, a);
    if (this.name === DB && a[1] === 'readwrite') { const r = {created: performance.now(), complete: false, aborted: false};
      T.tx.push(r); t.addEventListener('complete', () => r.complete = true); t.addEventListener('abort', () => r.aborted = true); }
    return t;
  };
  T.gate = name => { const g = T.gates[name] = {reached: false, released: false, settled: false}; g.p = new Promise(r => g.open = r); return g; };
  T.release = name => { const g = T.gates[name]; g.released = performance.now(); g.open(); return true; };
  T.read = () => new Promise((res, rej) => { const rq = indexedDB.open(DB);
    rq.onupgradeneeded = () => { rq.transaction.abort(); rej(new Error('no canonical DB')); }; rq.onerror = () => rej(rq.error);
    rq.onsuccess = () => { const db = rq.result; let v; const t = db.transaction('state', 'readonly'); const g = t.objectStore('state').get('root');
      g.onsuccess = () => v = g.result; t.oncomplete = () => { db.close(); res(v === undefined ? null : v); }; t.onabort = () => { db.close(); rej(t.error); }; }; });
  T.decrypt = async (packet, pw, saltB64) => { const b = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));
    const base = await crypto.subtle.importKey('raw', new TextEncoder().encode(pw), 'PBKDF2', false, ['deriveKey']);
    const k = await crypto.subtle.deriveKey({name: 'PBKDF2', salt: b(saltB64), iterations: 250000, hash: 'SHA-256'}, base, {name: 'AES-GCM', length: 256}, false, ['decrypt']);
    return new TextDecoder().decode(await crypto.subtle.decrypt({name: 'AES-GCM', iv: b(packet.iv)}, k, b(packet.ct))); };
  /* Canonical view of the native root: encrypted values are replaced by their plaintext (decrypted with the
   * candidate's own decStr + current key), so a legitimate persistSnapshot that only changes IV / revision
   * does not count as a data change. revision itself is excluded. */
  T.canonical = async () => { const root = await T.read(); if (!root) return null; const out = {};
    for (const [k, v] of Object.entries(root.values || {}).sort()) {
      let p = null; try { p = typeof v === 'string' ? JSON.parse(v) : null; } catch (e) {}
      if (p && typeof p === 'object' && typeof p.ct === 'string' && typeof p.iv === 'string') {
        try { out[k] = {plain: await decStr(p, sec.key)}; } catch (e) { out[k] = {undecryptable: true, ct: p.ct}; }
      } else out[k] = v; }
    return JSON.stringify(out); };
  /* Request tracking: every cloudRequest gets an id and stage events; timestamps are performance.now(). */
  T.trackRequests = () => { if (T.tracking) return; T.tracking = true; const orig = window.cloudRequest;
    window.cloudRequest = function (epoch, run, write = false, requireStore = true) {
      const r = {id: T.reqs.length + 1, write, start: performance.now(), stage: 'pre-run-checks', ensureCalls: 0, end: null, outcome: null, code: null};
      T.reqs.push(r); T.ev('req:start', {req: r.id, write});
      const run2 = async ticket => { r.stage = 'run'; T.ev('req:run-start', {req: r.id});
        try { const v = await run(ticket); r.stage = 'run-resolved'; T.ev('req:run-resolved', {req: r.id}); return v; }
        catch (e) { r.stage = 'run-rejected'; T.ev('req:run-rejected', {req: r.id, msg: String(e && e.message)}); throw e; } };
      return orig.call(this, epoch, run2, write, requireStore).then(
        v => { r.end = performance.now(); r.outcome = 'resolved'; T.ev('req:resolved', {req: r.id}); return v; },
        e => { r.end = performance.now(); r.outcome = 'rejected'; r.code = e && e.code || null; T.ev('req:rejected', {req: r.id, code: r.code, msg: String(e && e.message).slice(0, 120)}); throw e; }); };
    const origEnsure = window.ensureStorageCurrent;
    window.ensureStorageCurrent = async function (...a) {
      const live = T.reqs.filter(x => x.end === null); const cur = live[live.length - 1] || null;
      if (cur) cur.ensureCalls++;
      const g = T.gates.postRunCheck;
      if (g && !g.reached && cur && cur.stage === 'run-resolved' && (!T.holdTarget || T.holdTarget(cur))) {
        g.reached = performance.now(); g.req = cur.id; g.callIndex = cur.ensureCalls; g.msSinceRequestStart = g.reached - cur.start;
        T.ev('post-run ensureStorageCurrent:held', {req: cur.id, callIndex: cur.ensureCalls}); await g.p; g.settled = performance.now(); }
      return origEnsure.apply(this, a); }; };
  /* Wrap official SDK entry points after test wiring. */
  T.instrumentSdk = () => {
    const fs = cloud.fs, origRT = fs.runTransaction, origGet = fs.getDocFromServer, origSnap = fs.onSnapshot;
    cloud.fs = Object.assign(Object.create(null), fs, {
      runTransaction: async (db, fn, ...rest) => { T.sdk.runTransaction++; const n = T.sdk.runTransaction; T.ev('runTransaction:start', {n});
        const g = T.gates.ackHold, mg = T.gates.metaHold, eg = T.gates.entryHold;
        const wrapped = async tx => { T.sdk.txAttempts++; const st = {n, attempt: T.sdk.txAttempts, sets: {}, deletes: []}; T.staged.push(st);
          if (eg && !eg.released) { eg.reached = performance.now(); T.ev('callback-entry:held'); await eg.p; }
          const proxy = {get: async ref => { const r = await tx.get(ref);
              if (mg && ref.id === 'meta' && !mg.released) { mg.reached = performance.now(); T.ev('tx.get(meta):held-after-real-read'); await mg.p; }
              return r; },
            set: (ref, data, ...o) => { T.ev('tx.set', {id: ref.id}); const c = Object.assign({}, data); if (ref.id === 'meta') delete c.updatedAt; st.sets[ref.id] = c; tx.set(ref, data, ...o); return proxy; },
            update: (...a) => { T.ev('tx.update', {id: a[0].id}); tx.update(...a); return proxy; },
            delete: ref => { T.ev('tx.delete', {id: ref.id}); st.deletes.push(ref.id); tx.delete(ref); return proxy; }};
          try { const v = await fn(proxy); T.ev('txCallback:settled', {n, ok: true}); return v; }
          catch (e) { T.ev('txCallback:settled', {n, ok: false, msg: String(e && e.message).slice(0, 120)}); throw e; }
          finally { T.settled.callbacks++; } };
        let out;
        try { out = await origRT.call(fs, db, wrapped, ...rest); T.ev('runTransaction:sdk-resolved', {n}); }
        catch (e) { T.ev('runTransaction:sdk-rejected', {n, code: e && e.code || null, msg: String(e && e.message).slice(0, 120)}); T.settled.transactions++; throw e; }
        T.settled.transactions++;
        if (g && !g.released) { g.reached = performance.now(); T.ev('ack:held-after-real-commit'); await g.p; g.settled = performance.now(); T.ev('ack:released'); }
        return out; },
      getDocFromServer: async (...a) => { T.sdk.getDocFromServer++; const r = await origGet.apply(fs, a); T.ev('getDocFromServer:resolved', {id: a[0] && a[0].id}); return r; },
      onSnapshot: (...a) => { T.sdk.onSnapshot++; return origSnap.apply(fs, a); }
    });
  };
  /* BSDK07 baseline + CAS gates. */
  T.armIntent = (casGate) => { const orig = window.beginCloudWrite;
    window.beginCloudWrite = async function (...a) {
      T.intentBaseline = await T.canonical(); T.intentBaselineRevision = (await T.read()).revision; T.ev('intent:baseline-captured');
      const g = casGate && T.gates[casGate]; if (g && !g.reached) { g.reached = performance.now(); T.ev(casGate + ':held'); await g.p; }
      return orig.apply(this, a); }; };
  /* snapshot-CAS gate. Install only AFTER the initial save has settled. Holds only the first persistSnapshot call whose
   * synchronous caller frame is `requireCaller` (e.g. 'cloudPushLocked'); every other call passes straight through and
   * is recorded, so the case can prove which call reached the gate. */
  T.armSnapshotCas = (requireCaller) => { const orig = window.persistSnapshot, g = T.gate('snapCas'); T.snapCalls = [];
    window.persistSnapshot = async function (...a) {
      const stack = String(new Error().stack).split('\n').slice(2, 8).map(x => x.trim().replace(/^at /, '').replace(/\s*\(.*\)$/, '').trim());
      const match = !requireCaller || stack.some(f => f === requireCaller || f === 'async ' + requireCaller);
      T.snapCalls.push({t: performance.now(), stack, held: match && !g.reached, busy: cloud.busy, opsPending: persistence.operations});
      if (match && !g.reached) { g.stack = stack; g.reached = performance.now(); T.snapBaseline = await T.canonical(); T.ev('snapCas:held', {stack}); await g.p; g.settled = performance.now(); }
      return orig.apply(this, a); }; };
  /* Another tab's legitimate write: same values, revision+1 (separate native connection). */
  T.peerBump = (marker) => new Promise((res, rej) => { const o = indexedDB.open(DB); o.onerror = () => rej(o.error);
    o.onsuccess = () => { const db = o.result, t = db.transaction('state', 'readwrite'), s = t.objectStore('state'), g = s.get('root'); let rev;
      g.onsuccess = () => { const v = g.result; if (marker !== undefined) v.values.bhcs_payroll_cloudwrite = marker; v.revision++; rev = v.revision; s.put(v, 'root'); };
      t.oncomplete = () => { db.close(); res(rev); }; t.onabort = () => { db.close(); rej(t.error); }; }; });
  /* BSDK07 precise native fault on the root put whose CLOUD_WRITE value is a new operation marker. */
  T.cloudWriteFault = mode => { const np = IDBObjectStore.prototype.put; T.fault = {mode, hits: 0, requestSucceeded: false, aborted: false};
    IDBObjectStore.prototype.put = function (v, k) {
      let target = false; try { const m = JSON.parse(v && v.values && v.values.bhcs_payroll_cloudwrite || 'null'); target = k === 'root' && m && m.id && m.base !== undefined; } catch (e) {}
      if (!target || T.fault.hits) return np.call(this, v, k);
      T.fault.hits++;
      if (mode === 'quota') throw new DOMException('synthetic targeted quota (NOT real exhaustion)', 'QuotaExceededError');
      const r = np.call(this, v, k), t = this.transaction;
      r.addEventListener('success', () => { T.fault.requestSucceeded = true; t.abort(); T.fault.aborted = true; });
      return r; };
    T.restorePut = () => { IDBObjectStore.prototype.put = np; }; };
})();
