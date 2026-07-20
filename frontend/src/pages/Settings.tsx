import { useState } from 'react'

type SettingsTab = 'basic' | 'providers' | 'publishers' | 'sources'

export default function Settings() {
  const [tab, setTab] = useState<SettingsTab>('basic')

  return (
    <>
      <div className="page-head">
        <div>
          <h1>系统设置</h1>
          <p>此页展示环境配置项和填写示例。页面不会保存修改，请在服务端 .env 中配置后重启服务。</p>
        </div>
      </div>

      <div className="tabs" style={{ marginBottom: 16 }}>
        {([
          ['basic', '基础配置'],
          ['providers', 'AI 模型服务'],
          ['sources', '采集源'],
          ['publishers', '发布渠道'],
        ] as const).map(([value, label]) => (
          <button
            className={`tab ${tab === value ? 'active' : ''}`}
            key={value}
            onClick={() => setTab(value)}
            type="button"
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'basic' && <BasicSettings />}
      {tab === 'providers' && <ProviderSettings />}
      {tab === 'sources' && <SourceSettings />}
      {tab === 'publishers' && <PublisherSettings />}
    </>
  )
}

function BasicSettings() {
  const rows = [
    ['DB_PATH', '数据库文件路径', 'data/database.sqlite'],
    ['LOG_LEVEL', '日志级别', 'INFO'],
    ['PORT', 'API 服务端口', '8000'],
    ['SYSTEM_PASSWORD', '登录访问密码', 'admin123（请务必修改）'],
  ]
  return <SettingsTable title="基础配置" rows={rows} />
}

function ProviderSettings() {
  return <SettingsTable title="AI 模型服务" rows={[
    ['OpenAI', 'OPENAI_API_KEY', '支持 OPENAI_API_BASE_URL 中转端点'],
    ['Anthropic', 'ANTHROPIC_API_KEY', '配置后可在 Agent 中选择'],
    ['Google', 'GOOGLE_API_KEY', '可选'],
    ['Ollama（本地）', '无需 key', '需要本机运行 Ollama 服务'],
  ]} />
}

function SourceSettings() {
  return (
    <article className="card">
      <div className="card-head"><span>采集源配置</span></div>
      <div className="card-body">
        <p className="text-muted text-sm" style={{ marginBottom: 16 }}>
          以下参数写入 .env 后重启服务生效。实际配置请编辑项目根目录下的 <code>.env</code> 文件。
        </p>

        <details style={{ marginBottom: 16 }}>
          <summary style={{ cursor: 'pointer', fontWeight: 600 }}>GitHub Trending</summary>
          <div className="grid cols-2" style={{ marginTop: 12, gap: 12 }}>
            <Field label="GITHUB_LANGUAGE" placeholder="例如 python、typescript（留空为全部）" />
            <Field label="GITHUB_STARS_MIN" placeholder="例如 100" type="number" />
            <Field label="GITHUB_MAX_ITEMS" placeholder="每次最多抓取数量" type="number" />
          </div>
        </details>

        <details style={{ marginBottom: 16 }}>
          <summary style={{ cursor: 'pointer', fontWeight: 600 }}>AI 搜索</summary>
          <div className="grid cols-2" style={{ marginTop: 12, gap: 12 }}>
            <Field label="AI_SEARCH_PROVIDER" placeholder="perplexity / phind / custom" />
            <Field label="PERPLEXITY_API_KEY" placeholder="API Key（留空则不启用）" type="password" />
            <Field label="PHIND_API_KEY" placeholder="API Key（留空则不启用）" type="password" />
            <Field label="AI_SEARCH_CUSTOM_ENDPOINT" placeholder="https://api.example.com/v1/chat" />
          </div>
        </details>

        <details>
          <summary style={{ cursor: 'pointer', fontWeight: 600 }}>RSS 订阅源</summary>
          <div className="card-body" style={{ marginTop: 8 }}>
            <p className="text-muted text-sm" style={{ marginBottom: 12 }}>
              RSS 源通过 <code>data/sources.yaml</code> 配置，支持 title / url / category / update_interval 字段。
            </p>
            <Field label="SOURCES_FILE" placeholder="data/sources.yaml" />
          </div>
        </details>
      </div>
    </article>
  )
}

function PublisherSettings() {
  return (
    <>
      <article className="card" style={{ marginBottom: 16 }}>
        <div className="card-head"><span>发布端配置</span></div>
        <div className="card-body">
          <p className="text-muted text-sm" style={{ marginBottom: 16 }}>
            敏感凭据不会在此页保存或回显。请将实际值保留在 .env。
          </p>

          <details style={{ marginBottom: 16 }}>
            <summary style={{ cursor: 'pointer', fontWeight: 600 }}>微信公众号</summary>
            <div className="grid cols-2" style={{ marginTop: 12, gap: 12 }}>
              <Field label="WECHAT_APP_ID" placeholder="wx…" />
              <Field label="WECHAT_APP_SECRET" placeholder="App Secret（请在 .env 中配置）" type="password" />
            </div>
          </details>

          <details style={{ marginBottom: 16 }}>
            <summary style={{ cursor: 'pointer', fontWeight: 600 }}>小红书</summary>
            <div style={{ marginTop: 12 }}>
              <Field label="XIAOHONGSHU_APP_KEY" placeholder="开放平台 App Key" />
            </div>
          </details>

          <details>
            <summary style={{ cursor: 'pointer', fontWeight: 600 }}>钉钉群机器人</summary>
            <div style={{ marginTop: 12 }}>
              <Field
                label="DINGTALK_WEBHOOK"
                placeholder="https://oapi.dingtalk.com/robot/send?access_token=…"
              />
              <Field label="DINGTALK_SECRET" placeholder="加签密钥（可选）" type="password" />
            </div>
          </details>
        </div>
      </article>

      <article className="card">
        <div className="card-head"><span>飞书 / 企业微信</span></div>
        <div className="card-body">
          <details>
            <summary style={{ cursor: 'pointer', fontWeight: 600 }}>飞书群机器人</summary>
            <div style={{ marginTop: 12 }}>
              <Field label="FEISHU_WEBHOOK" placeholder="飞书自定义机器人 Webhook 地址" />
            </div>
          </details>
          <details style={{ marginTop: 12 }}>
            <summary style={{ cursor: 'pointer', fontWeight: 600 }}>企业微信机器人</summary>
            <div style={{ marginTop: 12 }}>
              <Field label="WECOM_WEBHOOK" placeholder="企业微信群机器人 Webhook 地址" />
            </div>
          </details>
        </div>
      </article>
    </>
  )
}

function SettingsTable({ title, rows }: { title: string; rows: string[][] }) {
  return (
    <article className="card">
      <div className="card-head"><span>{title}</span></div>
      <div className="table-wrap"><table><thead><tr><th>项目</th><th>环境变量</th><th>说明</th></tr></thead><tbody>
        {rows.map(([name, environment, note]) => <tr key={name}><td><strong>{name}</strong></td><td className="text-mono">{environment}</td><td className="text-muted">{note}</td></tr>)}
      </tbody></table></div>
    </article>
  )
}

function Field({ label, placeholder, type = 'text' }: { label: string; placeholder: string; type?: string }) {
  return (
    <div className="field">
      <span className="text-sm text-muted">{label}</span>
      <code className="config-value" data-kind={type}>{placeholder}</code>
    </div>
  )
}
