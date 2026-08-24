import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent, type ReactElement } from 'react'
import { BrainCircuit, CircleAlert, ListChecks, Plus, Search, Send, Sparkles, Trash2 } from 'lucide-react'
import { SectionHeading } from '../components/SectionHeading'
import { DataStatus } from '../components/DataStatus'
import { chatApi, type JsonRecord } from '../services/api'
import { useRemoteData } from '../hooks/useRemoteData'

interface ChatSession {
  id: string
  title: string
  updatedAt: string
  pinned: boolean
  unread: boolean
}

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  status: 'pending' | 'done' | 'error'
  skills?: string[]
  createdAt: string
}

const skillOptions = ['curate-daily-news', 'feishu-publisher', 'summarize-zh', 'memory-extract']

interface BackendSessionShape {
  id: string
  title: string
  created_at: number
  updated_at: number
  message_count: number
}

interface BackendMessageShape {
  id: string
  session_id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  created_at: number
}

function formatSessionTime(value: number | null | undefined): string {
  if (!value) return '刚刚'
  const ms = value < 1e12 ? value * 1000 : value
  const date = new Date(ms)
  if (Number.isNaN(date.getTime())) return '刚刚'
  const diff = Math.max(0, Date.now() - date.getTime())
  const minutes = Math.round(diff / 60_000)
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  if (minutes < 1440) return `${Math.round(minutes / 60)} 小时前`
  return `${Math.round(minutes / 1440)} 天前`
}

function formatMessageTime(value: number | null | undefined): string {
  if (!value) return '刚刚'
  const ms = value < 1e12 ? value * 1000 : value
  const date = new Date(ms)
  if (Number.isNaN(date.getTime())) return '刚刚'
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  status: 'pending' | 'done' | 'error'
  skills?: string[]
  createdAt: string
}

interface BackendSessionShape {
  id: string
  title: string
  created_at: number
  updated_at: number
  message_count: number
}

interface BackendMessageShape {
  id: string
  session_id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  created_at: number
}

function hydrateSession(row: JsonRecord): ChatSession {
  const data = row as unknown as BackendSessionShape
  return {
    id: data.id,
    title: data.title || '新会话',
    updatedAt: formatSessionTime(data.updated_at),
    pinned: false,
    unread: data.message_count === 0,
  }
}

function hydrateMessage(row: JsonRecord): ChatMessage {
  const data = row as unknown as BackendMessageShape
  return {
    id: data.id,
    role: data.role === 'user' ? 'user' : 'assistant',
    content: data.content,
    status: 'done',
    createdAt: formatMessageTime(data.created_at),
  }
}

export function ChatPage({ onFlash }: { onFlash: (message: string) => void }): ReactElement {
  const sessionsRemote = useRemoteData<JsonRecord[]>(() => chatApi.listSessions(50), {
    onError: (error) => onFlash(`加载会话失败：${error.message}`),
  })
  const sessions = useMemo<ChatSession[]>(() => (sessionsRemote.data ?? []).map(hydrateSession), [sessionsRemote.data])
  const [activeId, setActiveId] = useState<string>('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [draft, setDraft] = useState('')
  const [pendingSkills, setPendingSkills] = useState<string[]>(['curate-daily-news'])
  const [pending, setPending] = useState(false)
  const scrollRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!activeId && sessions.length > 0) setActiveId(sessions[0].id)
  }, [activeId, sessions])

  useEffect(() => {
    if (!activeId) {
      setMessages([])
      return
    }
    let cancelled = false
    void (async () => {
      try {
      const result = await chatApi.listMessages(activeId, 200)
      if (cancelled) return
      setMessages(result.map((row) => hydrateMessage(row)))
    } catch (caught) {
        onFlash(caught instanceof Error ? caught.message : '加载消息失败')
      }
    })()
    return () => { cancelled = true }
  }, [activeId, onFlash])

  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, activeId])

  const activeSession = sessions.find((s) => s.id === activeId) ?? null

  const toggleSkill = (skill: string): void => {
    setPendingSkills((current) => current.includes(skill) ? current.filter((s) => s !== skill) : [...current, skill])
  }

  const send = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    if (!activeId) return
    const content = draft.trim()
    if (!content || pending) return
    setPending(true)
    const userMsg: ChatMessage = { id: `local-${Date.now()}`, role: 'user', content, status: 'done', createdAt: '刚刚' }
    setMessages((current) => [...current, userMsg])
    setDraft('')
    try {
      const reply = await chatApi.sendMessage(activeId, content) as JsonRecord
      setMessages((current) => [...current, hydrateMessage(reply)])
      onFlash('AI 已回复当前会话。')
    } catch (caught) {
      onFlash(caught instanceof Error ? caught.message : '回复失败')
    } finally {
      setPending(false)
    }
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>): void => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      const form = event.currentTarget.form
      if (form) form.requestSubmit()
    }
  }

  const newSession = async (): Promise<void> => {
    try {
      const created = await chatApi.createSession('新会话') as JsonRecord
      onFlash('已创建新会话。')
      await sessionsRemote.reload()
      setActiveId(String((created as unknown as { id: string }).id))
    } catch (caught) {
      onFlash(caught instanceof Error ? caught.message : '创建会话失败')
    }
  }

  const deleteSession = async (id: string): Promise<void> => {
    try {
      await chatApi.deleteSession(id)
      onFlash('已删除会话。')
      if (activeId === id) setActiveId('')
      await sessionsRemote.reload()
    } catch (caught) {
      onFlash(caught instanceof Error ? caught.message : '删除失败')
    }
  }

  return (
    <>
      <SectionHeading
        icon={<Sparkles />}
        title="对话"
        description="对接 /api/chat/sessions 和 /api/chat/sessions/{id}/messages。"
        actions={
          <button className="btn btn-primary" type="button" onClick={() => void newSession()}>
            <Plus /> 新建会话
          </button>
        }
      />

      <DataStatus
        loading={sessionsRemote.loading && sessions.length === 0}
        error={sessionsRemote.error?.message ?? null}
        empty={!sessionsRemote.loading && sessions.length === 0}
        emptyTitle="暂无会话"
        emptyDescription="点击「新建会话」发起一段对话。"
        onRetry={() => void sessionsRemote.reload()}
      >
        <section className="section">
          <div className="chat-layout">
            <aside className="chat-sidebar" aria-label="会话列表">
              <div className="chat-sidebar-header">
                <strong>所有会话</strong>
                <span>{sessions.length}</span>
              </div>
              <div className="chat-sidebar-search">
                <Search />
                <input type="search" placeholder="搜索会话" aria-label="搜索会话" />
              </div>
              <ul className="chat-session-list">
                {sessions.map((session) => {
                  const isActive = session.id === activeId
                  return (
                    <li key={session.id}>
                      <button
                        type="button"
                        className={isActive ? 'chat-session-item is-active' : 'chat-session-item'}
                        onClick={() => setActiveId(session.id)}
                      >
                        <span className="chat-session-main">
                          <strong>{session.title}</strong>
                          <small>共 {session.title} 条</small>
                        </span>
                        <span className="chat-session-meta">
                          <span>{session.updatedAt}</span>
                          <button
                            className="btn btn-sm btn-ghost"
                            type="button"
                            onClick={(event) => { event.stopPropagation(); void deleteSession(session.id) }}
                          >
                            <Trash2 />
                          </button>
                        </span>
                      </button>
                    </li>
                  )
                })}
              </ul>
            </aside>

            <article className="chat-thread" aria-label="当前会话">
              <header className="chat-thread-header">
                <div>
                  <h2>{activeSession?.title ?? '选择左侧会话'}</h2>
                  <p>消息会通过 POST /api/chat/sessions/{'{id}'}/messages 提交给 Agent。</p>
                </div>
                <div className="chat-thread-actions">
                  <button className="btn btn-sm" type="button" onClick={() => onFlash('清空操作请用 DELETE /api/chat/sessions/{id}')}>
                    <Trash2 /> 清空
                  </button>
                </div>
              </header>

              <div className="chat-thread-scroll" ref={scrollRef}>
                {messages.length === 0 ? (
                  <div className="chat-empty">
                    <Sparkles />
                    <h3>开始新会话</h3>
                    <p>提出一个问题，让 Agent 帮你完成检索、摘要或工作流草稿。</p>
                  </div>
                ) : (
                  <ul className="chat-message-list">
                    {messages.map((message) => <MessageBubble key={message.id} message={message} />)}
                    {pending && <PendingBubble />}
                  </ul>
                )}
              </div>

              <form className="chat-composer" onSubmit={(event) => void send(event)}>
                <div className="chat-composer-skills">
                  <span className="chat-composer-label">
                    <BrainCircuit /> 本轮启用：
                  </span>
                  {skillOptions.map((skill) => {
                    const enabled = pendingSkills.includes(skill)
                    return (
                      <button
                        key={skill}
                        type="button"
                        className={enabled ? 'skill-chip is-active' : 'skill-chip'}
                        onClick={() => toggleSkill(skill)}
                      >
                        {skill}
                      </button>
                    )
                  })}
                </div>
                <div className="chat-composer-input">
                  <textarea
                    value={draft}
                    placeholder="输入消息，回车发送，Shift+回车换行"
                    onChange={(event) => setDraft(event.target.value)}
                    onKeyDown={handleKeyDown}
                    rows={2}
                    disabled={pending}
                  />
                  <button type="submit" className="btn btn-primary" disabled={pending || !draft.trim() || !activeId}>
                    <Send /> {pending ? '生成中…' : '发送'}
                  </button>
                </div>
              </form>
            </article>

            <aside className="chat-context" aria-label="上下文">
              <div className="chat-context-card context-info">
                <header><ListChecks /><span>当前会话</span></header>
                <p>
                  {activeSession
                    ? <>会话 ID：<code>{activeSession.id}</code></>
                    : '请选择左侧会话'}
                </p>
                <small>每轮回复后系统会通过 <code>/api/memory/extract</code> 抽取偏好。</small>
              </div>
              <div className="chat-context-card context-warn">
                <header><CircleAlert /><span>提示</span></header>
                <p>聊天接口要求管理员权限（<code>is_admin_user</code>），未配置时会返回 403。</p>
              </div>
            </aside>
          </div>
        </section>
      </DataStatus>
    </>
  )
}

function PendingBubble(): ReactElement {
  return (
    <li className="chat-message chat-message-assistant">
      <article className="chat-bubble chat-bubble-pending">
        <header><strong>AI</strong><small>生成中…</small></header>
        <p>正在整理上下文并调用工具…</p>
      </article>
    </li>
  )
}

function MessageBubble({ message }: { message: ChatMessage }): ReactElement {
  return (
    <li className={`chat-message chat-message-${message.role}`}>
      <article className="chat-bubble">
        <header>
          <strong>{message.role === 'user' ? '你' : 'AI'}</strong>
          <small>{message.createdAt}</small>
        </header>
        <p>{message.content}</p>
        {message.skills && message.skills.length > 0 && (
          <div className="chat-bubble-skills">
            {message.skills.map((skill) => <span key={skill} className="pill pill-neutral">{skill}</span>)}
          </div>
        )}
      </article>
    </li>
  )
}