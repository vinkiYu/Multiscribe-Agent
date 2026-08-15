import { useEffect, useMemo, useState, type ReactElement } from 'react'
import { CheckCircle2, CircleAlert, Clock3, ExternalLink, LoaderCircle, RefreshCw, Send, Wifi } from 'lucide-react'
import { SectionHeading } from '../components/SectionHeading'
import { DataStatus } from '../components/DataStatus'
import { channelsApi, publishingApi, type JsonRecord } from '../services/api'
import { useRemoteData } from '../hooks/useRemoteData'
import type { PublishChannel, PublishRecord } from '../types'

type ChannelStatus = 'connected' | 'error' | 'paused' | 'disabled' | 'unknown'
type RecordStatus = 'success' | 'failed' | 'pending' | 'retrying' | string

function recordStatusClass(status: RecordStatus): string {
  if (status === 'success') return 'record-status-success'
  if (status === 'failed' || status === 'error') return 'record-status-error'
  if (status === 'pending') return 'record-status-pending'
  if (status === 'retrying') return 'record-status-retrying'
  return 'record-status-pending'
}

function recordStatusLabel(status: RecordStatus): string {
  if (status === 'success') return '成功'
  if (status === 'failed' || status === 'error') return '失败'
  if (status === 'pending') return '等待中'
  if (status === 'retrying') return '重试中'
  return status
}

function channelStatus(status: PublishChannel['enabled']): ChannelStatus {
  if (status === true) return 'connected'
  if (status === false) return 'paused'
  return 'unknown'
}

function formatRelativeTime(iso: string): string {
  if (!iso) return '尚未发送'
  const value = Date.parse(iso)
  if (Number.isNaN(value)) return iso
  const diff = Math.max(0, Date.now() - value)
  const minutes = Math.round(diff / 60_000)
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  if (minutes < 1440) return `${Math.round(minutes / 60)} 小时前`
  return `${Math.round(minutes / 1440)} 天前`
}

function summarizeRecords(records: PublishRecord[]) {
  return {
    success: records.filter((r) => r.status === 'success').length,
    error: records.filter((r) => r.status === 'failed' || r.status === 'error').length,
    pending: records.filter((r) => r.status === 'pending' || r.status === 'retrying').length,
    sentToday: records.filter((r) => {
      const value = Date.parse(r.published_at)
      if (Number.isNaN(value)) return false
      return Date.now() - value < 24 * 60 * 60_000
    }).length,
  }
}

export function PublishingPage({ onFlash }: { onFlash: (message: string) => void }): ReactElement {
  const channelsRemote = useRemoteData<JsonRecord[]>(() => channelsApi.list())
  const recordsRemote = useRemoteData<{ records: JsonRecord[]; total: number; has_more: boolean }>(() => publishingApi.list({ limit: 100 }))
  const channels = (channelsRemote.data ?? []) as unknown as PublishChannel[]
  const records = (recordsRemote.data?.records ?? []) as unknown as PublishRecord[]
  const loading = (channelsRemote.loading || recordsRemote.loading) && !channelsRemote.data && !recordsRemote.data
  const error = channelsRemote.error?.message ?? recordsRemote.error?.message ?? null
  const hasData = Boolean(channelsRemote.data) || Boolean(recordsRemote.data)

  const [activeChannelId, setActiveChannelId] = useState<string>(channels[0]?.id ?? '')
  const [activeRecordId, setActiveRecordId] = useState<string | null>(null)

  useEffect(() => {
    if (!activeChannelId && channels.length > 0) setActiveChannelId(channels[0].id)
  }, [channels, activeChannelId])

  const activeChannel = channels.find((c) => c.id === activeChannelId) ?? null
  const filteredRecords = useMemo(() => records.filter((r) => r.publisher_id === activeChannelId), [records, activeChannelId])
  const activeRecord = filteredRecords.find((r) => r.id === activeRecordId) ?? filteredRecords[0] ?? null

  const summary = {
    connected: channels.filter((c) => channelStatus(c.enabled) === 'connected').length,
    error: 0,
    paused: channels.filter((c) => channelStatus(c.enabled) === 'paused').length,
    sentToday: summarizeRecords(records).sentToday,
  }

  const reload = async (): Promise<void> => {
    await Promise.all([channelsRemote.reload(), recordsRemote.reload()])
    onFlash('已刷新发布记录。')
  }

  return (
    <>
      <SectionHeading
        icon={<Send />}
        title="发布记录"
        description="查看各渠道的最近投递结果。GET /api/publish-history 与 GET /api/settings.publishers。"
        actions={
          <>
            <button className="btn" type="button" onClick={reload}>
              <RefreshCw /> 刷新
            </button>
            <button className="btn btn-primary" type="button" onClick={() => onFlash('重试失败投递：调用 channels 后端 /retry 接口')}>
              <RefreshCw /> 重试失败
            </button>
          </>
        }
      />

      <DataStatus
        loading={loading}
        error={error}
        empty={!hasData && !loading}
        emptyTitle="暂无投递记录"
        emptyDescription="完成首次发布后，投递记录会显示在这里。"
        onRetry={reload}
      >
        <section className="section">
          <div className="publish-summary">
            <SummaryItem icon={<Wifi />} label="已启用渠道" value={summary.connected} tone="green" />
            <SummaryItem icon={<CircleAlert />} label="异常渠道" value={summary.error} tone="amber" />
            <SummaryItem icon={<Clock3 />} label="已停用渠道" value={summary.paused} tone="muted" />
            <SummaryItem icon={<Send />} label="今日投递" value={summary.sentToday} tone="cyan" />
          </div>
        </section>

        <section className="section">
          <div className="publish-layout">
            <aside className="publish-channels" aria-label="发布渠道">
              <header className="publish-channels-header">
                <strong>发布渠道</strong>
                <span>{channels.length} 个</span>
              </header>
              <ul className="publish-channels-list">
                {channels.length === 0 ? (
                  <li className="publish-channel-empty">尚未注册任何渠道。</li>
                ) : channels.map((channel) => {
                  const isActive = channel.id === activeChannelId
                  const status = channelStatus(channel.enabled)
                  return (
                    <li key={channel.id}>
                      <button
                        type="button"
                        className={isActive ? 'publish-channel-item is-active' : 'publish-channel-item'}
                        onClick={() => { setActiveChannelId(channel.id); setActiveRecordId(null) }}
                      >
                        <span className="publish-channel-icon" aria-hidden="true"><Send /></span>
                        <span className="publish-channel-copy">
                          <strong>{channel.id}</strong>
                          <small>{channel.type} · {channel.enabled ? '已启用' : '已停用'}</small>
                        </span>
                        <span className={`channel-status channel-status-${status}`}>
                          {status === 'connected' && <CheckCircle2 />}
                          {status === 'paused' && <Clock3 />}
                          {status === 'unknown' && <CircleAlert />}
                        </span>
                      </button>
                    </li>
                  )
                })}
              </ul>
            </aside>

            <article className="publish-records" aria-label="投递记录">
              <header className="publish-records-header">
                <div>
                  <h2>{activeChannel?.id ?? '渠道'}</h2>
                  <p>{activeChannel ? `${activeChannel.type} · 投递历史 ${filteredRecords.length} 条` : '请选择左侧渠道'}</p>
                </div>
              </header>
              {filteredRecords.length === 0 ? (
                <div className="empty-card">
                  <div>
                    <div className="empty-icon" aria-hidden="true"><Send /></div>
                    <h3 className="empty-title">该渠道暂无投递</h3>
                    <p className="empty-description">配置任务后，渠道会自动接收摘要投递。</p>
                  </div>
                </div>
              ) : (
                <table className="data-table publish-record-table">
                  <thead>
                    <tr>
                      <th>内容</th>
                      <th>状态</th>
                      <th>发布时间</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredRecords.map((record) => {
                      const isActive = record.id === activeRecord?.id
                      return (
                        <tr key={record.id} className={isActive ? 'is-active' : ''} onClick={() => setActiveRecordId(record.id)}>
                          <td className="data-table-primary">
                            <strong>{record.title}</strong>
                            <small>{record.id}</small>
                          </td>
                          <td>
                            <span className={`record-status ${recordStatusClass(record.status)}`}>
                              {record.status === 'success' && <CheckCircle2 />}
                              {record.status === 'failed' && <CircleAlert />}
                              {record.status === 'pending' && <LoaderCircle />}
                              {record.status === 'retrying' && <RefreshCw />}
                              {recordStatusLabel(record.status)}
                            </span>
                          </td>
                          <td>{formatRelativeTime(record.published_at)}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              )}
            </article>

            <aside className="publish-detail" aria-label="投递详情">
              {!activeRecord ? (
                <div className="state-panel"><Send /><h2>选择投递记录</h2><p>记录选中后，可在此查看响应、result_data 与错误详情。</p></div>
              ) : (
                <>
                  <header className="publish-detail-header">
                    <div>
                      <h2>{activeRecord.title}</h2>
                      <p>{activeRecord.id} · {formatRelativeTime(activeRecord.published_at)}</p>
                    </div>
                    <span className={`record-status ${recordStatusClass(activeRecord.status)}`}>
                      {recordStatusLabel(activeRecord.status)}
                    </span>
                  </header>

                  <section className="publish-detail-section">
                    <h3>摘要</h3>
                    <p className="publish-response">{activeRecord.content_preview ?? '—'}</p>
                  </section>

                  {activeRecord.error_message && (
                    <section className="publish-detail-section">
                      <h3><CircleAlert /> 错误信息</h3>
                      <p className="publish-error">{activeRecord.error_message}</p>
                    </section>
                  )}

                  {activeRecord.result_data && (
                    <section className="publish-detail-section">
                      <h3>响应</h3>
                      <pre className="publish-payload">{JSON.stringify(activeRecord.result_data, null, 2)}</pre>
                    </section>
                  )}

                  <footer className="publish-detail-footer">
                    <a className="btn" href="#" onClick={(event) => event.preventDefault()}>
                      查看原始日志 <ExternalLink />
                    </a>
                  </footer>
                </>
              )}
            </aside>
          </div>
        </section>
      </DataStatus>
    </>
  )
}

function SummaryItem({ icon, label, value, tone }: { icon: ReactElement; label: string; value: number; tone: 'green' | 'amber' | 'cyan' | 'muted' }): ReactElement {
  return (
    <article className={`publish-summary-item tone-${tone}`}>
      <span className="publish-summary-icon" aria-hidden="true">{icon}</span>
      <div>
        <strong>{value}</strong>
        <small>{label}</small>
      </div>
    </article>
  )
}