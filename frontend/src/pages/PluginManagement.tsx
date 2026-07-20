export default function PluginManagement() {
  const plugins = [
    {
      id: 'feishu_bot',
      name: '飞书机器人',
      type: 'publisher',
      builtin: true,
      desc: '将摘要推送到飞书群机器人',
      status: '需配置',
      configured: '配置 FEISHU_WEBHOOK 后可用',
    },
    {
      id: 'wecom_bot',
      name: '企业微信机器人',
      type: 'publisher',
      builtin: true,
      desc: '将摘要推送到企业微信群机器人',
      status: '需配置',
      configured: '配置 WECOM_WEBHOOK 后可用',
    },
    {
      id: 'rss',
      name: 'RSS 采集器',
      type: 'adapter',
      builtin: true,
      desc: '从 RSS 订阅源抓取内容',
      status: '内置可用',
      configured: '运行时传入 RSS 地址',
    },
    {
      id: 'github_trending',
      name: 'GitHub Trending',
      type: 'adapter',
      builtin: true,
      desc: '抓取 GitHub 热门项目及其更新信息',
      status: '已注册',
      configured: '运行时传入语言和数量参数',
    },
    {
      id: 'ai_search',
      name: 'AI Search',
      type: 'adapter',
      builtin: true,
      desc: '通过配置的 AI 搜索服务补充内容来源',
      status: '需配置',
      configured: '需要对应搜索服务凭据',
    },
    {
      id: 'follow_opml',
      name: 'OPML 导入',
      type: 'adapter',
      builtin: true,
      desc: '从 OPML 文件或地址导入订阅源',
      status: '已注册',
      configured: '当前前端未提供导入入口',
    },
    {
      id: 'dingtalk',
      name: '钉钉群机器人',
      type: 'publisher',
      builtin: true,
      desc: '将摘要发布到钉钉自定义机器人',
      status: '已注册',
      configured: '需在运行参数中提供 Webhook',
    },
    {
      id: 'wechat',
      name: '微信公众号草稿',
      type: 'publisher',
      builtin: true,
      desc: '将摘要创建为微信公众号草稿',
      status: '已注册',
      configured: '需在运行参数中提供 App ID 和密钥',
    },
    {
      id: 'xiaohongshu',
      name: '小红书图文',
      type: 'publisher',
      builtin: true,
      desc: '将摘要发布为小红书图文笔记',
      status: '已注册',
      configured: '需在运行参数中提供 App Key 和密钥',
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
          <p>查看系统已注册的采集器和发布渠道。这里展示的是能力注册状态，不代表外部凭据已经配置。</p>
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
        插件的启用、停用和配置当前仍由服务端和运行参数控制；页面暂不提供修改入口。
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
                    className={'badge ' + (plugin.status === '内置可用' ? 'live' : '')}
                    aria-label={plugin.status}
                  >
                    {plugin.status}
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
