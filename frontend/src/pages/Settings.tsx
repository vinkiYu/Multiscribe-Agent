import { useState } from 'react'

export default function Settings() {
  const [tab, setTab] = useState<'basic' | 'providers' | 'publishers'>('basic')

  return (
    <>
      <div className="page-head">
        <div>
          <h1>配置说明</h1>
          <p>
            以下是 Multiscribe 的关键配置项说明。修改请编辑部署目录下的 <code>.env</code> 文件，保存后重启服务生效。
          </p>
        </div>
      </div>

      <div className="tabs" style={{ marginBottom: 16 }}>
        <button
          className={'tab ' + (tab === 'basic' ? 'active' : '')}
          onClick={() => setTab('basic')}
          type="button"
        >
          基础配置
        </button>
        <button
          className={'tab ' + (tab === 'providers' ? 'active' : '')}
          onClick={() => setTab('providers')}
          type="button"
        >
          AI 模型服务
        </button>
        <button
          className={'tab ' + (tab === 'publishers' ? 'active' : '')}
          onClick={() => setTab('publishers')}
          type="button"
        >
          发布渠道
        </button>
      </div>

      {tab === 'basic' && (
        <article className="card">
          <div className="card-head"><span>基础配置</span></div>
          <div className="card-body">
            <table>
              <tbody>
                {[
                  { key: 'DB_PATH', label: '数据库文件路径', default: 'data/database.sqlite' },
                  { key: 'LOG_LEVEL', label: '日志级别', default: 'INFO' },
                  { key: 'PORT', label: 'API 服务端口', default: '8000' },
                  { key: 'SYSTEM_PASSWORD', label: '登录访问密码', default: 'admin123（请务必修改）' },
                ].map(row => (
                  <tr key={row.key}>
                    <td style={{ width: 200, fontFamily: 'var(--font-mono)', fontSize: 12 }}>
                      {row.key}
                    </td>
                    <td style={{ color: 'var(--color-muted)' }}>{row.label}</td>
                    <td className="text-mono text-muted" style={{ fontSize: 12 }}>
                      默认：{row.default}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      )}

      {tab === 'providers' && (
        <article className="card">
          <div className="card-head"><span>AI 模型服务</span></div>
          <div className="card-body">
            <table>
              <thead>
                <tr>
                  <th>服务</th>
                  <th>环境变量</th>
                  <th>说明</th>
                </tr>
              </thead>
              <tbody>
                {[
                  { id: 'default-openai', name: 'OpenAI', env: 'OPENAI_API_KEY', note: '也支持兼容中转端点（OPENAI_API_BASE_URL）' },
                  { id: 'default-anthropic', name: 'Anthropic', env: 'ANTHROPIC_API_KEY', note: '可选，配置后即可在 Agent 中选择' },
                  { id: 'default-google', name: 'Google', env: 'GOOGLE_API_KEY', note: '可选' },
                  { id: 'default-ollama', name: 'Ollama（本地）', env: '（无需 key）', note: '需本机运行 Ollama 服务' },
                ].map(p => (
                  <tr key={p.id}>
                    <td><strong>{p.name}</strong></td>
                    <td className="text-mono">{p.env}</td>
                    <td className="text-muted">{p.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="text-muted text-sm" style={{ marginTop: 16 }}>
              状态以实际 <code>.env</code> 配置为准。是否可用取决于密钥有效性和网络连通性。
            </p>
          </div>
        </article>
      )}

      {tab === 'publishers' && (
        <article className="card">
          <div className="card-head"><span>发布渠道</span></div>
          <div className="card-body">
            <table>
              <thead>
                <tr><th>渠道</th><th>环境变量</th><th>说明</th></tr>
              </thead>
              <tbody>
                {[
                  { name: '飞书机器人', env: 'FEISHU_WEBHOOK', note: '飞书群自定义机器人 Webhook 地址' },
                  { name: '企业微信机器人', env: 'WECOM_WEBHOOK', note: '企业微信群机器人 Webhook 地址' },
                ].map(pub => (
                  <tr key={pub.env}>
                    <td><strong>{pub.name}</strong></td>
                    <td className="text-mono">{pub.env}</td>
                    <td className="text-muted">{pub.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="text-muted text-sm" style={{ marginTop: 16 }}>
              渠道密钥仅配置在 <code>.env</code> 中，界面不展示具体值。是否已配置以文件内容为准。
            </p>
          </div>
        </article>
      )}
    </>
  )
}
