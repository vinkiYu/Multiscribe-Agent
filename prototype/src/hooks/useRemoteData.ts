import { useCallback, useEffect, useRef, useState } from 'react'

export interface RemoteData<T> {
  data: T | null
  loading: boolean
  error: Error | null
  reload: () => Promise<void>
}

interface UseRemoteDataOptions<T> {
  enabled?: boolean
  fallback?: () => T | Promise<T>
  onSuccess?: (value: T) => void
  onError?: (error: Error) => void
}

export function useRemoteData<T>(load: () => Promise<T>, options: UseRemoteDataOptions<T> = {}): RemoteData<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<Error | null>(null)

  // Hold options in refs so reload's identity stays stable across renders.
  // The previous implementation depended on `load` directly, so any inline
  // arrow function (e.g. `() => dashboardApi.getStats()`) rebuilt `reload` on
  // every render, which retriggered the mount effect, which set loading and
  // re-rendered, looping forever and producing a request storm.
  const loadRef = useRef(load)
  loadRef.current = load
  const enabledRef = useRef(options.enabled !== false)
  enabledRef.current = options.enabled !== false
  const fallbackRef = useRef(options.fallback)
  fallbackRef.current = options.fallback
  const onSuccessRef = useRef(options.onSuccess)
  onSuccessRef.current = options.onSuccess
  const onErrorRef = useRef(options.onError)
  onErrorRef.current = options.onError

  const reload = useCallback(async (): Promise<void> => {
    if (!enabledRef.current) {
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const value = await loadRef.current()
      setData(value)
      onSuccessRef.current?.(value)
    } catch (caught) {
      if (fallbackRef.current) {
        try {
          const value = await fallbackRef.current()
          setData(value)
          onSuccessRef.current?.(value)
          return
        } catch (_) { /* swallow */ }
      }
      const err = caught instanceof Error ? caught : new Error(String(caught))
      setError(err)
      onErrorRef.current?.(err)
    } finally {
      setLoading(false)
    }
  }, [])

  // Only fire on mount; rely on callers (or wsBus subscriptions) for refreshes.
  useEffect(() => {
    void reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return { data, loading, error, reload }
}