export default function PluginManagement() {
  const plugins = [
    {
      id: 'feishu_bot',
      name: '飞书机器人',
      type: 'publisher',
      builtin: true,
      desc: '将摘要推送到飞书群机器人',
      status: '需要配置',
      configured: '填写飞书机器人地址后可发送',
    },
    {
      id: 'wecom_bot',
      name: '企业微信机器人',
      type: 'publisher',
      builtin: true,
      desc: '将摘要推送到企业微信群机器人',
      status: '需要配置',
      configured: '填写企业微信机器人地址后可发送',
    },
    {
      id: 'rss',
      name: 'RSS 采集器',
      type: 'adapter',
      builtin: true,
      desc: '从 RSS 订阅源抓取内容',
      status: '可直接使用',
      configured: '运行时需要提供 RSS 地址',
    },
    {
      id: 'github_trending',
      name: 'GitHub Trending',
      type: 'adapter',
      builtin: true,
      desc: '抓取 GitHub 热门项目及其更新信息',
      status: '已加入系统',
      configured: '运行时还需选择语言和数量',
    },
    {
      id: 'ai_search',
      name: 'AI Search',
      type: 'adapter',
      builtin: true,
      desc: '通过配置的 AI 搜索服务补充内容来源',
      status: '需要配置',
      configured: '需要填写对应搜索服务的访问密钥',
    },
    {
      id: 'follow_opml',
      name: 'OPML 导入',
      type: 'adapter',
      builtin: true,
      desc: '从 OPML 文件或地址导入订阅源',
      status: '已加入系统',
      configured: '当前页面暂不支持导入',
    },
    {
      id: 'dingtalk',
      name: '钉钉群机器人',
      type: 'publisher',
      builtin: true,
      desc: '将摘要发布到钉钉自定义机器人',
      status: '已加入系统',
      configured: '运行时需要填写机器人连接地址',
    },
    {
      id: 'wechat',
      name: '微信公众号草稿',
      type: 'publisher',
      builtin: true,
      desc: '将摘要创建为微信公众号草稿',
      status: '已加入系统',
      configured: '运行时需要填写 App ID 和密钥',
    },
    {
      id: 'xiaohongshu',
      name: '小红书图文',
      type: 'publisher',
      builtin: true,
      desc: '将摘要发布为小红书图文笔记',
      status: '已加入系统',
      configured: '运行时需要填写 App Key 和密钥',
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
    storage: '数据存储',
    tool: '辅助工具',
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>扩展功能</h1>
          <p>查看系统可用的采集和发送能力。状态会说明该功能是否还需要填写连接信息。</p>
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
        这里仅展示当前已加入的功能，不能在此启用、停用或填写连接信息。请在系统设置或启动参数中完成配置。
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
                    className={'badge ' + (plugin.status === '可直接使用' ? 'live' : '')}
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
