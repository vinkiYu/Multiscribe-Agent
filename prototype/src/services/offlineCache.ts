// IndexedDB cache + offline replay layer.
// Persists last successful fetch per resource; restores on remount when network is unavailable.

const DB_NAME = 'multiscribe-cache'
const DB_VERSION = 1
const STORE = 'snapshots'

type Listener = (event: 'replayed') => void

interface CacheState {
  db: IDBDatabase | null
  listeners: Set<Listener>
  available: boolean
}

const state: CacheState = {
  db: null,
  listeners: new Set(),
  available: typeof indexedDB !== 'undefined',
}

function open(): Promise<IDBDatabase | null> {
  if (!state.available) return Promise.resolve(null)
  if (state.db) return Promise.resolve(state.db)
  return new Promise((resolve) => {
    const request = window.indexedDB.open(DB_NAME, DB_VERSION)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE)
      }
    }
    request.onsuccess = () => {
      state.db = request.result
      resolve(request.result)
    }
    request.onerror = () => {
      state.available = false
      resolve(null)
    }
  })
}

export interface CacheEntry<T> {
  key: string
  data: T
  savedAt: number
  ttlMs: number
}

export async function saveSnapshot<T>(key: string, data: T, ttlMs = 60 * 60_000): Promise<void> {
  const db = await open()
  if (!db) return
  try {
    const tx = db.transaction(STORE, 'readwrite')
    tx.objectStore(STORE).put({ data, savedAt: Date.now(), ttlMs }, key)
    await txDone(tx)
  } catch {
    // noop — quota or private mode
  }
}

export async function readSnapshot<T>(key: string): Promise<T | null> {
  const db = await open()
  if (!db) return null
  try {
    const tx = db.transaction(STORE, 'readonly')
    return await new Promise<T | null>((resolve) => {
      const request = tx.objectStore(STORE).get(key)
      request.onsuccess = () => {
        const entry = request.result as CacheEntry<T> | undefined
        if (!entry) {
          resolve(null)
          return
        }
        if (Date.now() - entry.savedAt > entry.ttlMs) {
          resolve(null)
          return
        }
        resolve(entry.data)
      }
      request.onerror = () => resolve(null)
    })
  } catch {
    return null
  }
}

export async function dropSnapshot(key: string): Promise<void> {
  const db = await open()
  if (!db) return
  try {
    const tx = db.transaction(STORE, 'readwrite')
    tx.objectStore(STORE).delete(key)
    await txDone(tx)
  } catch { /* noop */ }
}

export async function clearAll(): Promise<void> {
  const db = await open()
  if (!db) return
  try {
    const tx = db.transaction(STORE, 'readwrite')
    tx.objectStore(STORE).clear()
    await txDone(tx)
  } catch { /* noop */ }
}

export function onReplay(listener: Listener): () => void {
  state.listeners.add(listener)
  return () => { state.listeners.delete(listener) }
}

export function emitReplay(): void {
  for (const fn of state.listeners) fn('replayed')
}

function txDone(tx: IDBTransaction): Promise<void> {
  return new Promise((resolve) => {
    tx.oncomplete = () => resolve()
    tx.onerror = () => resolve()
    tx.onabort = () => resolve()
  })
}