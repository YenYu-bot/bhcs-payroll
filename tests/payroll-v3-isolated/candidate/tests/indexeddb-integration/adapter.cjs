'use strict';

// Official fake-indexeddb supplies IndexedDB request/transaction semantics.
// This adapter only instruments API boundaries and injects declared failures.
// It does not simulate OS/disk durability, browser caches, process crashes or
// Firebase. A "crash" test must be described as abort + discarded VM + reopen.
const fake = require('fake-indexeddb');
const packageVersion = require('./node_modules/fake-indexeddb/package.json').version;

function createIDBOrigin() {
  const factory = new fake.IDBFactory(), connections = new Set(), trace = [];
  let sequence = 0, txID = 0;
  const record = event => trace.push({ seq: ++sequence, ...event });
  const control = {
    nextPutError: null, abortNextPutSuccess: false,
    beforePut: null, afterPutSuccess: null, beforeGetSuccess: null, afterTransactionComplete: null,
    openError: null, transactions: new Set()
  };
  function instrumentDB(db) {
    if (connections.has(db)) return;
    connections.add(db);
    const originalTransaction = db.transaction.bind(db);
    db.transaction = (...args) => {
      const tx = originalTransaction(...args), id = ++txID;
      control.transactions.add(tx);
      record({ event:'tx-start', id, mode:tx.mode, stores:[...tx.objectStoreNames] });
      for (const event of ['complete','abort','error']) tx.addEventListener(event, () => {
        record({ event:'tx-'+event, id, error:tx.error?.name ?? null });
        if (event !== 'error') control.transactions.delete(tx);
        if (event === 'complete' && control.afterTransactionComplete) {
          control.afterTransactionComplete({id, tx, db});
        }
      });
      const originalStore = tx.objectStore.bind(tx);
      const stores = new Map();
      tx.objectStore = name => {
        if (stores.has(name)) return stores.get(name);
        const store = originalStore(name);
        for (const method of ['get','put','add','delete','clear']) {
          const original = store[method].bind(store);
          store[method] = (...opArgs) => {
            const write = method !== 'get';
            const descriptor = { id, store:name, method, key:write?opArgs[1]:opArgs[0], value:write?structuredClone(opArgs[0]):undefined };
            record({ event:'request', ...descriptor });
            if (write && control.nextPutError) {
              const error = control.nextPutError; control.nextPutError = null;
              record({ event:'injected-error', id, error:error.name });
              throw error;
            }
            if (write && control.beforePut) control.beforePut({ ...descriptor, tx, db });
            const request = original(...opArgs);
            request.addEventListener('success', () => {
              record({ event:'request-success', id, method });
              if (!write && control.beforeGetSuccess) control.beforeGetSuccess({ ...descriptor, request, tx, db });
              if (write && control.abortNextPutSuccess) {
                control.abortNextPutSuccess = false;
                record({ event:'injected-abort-after-request-success', id }); tx.abort();
              }
              if (write && control.afterPutSuccess) control.afterPutSuccess({ ...descriptor, request, tx, db });
            });
            return request;
          };
        }
        stores.set(name, store); return store;
      };
      return tx;
    };
  }
  const indexedDB = {
    open(...args) {
      if (control.openError) throw control.openError;
      const request = factory.open(...args);
      request.addEventListener('upgradeneeded', () => instrumentDB(request.result));
      request.addEventListener('success', () => instrumentDB(request.result));
      return request;
    },
    deleteDatabase: (...args) => factory.deleteDatabase(...args),
    cmp: (...args) => factory.cmp(...args),
    databases: (...args) => factory.databases(...args)
  };
  return {
    indexedDB, factory, control, trace, packageVersion,
    globals: { indexedDB, IDBKeyRange:fake.IDBKeyRange },
    async open(name, version, upgrade) {
      return new Promise((resolve,reject) => {
        const request = indexedDB.open(name,version);
        request.onupgradeneeded = () => upgrade?.(request.result,request.transaction);
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      });
    },
    closeAll() { for (const db of connections) db.close(); },
    // Synthetic interruption boundary. NOT an actual browser/process crash.
    abortOpenTransactions() { for (const tx of control.transactions) { try { tx.abort(); } catch {} } }
  };
}

function readRecord(db, store, key) {
  return new Promise((resolve,reject) => {
    const tx = db.transaction(store,'readonly');
    const request = tx.objectStore(store).get(key);
    let result;
    request.onsuccess = () => { result = request.result; };
    tx.oncomplete = () => resolve(result);
    tx.onabort = () => reject(tx.error || new DOMException('aborted','AbortError'));
    tx.onerror = () => {};
  });
}

module.exports = { createIDBOrigin, readRecord, packageVersion };
