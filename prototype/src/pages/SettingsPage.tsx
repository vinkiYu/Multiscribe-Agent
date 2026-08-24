import { useEffect, useState, type ReactElement } from 'react'
import { CircleAlert, Eye, EyeOff, KeyRound, Plus, RefreshCw, Save, Settings2, ShieldAlert, Trash } from 'lucide-react'
import { SectionHeading } from '../components/SectionHeading'
import { DataStatus } from '../components/DataStatus'
import { settingsApi, type JsonRecord } from '../services/api'
import { useRemoteData } from '../hooks/useRemoteData'
import type { ModelProvider, SettingsPayload } from '../types'

const tabItems = [
  { key: 'models', label: '模型', icon: <KeyRound /> },
  { key: 'publishers', label: '发布渠道', icon: <Settings2 /> },
  { key: 'system', label: '系统', icon: <Settings2 /> },
  { key: 'plugins', label: '依赖', icon: <ShieldAlert /> },
] as const

type TabKey = (typeof tabItems)[number]['key']

const HTTP_PROXY_KEY = 'http_proxy'

// The backend's GET /api/settings returns { ai_providers, publishers, http_proxy,
// optional_dependencies }. We map the raw response to the legacy `SettingsPayload`
// shape (providers / publishers / plugins / system) used by the page so the rest of
// the UI can stay simple.
function toSettingsPayload(raw: JsonRecord | null): SettingsPayload {
  const fallback: SettingsPayload = {
    providers: [],
    publishers: [],
    sources: [],
    plugins: [],
    system: [],
    http_proxy: null,
    optional_dependencies: { opentelemetry: false, prometheus: false, vector_search: false },
  }
  if (!raw) return fallback
  const providers = Array.isArray(raw.ai_providers) ? (raw.ai_providers as ModelProvider[]) : fallback.providers
  const publishers = Array.isArray(raw.publishers) ? (raw.publishers as SettingsPayload['publishers']) : fallback.publishers
  return {
    ...fallback,
    providers,
    publishers,
    http_proxy: typeof raw.http_proxy === 'string' && raw.http_proxy ? raw.http_proxy : null,
    optional_dependencies: (raw.optional_dependencies as SettingsPayload['optional_dependencies']) ?? fallback.optional_dependencies,
  }
}

export function SettingsPage({ onFlash }: { onFlash: (message: string) => void }): ReactElement {
  const remote = useRemoteData<JsonRecord>(() => settingsApi.get() as unknown as Promise<JsonRecord>, {
    onError: (error) => onFlash(`加载设置失败：${error.message}`),
  })
  const settings = toSettingsPayload(remote.data ?? null)
  const loading = remote.loading && !remote.data
  const error = remote.error?.message ?? null
  const hasData = Boolean(remote.data)

  const [tab, setTab] = useState<TabKey>('models')
  const [providers, setProviders] = useState<ModelProvider[]>(settings.providers)
  const [publishers, setPublishers] = useState<SettingsPayload['publishers']>(settings.publishers)
  const [reveed, setReveed] = useState<Record<string, boolean>>({})
  const [pendingProvider, setPendingProvider] = useState<string | null>(null)
  const [pendingAction, setPendingAction] = useState<string | null>(null)
  const [httpProxy, setHttpProxy] = useState<string>(settings.http_proxy ?? '')

  useEffect(() => {
    if (!settings) return
    if (providers.length === 0 && settings.providers.length > 0) setProviders(settings.providers)
    if (publishers.length === 0 && settings.publishers.length > 0) setPublishers(settings.publishers)
    if (httpProxy === '' && settings.http_proxy) setHttpProxy(settings.http_proxy)
  }, [settings, providers.length, publishers.length, httpProxy])

  const reload = async (): Promise<void> => {
    await remote.reload()
    onFlash('已刷新设置。')
  }

  const persistProvider = async (provider: ModelProvider): Promise<void> => {
    setPendingProvider(provider.id)
    try {
      const next: ModelProvider[] = providers.map((item) => item.id === provider.id ? provider : item)
      await settingsApi.save({ ai_providers: next as unknown as JsonRecord[] })
      onFlash(`Provider「${provider.name}」已保存。`)
      await remote.reload()
    } catch (caught) {
      onFlash(caught instanceof Error ? caught.message : '保存失败')
    } finally {
      setPendingProvider(null)
    }
  }

  const updateProvider = (id: string, patch: Partial<ModelProvider>): void => {
    setProviders((current) => current.map((item) => item.id === id ? { ...item, ...patch } : item))
  }

  const toggleReveal = (id: string): void => {
    setReveed((current) => ({ ...current, [id]: !current[id] }))
  }

  const testProvider = async (id: string): Promise<void> => {
    setPendingProvider(id)
    try {
      const provider = providers.find((item) => item.id === id)
      if (!provider) throw new Error('Provider 不存在')
      const result = await settingsApi.testProvider(id, {
        base_url: provider.base_url,
        api_key: provider.api_key === '' ? undefined : provider.api_key,
      })
      onFlash(`Provider「${provider.name}」连通：${result.model_count} 个模型可用。`)
    } catch (caught) {
      onFlash(caught instanceof Error ? caught.message : '连通性测试失败')
    } finally {
      setPendingProvider(null)
    }
  }

  const listProviderModels = async (id: string): Promise<void> => {
    setPendingProvider(id)
    try {
      const provider = providers.find((item) => item.id === id)
      if (!provider) throw new Error('Provider 不存在')
      const result = await settingsApi.listProviderModels(id, {
        base_url: provider.base_url,
        api_key: provider.api_key === '' ? undefined : provider.api_key,
      })
      const next = providers.map((item) => item.id === id ? { ...item, models: result.models } : item)
      await settingsApi.save({ ai_providers: next as unknown as JsonRecord[] })
      onFlash(`Provider「${provider.name}」模型清单已刷新（${result.models.length} 个）。`)
      await remote.reload()
    } catch (caught) {
      onFlash(caught instanceof Error ? caught.message : '获取模型清单失败')
    } finally {
      setPendingProvider(null)
    }
  }

  const addProvider = (): void => {
    setProviders((current) => [
      ...current,
      {
        id: `custom-${Date.now().toString(36)}`,
        name: '新 Provider',
        type: 'openai',
        enabled: false,
        api_key: '',
        base_url: 'https://',
        use_proxy: false,
        models: [],
        context_window_tokens: {},
        default_output_tokens: {},
      },
    ])
    onFlash('已添加新 Provider 占位，请点击「保存」同步到服务端。')
  }

  const removeProvider = async (id: string): Promise<void> => {
    setPendingProvider(id)
    try {
      const next = providers.filter((item) => item.id !== id)
      await settingsApi.save({ ai_providers: next as unknown as JsonRecord[] })
      setProviders(next)
      onFlash(`已删除 Provider ${id}。`)
      await remote.reload()
    } catch (caught) {
      onFlash(caught instanceof Error ? caught.message : '删除失败')
    } finally {
      setPendingProvider(null)
    }
  }

  const persistPublishers = async (next: SettingsPayload['publishers']): Promise<void> => {
    setPendingAction('publishers')
    try {
      await settingsApi.save({ publishers: next as unknown as JsonRecord[] })
      setPublishers(next)
      onFlash('发布渠道已保存。')
      await remote.reload()
    } catch (caught) {
      onFlash(caught instanceof Error ? caught.message : '保存失败')
    } finally {
      setPendingAction(null)
    }
  }

  const togglePublisher = (id: string): void => {
    const next = publishers.map((item) => item.id === id ? { ...item, enabled: !item.enabled } : item)
    void persistPublishers(next)
  }

  const persistHttpProxy = async (value: string): Promise<void> => {
    setPendingAction(HTTP_PROXY_KEY)
    try {
      await settingsApi.save({ http_proxy: value.trim() || null })
      onFlash('HTTP 代理已更新。')
      await remote.reload()
    } catch (caught) {
      onFlash(caught instanceof Error ? caught.message : '更新失败')
    } finally {
      setPendingAction(null)
    }
  }

  return (
    <>
      <SectionHeading
        title="设置"
        description="配置 AI Provider、发布渠道与系统参数。修改通过 PUT /api/settings 同步到服务端。"
        actions={
          <button className="btn" type="button" onClick={() => void reload()}>
            <RefreshCw /> 刷新
          </button>
        }
      />

      <DataStatus
        loading={loading}
        error={error}
        empty={!hasData && !loading}
        emptyTitle="暂无设置"
        emptyDescription="配置加载失败，请稍后重试。"
        onRetry={() => void remote.reload()}
      >
        <nav className="settings-tabs" role="tablist">
          {tabItems.map((item) => {
            const isActive = tab === item.key
            return (
              <button
                key={item.key}
                type="button"
                role="tab"
                aria-selected={isActive}
                className={isActive ? 'settings-tab is-active' : 'settings-tab'}
                onClick={() => setTab(item.key)}
              >
                {item.icon}
                <span>{item.label}</span>
              </button>
            )
          })}
        </nav>

        {tab === 'models' && (
          <section className="section">
            <div className="settings-section">
              <header>
                <div>
                  <h2>模型 Provider</h2>
                  <p>配置不同提供商的 Base URL 与 API Key。点击「保存」通过 PUT /api/settings 同步到服务端。</p>
                </div>
                <button className="btn" type="button" onClick={addProvider}>
                  <Plus /> 新增 Provider
                </button>
              </header>
              <div className="provider-grid">
                {providers.map((provider) => {
                  const visible = Boolean(reveed[provider.id])
                  const server = settings.providers.find((item) => item.id === provider.id)
                  const dirty = !server || JSON.stringify(server) !== JSON.stringify(provider)
                  return (
                    <article key={provider.id} className="provider-card">
                      <header className="provider-card-header">
                        <div>
                          <strong>{provider.name}</strong>
                          <small>{provider.type} · {provider.models.length} 个模型</small>
                        </div>
                        <span className={provider.enabled ? 'pill pill-builtin' : 'pill pill-neutral'}>
                          {provider.enabled ? '已启用' : '已停用'}
                        </span>
                      </header>

                      <div className="provider-fields">
                        <label className="form-field">
                          <span>显示名称</span>
                          <input type="text" value={provider.name} onChange={(event) => updateProvider(provider.id, { name: event.target.value })} />
                        </label>
                        <label className="form-field">
                          <span>类型</span>
                          <select value={provider.type} onChange={(event) => updateProvider(provider.id, { type: event.target.value })}>
                            <option value="openai">OpenAI</option>
                            <option value="anthropic">Anthropic</option>
                            <option value="google">Google Gemini</option>
                            <option value="ollama">Ollama</option>
                          </select>
                        </label>
                        <label className="form-field form-field-full">
                          <span>Base URL</span>
                          <input type="text" value={provider.base_url} onChange={(event) => updateProvider(provider.id, { base_url: event.target.value })} />
                        </label>
                        <label className="form-field form-field-full">
                          <span>API Key</span>
                          <div className="api-key-row">
                            <input
                              type={visible ? 'text' : 'password'}
                              value={provider.api_key}
                              placeholder="留空表示无需 API Key"
                              onChange={(event) => updateProvider(provider.id, { api_key: event.target.value })}
                            />
                            <button className="rail-icon" type="button" aria-label={visible ? '隐藏' : '显示'} onClick={() => toggleReveal(provider.id)}>
                              {visible ? <EyeOff /> : <Eye />}
                            </button>
                          </div>
                          <small>用于外部调用时验证身份；本地 Ollama 可留空。</small>
                        </label>
                      </div>

                      <footer className="provider-card-footer">
                        <button className="btn btn-sm" type="button" onClick={() => void removeProvider(provider.id)} disabled={pendingProvider === provider.id}>
                          <Trash /> 删除
                        </button>
                        <button className="btn btn-sm" type="button" onClick={() => void listProviderModels(provider.id)} disabled={pendingProvider === provider.id}>
                          拉取模型清单
                        </button>
                        <button className="btn btn-sm" type="button" onClick={() => void testProvider(provider.id)} disabled={pendingProvider === provider.id}>
                          {pendingProvider === provider.id ? '测试中…' : '测试连接'}
                        </button>
                        <button className="btn btn-sm btn-primary" type="button" disabled={pendingProvider === provider.id || !dirty} onClick={() => void persistProvider(provider)}>
                          <Save /> 保存
                        </button>
                      </footer>
                    </article>
                  )
                })}
              </div>
            </div>
          </section>
        )}

        {tab === 'publishers' && (
          <section className="section">
            <div className="settings-section">
              <header>
                <div>
                  <h2>发布渠道</h2>
                  <p>启用或停用已注册的发布渠道。变更通过 PUT /api/settings 整体覆盖。</p>
                </div>
              </header>
              <div className="data-table-card">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>标识</th>
                      <th>类型</th>
                      <th>配置</th>
                      <th>启用</th>
                    </tr>
                  </thead>
                  <tbody>
                    {publishers.length === 0 ? (
                      <tr><td colSpan={4} className="adapter-empty">尚未配置任何发布渠道。</td></tr>
                    ) : publishers.map((publisher) => {
                      const id = String((publisher as unknown as { id: string }).id)
                      const type = String((publisher as unknown as { type: string }).type)
                      const config = (publisher as unknown as { config: Record<string, unknown> }).config ?? {}
                      const enabled = Boolean((publisher as unknown as { enabled: boolean }).enabled)
                      return (
                        <tr key={id}>
                          <td className="data-table-primary">
                            <strong>{id}</strong>
                            <small>{id}</small>
                          </td>
                          <td><span className="pill pill-neutral">{type}</span></td>
                          <td>
                            <code className="version-code">{JSON.stringify(config)}</code>
                          </td>
                          <td>
                            <button
                              type="button"
                              className={enabled ? 'btn btn-sm' : 'btn btn-sm btn-primary'}
                              disabled={pendingAction === 'publishers'}
                              onClick={() => togglePublisher(id)}
                            >
                              {enabled ? '停用' : '启用'}
                            </button>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        )}

        {tab === 'system' && (
          <section className="section">
            <div className="settings-section">
              <header>
                <div>
                  <h2>系统参数</h2>
                  <p>目前仅 HTTP 代理支持持久化（PUT /api/settings → http_proxy）。</p>
                </div>
              </header>
              <div className="form-grid">
                <label className="form-field form-field-full">
                  <span>HTTP 代理</span>
                  <div className="api-key-row">
                    <input
                      type="text"
                      placeholder="例如：http://127.0.0.1:7890"
                      value={httpProxy}
                      onChange={(event) => setHttpProxy(event.target.value)}
                    />
                    <button
                      className="btn btn-sm"
                      type="button"
                      disabled={pendingAction === HTTP_PROXY_KEY}
                      onClick={() => void persistHttpProxy(httpProxy)}
                    >
                      保存
                    </button>
                  </div>
                  <small>用于访问外网 LLM API 与 RSS 源。留空表示直连。</small>
                </label>
              </div>
            </div>

            <div className="settings-section danger-section">
              <header>
                <div>
                  <h2><CircleAlert /> 危险操作</h2>
                  <p>以下操作不可逆，请确认后再继续。</p>
                </div>
              </header>
              <div className="danger-actions">
                <button className="btn" type="button" onClick={() => onFlash('已重置设置为默认值（占位）。')}>
                  <RefreshCw /> 重置为默认
                </button>
                <button className="btn btn-danger" type="button" onClick={() => onFlash('已清空本地数据（占位）。')}>
                  <Trash /> 清空本地数据
                </button>
              </div>
            </div>
          </section>
        )}

        {tab === 'plugins' && (
          <section className="section">
            <div className="settings-section">
              <header>
                <div>
                  <h2>可选依赖</h2>
                  <p>来自 GET /api/settings.optional_dependencies 的能力开关；启停需重启后端。</p>
                </div>
              </header>
              <div className="metric-grid metric-grid-compact">
                <DependencyCard label="OpenTelemetry" enabled={settings.optional_dependencies.opentelemetry} description="链路追踪导出" />
                <DependencyCard label="Prometheus" enabled={settings.optional_dependencies.prometheus} description="/metrics 指标抓取" />
                <DependencyCard label="Vector Search" enabled={settings.optional_dependencies.vector_search} description="KB 向量检索" />
              </div>
              <p className="capability-note">依赖配置通过 env / SystemSettings 控制，前端只负责展示。</p>
            </div>
          </section>
        )}
      </DataStatus>
    </>
  )
}

function DependencyCard({ label, enabled, description }: { label: string; enabled: boolean; description: string }): ReactElement {
  return (
    <article className={`metric ${enabled ? 'metric-blue' : 'metric-muted'}`}>
      <strong>{label}</strong>
      <span className={`pill ${enabled ? 'pill-builtin' : 'pill-neutral'}`}>
        {enabled ? '已启用' : '未启用'}
      </span>
      <small>{description}</small>
    </article>
  )
}