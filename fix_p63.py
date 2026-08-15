"""Insert AgentsConfigPage into ui.tsx before the existing export block."""
import re

path = 'prototype/src/shared/ui.tsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

NEW_FUNC = '''function AgentsConfigPage(): ReactElement {
  const remote = useRemoteData(agentsApi.list)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [draft, setDraft] = useState<AgentDefinition | null>(null)
  const [skillOptions, setSkillOptions] = useState<{ id: string; name: string }[]>([])
  const [settingsState] = useState<{ data: any }>({ data: null })
  const [tryInput, setTryInput] = useState('')
  const [tryEvents, setTryEvents] = useState<{ type: string; data: Record<string, unknown> }[]>([])
  const [trying, setTrying] = useState(false)
  const [saving, setSaving] = useState(false)
  const status = DataStatus({ remote, empty: false })
  useEffect(() => {
    if (remote.data?.length && !remote.data.some((agent) => agent.id === selectedId)) {
      setSelectedId(remote.data[0].id)
    }
  }, [remote.data, selectedId])
  useEffect(() => { void skillsApi.list().then((list) => setSkillOptions(list.map((s) => ({ id: s.id, name: s.name })))).catch(() => undefined) }, [])
  useEffect(() => { void settingsApi.get().then((data) => { settingsState.data = data }).catch(() => undefined) }, [])
  useEffect(() => {
    if (remote.data) {
      const current = remote.data.find((a) => a.id === selectedId) ?? remote.data[0]
      if (current) setDraft({ ...current })
    }
  }, [remote.data, selectedId])
  if (status) return status
  const data = remote.data!
  const selected = draft
  const settings = settingsState.data as any
  const providers = (settings?.ai_providers ?? []) as { id: string; models: string[]; name: string }[]
  const provider = providers.find((p) => p.id === selected?.provider_id)
  const allTools = [
    { id: 'read_artifact', risk: 'low', label: '读取压缩工具结果' },
    { id: 'search_source_data', risk: 'low', label: 'FTS 搜索资讯' },
    { id: 'execute_command', risk: 'high', label: '执行命令（需审批）' },
  ]
  const newAgentTemplate = (): AgentDefinition => ({
    id: 'agent-' + Date.now(),
    name: '',
    description: '',
    system_prompt: '',
    provider_id: providers[0]?.id ?? 'default-openai',
    model: providers[0]?.models[0] ?? 'gpt-4o-mini',
    temperature: 0.7,
    max_output_tokens: null,
    tool_ids: [],
    skill_ids: [],
    mcp_server_ids: [],
    streaming: false,
    is_hidden: false,
    category: null,
  })
  const selectAgent = (id: string | null) => {
    setSelectedId(id)
    if (id === null) setDraft(null)
    else {
      const next = data.find((a) => a.id === id)
      if (next) setDraft({ ...next })
    }
  }
  const updateDraft = (patch: Partial<AgentDefinition>) => {
    setDraft((current) => (current ? { ...current, ...patch } : current))
  }
  const save = async () => {
    if (!draft) return
    if (!draft.id.trim() || !draft.name.trim() || !draft.system_prompt.trim()) {
      toast.error('id、名称、系统提示词必填')
      return
    }
    setSaving(true)
    try {
      await agentsApi.save(draft)
      toast.success('Agent 已保存')
      await remote.reload()
    } catch (caught) {
      toast.error(caught instanceof Error ? caught.message : '保存 Agent 失败')
    } finally { setSaving(false) }
  }
  const remove = async (id: string) => {
    if (!window.confirm('删除 Agent ' + id + '？此操作会从知识库中移除该 Agent 定义。')) return
    try {
      await agentsApi.remove(id)
      toast.success('已删除 Agent ' + id)
      if (selectedId === id) setSelectedId(null)
      await remote.reload()
    } catch (caught) {
      toast.error(caught instanceof Error ? caught.message : '删除 Agent 失败')
    }
  }
  const tryRun = async () => {
    if (!selected) return
    if (!tryInput.trim()) return
    setTrying(true)
    setTryEvents([])
    try {
      await agentsApi.run(selected.id, tryInput, (event) => {
        const eventType = String(event.type)
        if (eventType === 'content') {
          const delta = String(event.data.delta ?? '')
          if (!delta) return
          setTryEvents((prev) => {
            const has = prev.some((e) => e.type === 'streaming')
            if (!has) return [...prev, { type: 'streaming', data: { content: delta } }]
            return prev.map((e) => e.type === 'streaming' ? { ...e, data: { ...e.data, content: String(e.data.content ?? '') + delta } } : e)
          })
        } else if (eventType === 'final_content') {
          const text = String(event.data.content ?? '')
          setTryEvents((prev) => [...prev.filter((e) => e.type !== 'streaming'), { type: 'final', data: { content: text } }])
        } else if (eventType === 'error') {
          setTryEvents((prev) => [...prev, { type: 'error', data: event.data }])
          toast.error(String(event.data.message ?? '试运行失败'))
        } else if (eventType === 'tool_start') {
          setTryEvents((prev) => [...prev, { type: 'tool', data: event.data }])
        } else if (eventType === 'approval_required') {
          toast.warning('此 Agent 含需审批工具，试运行可能被拦截。')
        }
      })
    } catch (caught) {
      toast.error(caught instanceof Error ? caught.message : '试运行失败')
    } finally { setTrying(false) }
  }
  const formatText = (value: string) => value.split(/\\\\r?\\\\n/).map((part, index) => index % 2 === 1 ? <span key={`nl-${index}`}><br /></span> : <span key={`t-${index}`}>{part}</span>);
  return <div className="data-stack agents-page">
    <section className="data-panel agents-layout">
      <aside className="agents-sidebar">
        <header><BrainCircuit /><span>已配置 Agent</span><b>{data.length}</b></header>
        <button className="button pink" onClick={() => { setDraft(newAgentTemplate()); setSelectedId(null) }}><Plus />新建 Agent</button>
        {data.length ? <ul className="agents-list">{data.map((agent) => <li key={agent.id} className={agent.id === selectedId ? 'active' : ''}><button type="button" className="agents-list-button" onClick={() => selectAgent(agent.id)}><strong>{agent.name || agent.id}</strong><small>{agent.provider_id} / {agent.model}</small><span className="row-meta">{agent.tool_ids.length} 个工具 · {agent.skill_ids.length} 个 Skill</span></button></li>)}</ul> : <EmptyInline text="还没有 Agent。点击「新建 Agent」开始。" />}
      </aside>
      {selected ? <section className="agents-detail">
        <header className="agents-detail-header">
          <div><BrainCircuit /><div><h2>{selected.name || selected.id}</h2><p>{selected.id}</p></div></div>
          <div className="agents-actions">
            <button className="icon-button danger-button" title="删除 Agent" aria-label={'删除 ' + selected.id} onClick={() => void remove(selected.id)}><Trash2 /></button>
          </div>
        </header>
        <div className="agents-form">
          <label>Agent ID<input value={selected.id} onChange={(event) => updateDraft({ id: event.target.value })} placeholder="agent-唯一标识" /></label>
          <label>名称<input value={selected.name} onChange={(event) => updateDraft({ name: event.target.value })} placeholder="给用户看的名字" /></label>
          <label>描述<textarea value={selected.description} onChange={(event) => updateDraft({ description: event.target.value })} placeholder="一句话说明这个 Agent 做什么" /></label>
          <label>系统提示词<textarea value={selected.system_prompt} rows={6} onChange={(event) => updateDraft({ system_prompt: event.target.value })} placeholder="完整 system prompt" /></label>
          <label>Provider<select value={selected.provider_id} onChange={(event) => updateDraft({ provider_id: event.target.value, model: providers.find((p) => p.id === event.target.value)?.models[0] ?? '' })}>{providers.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.id})</option>)}</select></label>
          <label>Model<select value={selected.model} onChange={(event) => updateDraft({ model: event.target.value })}>{(provider?.models ?? []).map((m) => <option key={m} value={m}>{m}</option>)}{(!(provider?.models ?? []).length) && <option value={selected.model}>{selected.model}</option>}</select></label>
          <label>温度 (0-2)<input type="number" min={0} max={2} step={0.1} value={selected.temperature} onChange={(event) => updateDraft({ temperature: Number(event.target.value) })} /></label>
          <label>最大输出 tokens (可选)<input type="number" min={1} value={selected.max_output_tokens ?? ''} onChange={(event) => updateDraft({ max_output_tokens: event.target.value === '' ? null : Number(event.target.value) })} /></label>
          <fieldset><legend>工具授权</legend>{allTools.map((tool) => <label key={tool.id} className="agents-tool-row"><input type="checkbox" checked={selected.tool_ids.includes(tool.id)} onChange={(event) => { const next = event.target.checked ? [...selected.tool_ids, tool.id] : selected.tool_ids.filter((id) => id !== tool.id); updateDraft({ tool_ids: next }) }} /><span><strong>{tool.label}</strong><small className={`risk-tag risk-${tool.risk}`}>{tool.risk === 'high' ? '⚠️ 高风险' : '低风险'}</small></span></label>)}</fieldset>
          <fieldset><legend>Skill</legend>{skillOptions.length ? skillOptions.map((skill) => <label key={skill.id} className="agents-tool-row"><input type="checkbox" checked={selected.skill_ids.includes(skill.id)} onChange={(event) => { const next = event.target.checked ? [...selected.skill_ids, skill.id] : selected.skill_ids.filter((id) => id !== skill.id); updateDraft({ skill_ids: next }) }} /><span><strong>{skill.name}</strong><small>{skill.id}</small></span></label>) : <p className="capability-note">还没有加载任何 Skill。</p>}</fieldset>
          <label>分类 (可选)<input value={selected.category ?? ''} onChange={(event) => updateDraft({ category: event.target.value === '' ? null : event.target.value })} placeholder="例如 写作 / 翻译" /></label>
          <div className="agents-switches"><Switch checked={selected.streaming} onCheckedChange={(checked) => updateDraft({ streaming: checked })} label="启用流式输出" /><Switch checked={selected.is_hidden} onCheckedChange={(checked) => updateDraft({ is_hidden: checked })} label="在列表中隐藏" /></div>
          <div className="agents-savebar"><button className="button pink" disabled={saving} onClick={() => void save()}><CheckCircle2 />{saving ? '保存中…' : '保存 Agent'}</button></div>
        </div>
        <section className="agents-try">
          <header><Play /><div><h2>试运行</h2><p>输入一段输入，让 Agent 真实跑一次（流式 SSE）。</p></div></header>
          <textarea value={tryInput} onChange={(event) => setTryInput(event.target.value)} placeholder="例如：帮我总结今天的科技新闻" rows={3} />
          <div className="agents-trybar"><button className="button blue" disabled={trying || !tryInput.trim()} onClick={() => void tryRun()}>{trying ? '运行中…' : '运行'}</button></div>
          <div className="agents-tryevents">{tryEvents.map((event, index) => {
            if (event.type === 'streaming' || event.type === 'final') return <article key={'s-' + index} className="agent-tryevent"><div className="agent-tryevent-label">{event.type === 'streaming' ? '流式输出' : '最终输出'}</div><pre>{formatText(String(event.data.content ?? ''))}</pre></article>
            if (event.type === 'tool') return <article key={'t-' + index} className="agent-tryevent tool"><div className="agent-tryevent-label">工具调用</div><pre>{formatText(JSON.stringify(event.data, null, 2))}</pre></article>
            if (event.type === 'error') return <article key={'e-' + index} className="agent-tryevent error"><div className="agent-tryevent-label">错误</div><pre>{formatText(String(event.data.message ?? JSON.stringify(event.data)))}</pre></article>
            return null
          })}{!tryEvents.length && !trying && <p className="capability-note">点击「运行」开始试运行。</p>}</div>
        </section>
      </section> : <section className="agents-empty"><BrainCircuit /><h2>选择或新建 Agent</h2><p>从左侧选择 Agent 进行编辑，或点击「新建 Agent」开始。</p></section>}
    </section>
  </div>
}

'''

# Find position BEFORE 'export {' (the export block starts here)
export_idx = content.find('export {')
new_content = content[:export_idx] + NEW_FUNC + content[export_idx:]

with open(path, 'w', encoding='utf-8') as f:
    f.write(new_content)
print(f'wrote new function. new size: {len(new_content)}')
