import { useState, useEffect, useCallback } from 'react'
import { createPortal } from 'react-dom'
import { listAgents, saveAgent, deleteAgent } from '../services/agentService'
import type { AgentDefinition } from '../services/agentService'
import { listWorkflows, deleteWorkflow } from '../services/workflowService'
import type { WorkflowDefinition } from '../services/workflowService'
import { useToast } from '../context/ToastContext'

const EMPTY_AGENT: Omit<AgentDefinition, 'id'> = {
  name: '新 Agent',
  description: '',
  system_prompt:
    '你是资讯摘要助手。请按规则挑选最相关的内容，并返回包含标题、摘要、相关度评分的列表。',
  provider_id: 'default-openai',
  model: 'gpt-4o-mini',
  temperature: 0.5,
}

const PROVIDER_OPTIONS = [
  { value: 'default-openai', label: 'OpenAI' },
  { value: 'default-anthropic', label: 'Anthropic' },
  { value: 'default-google', label: 'Google' },
  { value: 'default-ollama', label: 'Ollama（本地）' },
]

const MODEL_OPTIONS: Record<string, string[]> = {
  'default-openai': ['gpt-4o-mini', 'gpt-4o', 'gpt-5.4-mini', 'gpt-5.2'],
  'default-anthropic': ['claude-3-5-sonnet', 'claude-3-opus'],
  'default-google': ['gemini-2.0-flash', 'gemini-1.5-pro'],
  'default-ollama': ['llama3.1', 'qwen2.5'],
}

export default function Agents() {
  const { showSuccess, showError } = useToast()
  const [tab, setTab] = useState<'agents' | 'workflows'>('agents')
  const [agents, setAgents] = useState<AgentDefinition[]>([])
  const [workflows, setWorkflows] = useState<WorkflowDefinition[]>([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [editing, setEditing] = useState<AgentDefinition | null>(null)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [a, w] = await Promise.all([listAgents(), listWorkflows()])
      setAgents(a)
      setWorkflows(w)
    } catch (err) {
      showError('加载失败：' + friendlyError(err))
    } finally {
      setLoading(false)
    }
  }, [showError])

  useEffect(() => { load() }, [load])

  const openAdd = () => {
    setEditing({ id: 'agent_' + Date.now(), ...EMPTY_AGENT } as AgentDefinition)
    setErrors({})
    setShowModal(true)
  }

  const openEdit = (a: AgentDefinition) => {
    setEditing({ ...a })
    setErrors({})
    setShowModal(true)
  }

  const closeModal = () => {
    setShowModal(false)
    setEditing(null)
    setErrors({})
  }

  const validate = (): boolean => {
    const e: Record<string, string> = {}
    if (!editing?.name?.trim()) e.name = '请填写名称'
    if (!editing?.provider_id?.trim()) e.provider_id = '请选择模型服务'
    if (!editing?.model?.trim()) e.model = '请选择模型'
    if (!editing?.system_prompt?.trim()) e.system_prompt = '请填写系统指令'
    setErrors(e)
    return Object.keys(e).length === 0
  }

  const handleSave = async () => {
    if (!editing || !validate()) return
    setSaving(true)
    try {
      await saveAgent(editing)
      showSuccess('保存成功')
      closeModal()
      await load()
    } catch (err) {
      showError('保存失败：' + friendlyError(err))
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (a: AgentDefinition) => {
    const ok = window.confirm(
      `删除 Agent「${a.name}」？使用该 Agent 的任务可能无法运行。此操作无法撤销。`,
    )
    if (!ok) return
    try {
      await deleteAgent(a.id)
      await load()
      showSuccess('已删除')
    } catch (err) {
      showError('删除失败：' + friendlyError(err))
    }
  }

  const handleDeleteWf = async (id: string, name: string) => {
    const ok = window.confirm(
      `删除工作流「${name}」？相关定时任务可能无法运行。此操作无法撤销。`,
    )
    if (!ok) return
    try {
      await deleteWorkflow(id)
      await load()
      showSuccess('已删除')
    } catch (err) {
      showError('删除失败：' + friendlyError(err))
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Agent 与生成规则</h1>
          <p>
            Agent 决定使用哪个模型、遵循什么指令以及如何生成摘要。工作流用于将多个处理步骤组合成可重复运行的流程。
          </p>
        </div>
        <div className="actions">
          <button className="btn" onClick={load} disabled={loading} type="button">
            {loading ? <span className="spinner" /> : '刷新'}
          </button>
          {tab === 'agents' && (
            <button className="btn primary" onClick={openAdd} type="button">
              新建 Agent
            </button>
          )}
        </div>
      </div>

      <div className="tabs" style={{ marginBottom: 16 }}>
        <button
          className={'tab ' + (tab === 'agents' ? 'active' : '')}
          onClick={() => setTab('agents')}
          type="button"
        >
          Agent（{agents.length}）
        </button>
        <button
          className={'tab ' + (tab === 'workflows' ? 'active' : '')}
          onClick={() => setTab('workflows')}
          type="button"
        >
          工作流（{workflows.length}）
        </button>
      </div>

      {tab === 'agents' ? (
        agents.length === 0 ? (
          <div className="empty">
            <strong>还没有 Agent</strong>
            <p>Agent 用于定义 AI 如何生成摘要。点击「新建 Agent」开始。</p>
          </div>
        ) : (
          <article className="card">
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>名称</th>
                    <th>模型服务</th>
                    <th>模型</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {agents.map(a => (
                    <tr key={a.id}>
                      <td>
                        <strong>{a.name}</strong>
                        {a.description && (
                          <div className="text-muted text-xs">{a.description}</div>
                        )}
                      </td>
                      <td>{providerLabel(a.provider_id)}</td>
                      <td className="text-mono">{a.model}</td>
                      <td>
                        <div style={{ display: 'flex', gap: 8 }}>
                          <button
                            className="btn"
                            style={{ minHeight: 32, fontSize: 11 }}
                            onClick={() => openEdit(a)}
                            type="button"
                          >
                            编辑
                          </button>
                          <button
                            className="btn ghost"
                            style={{ minHeight: 32, fontSize: 11 }}
                            onClick={() => handleDelete(a)}
                            type="button"
                          >
                            删除
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>
        )
      ) : (
        // Workflows: list only. Editing disabled per P0-4.6 (editor not yet delivered).
        <>
          <div
            className="text-muted text-sm"
            style={{
              padding: 12,
              borderRadius: 6,
              background: 'var(--color-subtle)',
              marginBottom: 16,
            }}
          >
            工作流编辑器即将开放。当前仅支持查看和删除已有工作流。
          </div>
          {workflows.length === 0 ? (
            <div className="empty">
              <strong>暂无工作流</strong>
              <p>工作流编辑器即将开放，敬请期待。</p>
            </div>
          ) : (
            <article className="card">
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>名称</th>
                      <th>步骤数</th>
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {workflows.map(w => (
                      <tr key={w.id}>
                        <td>
                          <strong>{w.name}</strong>
                          {w.description && (
                            <div className="text-muted text-xs">{w.description}</div>
                          )}
                        </td>
                        <td>{w.steps?.length ?? 0}</td>
                        <td>
                          <button
                            className="btn ghost"
                            style={{ minHeight: 32, fontSize: 11 }}
                            onClick={() => handleDeleteWf(w.id, w.name)}
                            type="button"
                          >
                            删除
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </article>
          )}
        </>
      )}

      {showModal && editing && createPortal(
        <div
          className="modal-backdrop"
          onClick={e => {
            if (e.target === e.currentTarget) closeModal()
          }}
        >
          <div className="modal" style={{ maxWidth: 640 }}>
            <div className="modal-head">
              <strong>{editing.id.startsWith('agent_') ? '新建 Agent' : '编辑 Agent'}</strong>
              <button className="btn icon-btn" onClick={closeModal} type="button">
                ×
              </button>
            </div>
            <div className="modal-body">
              <div className="field">
                <label>名称</label>
                <input
                  className="input"
                  value={editing.name ?? ''}
                  onChange={e =>
                    setEditing(p => (p ? { ...p, name: e.target.value } : p))
                  }
                />
                {errors.name && (
                  <span style={{ color: '#c0392b', fontSize: 11 }}>{errors.name}</span>
                )}
              </div>
              <div className="field">
                <label>描述</label>
                <input
                  className="input"
                  value={editing.description ?? ''}
                  placeholder="可选，便于区分用途"
                  onChange={e =>
                    setEditing(p => (p ? { ...p, description: e.target.value } : p))
                  }
                />
              </div>
              <div className="field">
                <label>系统指令</label>
                <textarea
                  className="input"
                  style={{ minHeight: 100 }}
                  value={editing.system_prompt ?? ''}
                  onChange={e =>
                    setEditing(p => (p ? { ...p, system_prompt: e.target.value } : p))
                  }
                />
                <span className="text-muted text-xs">
                  说明这个 Agent 的角色、规则和输出要求。
                </span>
                {errors.system_prompt && (
                  <span style={{ color: '#c0392b', fontSize: 11 }}>{errors.system_prompt}</span>
                )}
              </div>
              <div className="grid cols-2 form-grid-align-start">
                <div className="field">
                  <label>模型服务</label>
                  <select
                    className="input"
                    value={editing.provider_id ?? ''}
                    onChange={e => {
                      const pid = e.target.value
                      setEditing(p =>
                        p
                          ? {
                              ...p,
                              provider_id: pid,
                              model: MODEL_OPTIONS[pid]?.[0] ?? p.model,
                            }
                          : p,
                      )
                    }}
                  >
                    {PROVIDER_OPTIONS.map(o => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                  <span className="text-muted text-xs">
                    选择已经配置并可用的 AI 服务。
                  </span>
                  {errors.provider_id && (
                    <span style={{ color: '#c0392b', fontSize: 11 }}>{errors.provider_id}</span>
                  )}
                </div>
                <div className="field">
                  <label>模型</label>
                  <select
                    className="input"
                    value={editing.model ?? ''}
                    onChange={e =>
                      setEditing(p => (p ? { ...p, model: e.target.value } : p))
                    }
                  >
                    {(MODEL_OPTIONS[editing.provider_id] ?? []).map(m => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
                  </select>
                  {errors.model && (
                    <span style={{ color: '#c0392b', fontSize: 11 }}>{errors.model}</span>
                  )}
                </div>
              </div>
              <div className="field">
                <label>生成随机度</label>
                <input
                  className="input"
                  type="number"
                  step="0.1"
                  min="0"
                  max="2"
                  value={editing.temperature ?? 0.5}
                  onChange={e =>
                    setEditing(p =>
                      p ? { ...p, temperature: parseFloat(e.target.value) } : p,
                    )
                  }
                />
                <span className="text-muted text-xs">
                  数值越低越稳定，越高越有变化。
                </span>
              </div>
            </div>
            <div className="modal-foot">
              <button className="btn" onClick={closeModal} type="button">
                取消
              </button>
              <button
                className="btn primary"
                onClick={handleSave}
                disabled={saving}
                type="button"
              >
                {saving ? <span className="spinner" /> : '保存'}
              </button>
            </div>
          </div>
        </div>,
        document.body,
      )}
    </>
  )
}

function providerLabel(id: string): string {
  return PROVIDER_OPTIONS.find(o => o.value === id)?.label ?? id
}

function friendlyError(err: unknown): string {
  const msg = err instanceof Error ? err.message : String(err)
  if (/Failed to fetch|NetworkError|connect|ECONN/i.test(msg)) {
    return '无法连接服务，请确认 Multiscribe 已启动'
  }
  if (/401|unauthorized/i.test(msg)) {
    return '登录已过期，请重新登录'
  }
  return msg
}
