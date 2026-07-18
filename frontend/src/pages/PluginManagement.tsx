export default function PluginManagement() {
  const plugins = [
    {
      id: 'feishu_bot',
      name: '飞书机器人',
      type: 'publisher',
      enabled: true,
      builtin: true,
      desc: '将摘要推送到飞书群机器人',
      configured: '见 .env 中的 FEISHU_WEBHOOK',
    },
    {
      id: 'wecom_bot',
      name: '企业微信机器人',
      type: 'publisher',
      enabled: false,
      builtin: true,
      desc: '将摘要推送到企业微信群机器人',
      configured: '尚未配置（WECOM_WEBHOOK）',
    },
    {
      id: 'rss',
      name: 'RSS 采集器',
      type: 'adapter',
      enabled: true,
      builtin: true,
      desc: '从 RSS 订阅源抓取内容',
      configured: '内置示例：BBC News',
    },
  ]

  const grouped = plugins.reduce<Record<string, typeof plugins>>((acc, p) => {
    if (!acc[p.type]) acc[p.type] = []
    acc[p.type].push(p)
    return acc
  }, {})

  const labels: Record<string, string> = {
    publisher: '发布渠道',
    adapter: '数据采集',
    storage: '存储插件',
    tool: '智能工具',
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>插件</h1>
          <p>查看系统已注册的插件及其配置状态。插件状态当前为只读，启用与停用能力即将开放。</p>
        </div>
      </div>

      <div
        className="text-muted text-sm"
        style={{
          padding: 12,
          borderRadius: 6,
          background: 'var(--color-subtle)',
          marginBottom: 16,
        }}
      >
        插件的启用、停用和配置将在后续版本提供可视化操作。当前请通过 <code>.env</code> 配置相关密钥。
      </div>

      {Object.entries(grouped).map(([type, items]) => (
        <section key={type} style={{ marginBottom: 24 }}>
          <h2
            style={{
              fontSize: 14,
              fontWeight: 750,
              marginBottom: 12,
              color: 'var(--color-muted)',
              textTransform: 'uppercase',
              fontFamily: 'var(--font-mono)',
              letterSpacing: '0.05em',
            }}
          >
            {labels[type] ?? type}
          </h2>
          <div className="grid cols-3">
            {items.map(plugin => (
              <article key={plugin.id} className="card">
                <div className="card-head">
                  <span>
                    {plugin.name}
                    {plugin.builtin && (
                      <span className="badge" style={{ marginLeft: 8 }}>内置</span>
                    )}
                  </span>
                  <span
                    className={'badge ' + (plugin.enabled ? 'live' : '')}
                    aria-label={plugin.enabled ? '已启用' : '已停用'}
                  >
                    {plugin.enabled ? '已启用' : '已停用'}
                  </span>
                </div>
                <div className="card-body">
                  <p className="text-sm" style={{ marginTop: 0 }}>
                    {plugin.desc}
                  </p>
                  <div className="text-mono text-xs" style={{ color: 'var(--color-muted)' }}>
                    ID：{plugin.id}
                  </div>
                  <div className="text-xs" style={{ color: 'var(--color-muted)', marginTop: 4 }}>
                    {plugin.configured}
                  </div>
                </div>
              </article>
            ))}
          </div>
        </section>
      ))}
    </>
  )
}
