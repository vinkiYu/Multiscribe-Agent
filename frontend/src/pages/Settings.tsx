import { useState } from 'react'

type SettingsTab = 'basic' | 'providers' | 'publishers'

export default function Settings() {
  const [tab, setTab] = useState<SettingsTab>('basic')

  return (
    <>
      <div className="page-head">
        <div>
          <h1>系统设置</h1>
          <p>此页说明环境配置并提供静态表单预览。凭据不会从浏览器写入服务器，请在 .env 中配置。</p>
        </div>
      </div>

      <div className="tabs" style={{ marginBottom: 16 }}>
        {([
          ['basic', '基础配置'],
          ['providers', 'AI 模型服务'],
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
      {tab === 'publishers' && <PublisherSettings />}

      <section style={{ marginTop: 16 }}>
        <article className="card">
          <div className="card-head"><span>采集源配置</span><span className="badge">静态表单</span></div>
          <div className="card-body">
            <p className="text-muted text-sm">参数展示用于部署核对。保存配置请编辑 .env 并重启服务。</p>
            <details>
              <summary>GitHub Trending</summary>
              <div className="grid cols-2" style={{ marginTop: 16 }}>
                <Field label="编程语言" placeholder="例如 python、typescript" />
                <Field label="最低 Stars" placeholder="例如 100" type="number" />
              </div>
            </details>
            <details style={{ marginTop: 12 }}>
              <summary>AI 搜索</summary>
              <div className="field" style={{ marginTop: 16 }}>
                <label htmlFor="ai-search-provider">AI 搜索提供商</label>
                <select id="ai-search-provider" defaultValue="">
                  <option value="">未配置</option><option value="perplexity">Perplexity</option><option value="phind">Phind</option>
                </select>
              </div>
            </details>
          </div>
        </article>
      </section>

      <section style={{ marginTop: 16 }}>
        <article className="card">
          <div className="card-head"><span>发布端配置</span><span className="badge">仅供参考</span></div>
          <div className="card-body">
            <p className="text-muted text-sm">敏感凭据不会在此页保存或回显。请将实际值保留在 .env。</p>
            <details><summary>微信公众号</summary><div className="grid cols-2" style={{ marginTop: 16 }}><Field label="App ID" placeholder="wx…" /><Field label="App Secret" placeholder="在 .env 中配置" type="password" /></div></details>
            <details style={{ marginTop: 12 }}><summary>小红书</summary><div style={{ marginTop: 16 }}><Field label="App Key" placeholder="在 .env 中配置" /></div></details>
            <details style={{ marginTop: 12 }}><summary>钉钉</summary><div style={{ marginTop: 16 }}><Field label="Webhook URL" placeholder="https://oapi.dingtalk.com/robot/send?access_token=…" /></div></details>
          </div>
        </article>
      </section>
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

function PublisherSettings() {
  return <SettingsTable title="发布渠道" rows={[
    ['飞书机器人', 'FEISHU_WEBHOOK', '飞书群自定义机器人 Webhook 地址'],
    ['企业微信机器人', 'WECOM_WEBHOOK', '企业微信群机器人 Webhook 地址'],
  ]} />
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
  const id = label.toLowerCase().replace(/ /g, '-')
  return <div className="field"><label htmlFor={id}>{label}</label><input id={id} className="input" type={type} placeholder={placeholder} /></div>
}
