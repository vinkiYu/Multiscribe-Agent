// WebSocket event bus stub.
// The MultiscribeAgent backend does not expose /api/ws today, so this module
// preserves the public surface (subscribe / emit / start / stop / status) for
// future use while staying completely inert. The WsEvent type union is kept
// here so callers can keep their imports stable.

export type WsEvent =
  | { kind: 'task.updated'; id: string; status: string; finished_at?: string | null }
  | { kind: 'task.log'; id: string; level: 'info' | 'warn' | 'error'; message: string; ts: string }
  | { kind: 'adapter.health'; id: string; disabled: boolean; consecutive_failures: number; last_status: string; last_run_at: string | null }
  | { kind: 'publishing.record'; id: string; channel_id: string; status: string; sent_at: string }
  | { kind: 'content.updated'; id: string; status: string }
  | { kind: 'memory.extracted'; id: string; category: string; confidence: number }
  | { kind: 'settings.changed'; scope: 'providers' | 'sources' | 'plugins' | 'system'; id: string }

export type WsEventKind = WsEvent['kind']

type Listener = (event: WsEvent) => void

type BusStatus = 'idle' | 'closed'

class WsBus {
  private statusValue: BusStatus = 'idle'
  private listeners = new Map<WsEventKind | '*', Set<Listener>>()

  start(): void {
    // No-op: the backend has no /api/ws endpoint. Subscribers remain registered
    // so when a real socket is wired in the future we can simply flip the body.
    this.statusValue = 'closed'
  }

  stop(): void {
    this.statusValue = 'closed'
  }

  subscribe(kind: WsEventKind | '*', listener: Listener): () => void {
    const set = this.listeners.get(kind) ?? new Set<Listener>()
    set.add(listener)
    this.listeners.set(kind, set)
    return () => {
      set.delete(listener)
      if (set.size === 0) this.listeners.delete(kind)
    }
  }

  emit(event: WsEvent): void {
    const typed = this.listeners.get(event.kind)
    if (typed) for (const fn of typed) fn(event)
    const wildcard = this.listeners.get('*')
    if (wildcard) for (const fn of wildcard) fn(event)
  }

  status(): BusStatus {
    return this.statusValue
  }
}

export const wsBus = new WsBus()