import { useCallback, useEffect, useState, type ReactElement } from 'react'
import { CheckCircle2, CircleAlert, RadioTower, RefreshCw } from 'lucide-react'
import { adapterHealthApi, ApiError, type AdapterHealth } from './services/api'
import { toast } from 'sonner'

function formatRunAt(value: string | null): string {
  if (!value) return '暂无记录'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN')
}

export function AdapterHealthPage(): ReactElement {
  const [items, setItems] = useState<AdapterHealth[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<ApiError | null>(null)
  const [pending, setPending] = useState<string | null>(null)

  const load = useCallback(async (): Promise<void> => {
    setLoading(true)
    setError(null)
    try { setItems(await adapterHealthApi.list()) } catch (caught) { setError(caught instanceof ApiError ? caught : new ApiError('unknown', '读取适配器健康状态失败')) } finally { setLoading(false) }
  }, [])

  useEffect(() => { void load() }, [load])

  const toggle = async (item: AdapterHealth): Promise<void> => {
    setPending(item.adapter_id)
    try {
      if (item.disabled) await adapterHealthApi.enable(item.adapter_id)
      else await adapterHealthApi.disable(item.adapter_id)
      toast.success(item.disabled ? `已启用 ${item.adapter_id}` : `已停用 ${item.adapter_id}`)
      await load()
    } catch (caught) { toast.error(caught instanceof Error ? caught.message : '更新适配器状态失败') } finally { setPending(null) }
  }

  if (loading) return <section className="state-panel"><RefreshCw className="spin" /><h2>正在读取健康状态</h2><p>正在加载采集适配器的连续失败和运行记录。</p></section>
  if (error) return <section className="state-panel error"><CircleAlert /><h2>健康数据暂时不可用</h2><p>{error.message}</p><button className="button blue" onClick={() => void load()}><RefreshCw />重新连接</button></section>
  if (items.length === 0) return <section className="state-panel"><RadioTower /><h2>还没有适配器运行记录</h2><p>适配器首次执行后，健康状态会显示在这里。</p></section>

  return <div className="data-stack"><section className="data-panel"><div className="data-summary"><RadioTower /><span>适配器健康状态</span><span className="row-meta">{items.length} 个适配器</span><button className="button compact" onClick={() => void load()}><RefreshCw />刷新</button></div><div className="data-list">{items.map((item) => <article className="data-row" key={item.adapter_id}><div><strong>{item.adapter_id}</strong><p>{item.last_error || '最近一次运行没有错误'}</p></div><span className={`status-label ${item.disabled ? 'error' : 'ready'}`}>{item.disabled ? '已停用' : '已启用'}</span><span className="row-meta">连续失败 {item.consecutive_failures}</span><span className="row-meta">{item.last_status || '未知状态'}</span><time>{formatRunAt(item.last_run_at)}</time><button className="button compact" disabled={pending === item.adapter_id} onClick={() => void toggle(item)}>{pending === item.adapter_id ? '处理中' : item.disabled ? '启用' : '停用'}</button></article>)}</div></section><p className="capability-note"><CheckCircle2 /> 健康状态来自服务端持久化记录，停用适配器不会删除历史数据。</p></div>
}
