import { useEffect, useState } from 'react'
import { useRemoteData } from './useRemoteData'
import { wsBus, type WsEvent, type WsEventKind } from '../services/wsBus'
import { onReplay, readSnapshot, saveSnapshot } from '../services/offlineCache'

interface LiveOptions<T> {
  cacheKey?: string
  cacheTtlMs?: number
  enabled?: boolean
  fallback?: () => T | Promise<T>
  events: WsEventKind[]
}

interface LiveResource<T> extends ReturnType<typeof useRemoteData<T>> {
  status: 'idle' | 'connecting' | 'open' | 'closed'
  lastEvent: WsEvent | null
  replayed: boolean
}

export function useLiveResource<T>(load: () => Promise<T>, options: LiveOptions<T>): LiveResource<T> {
  const remote = useRemoteData<T>(load, { enabled: options.enabled, fallback: options.fallback })
  const [status, setStatus] = useState(wsBus.status())
  const [lastEvent, setLastEvent] = useState<WsEvent | null>(null)
  const [replayed, setReplayed] = useState<boolean>(false)
  const cacheKey = options.cacheKey
  const cacheTtlMs = options.cacheTtlMs ?? 60 * 60_000

  useEffect(() => {
    const offStatus = wsBus.subscribe('*', () => setStatus(wsBus.status()))
    const offReplay = onReplay(() => setReplayed(true))
    return () => { offStatus(); offReplay() }
  }, [])

  useEffect(() => {
    const handlers = options.events.map((kind) => {
      return wsBus.subscribe(kind, (event) => {
        setLastEvent(event)
        void remote.reload()
      })
    })
    return () => {
      for (const off of handlers) off()
    }
  }, [remote, options.events])

  // Persist successful loads to IndexedDB; on next mount + fetch failure, fall back.
  useEffect(() => {
    if (!cacheKey || !remote.data) return
    void saveSnapshot<T>(cacheKey, remote.data, cacheTtlMs)
  }, [cacheKey, cacheTtlMs, remote.data])

  // On error with cache available, fire replay signal so UI can show a banner.
  useEffect(() => {
    if (!cacheKey || !remote.error) return
    void readSnapshot<T>(cacheKey).then((cached) => {
      if (cached) setReplayed(true)
    })
  }, [cacheKey, remote.error])

  return { ...remote, status, lastEvent, replayed }
}

export async function readCachedResource<T>(key: string): Promise<T | null> {
  return readSnapshot<T>(key)
}