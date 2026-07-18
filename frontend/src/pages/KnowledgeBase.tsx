export default function KnowledgeBase() {
  return (
    <>
      <div className="page-head">
        <div>
          <h1>知识库</h1>
          <p>知识库与 Agent 记忆能力即将开放，当前不可用。</p>
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
        知识库用于存储文档供 Agent 检索；Agent 记忆用于跨任务保留上下文。两项能力正在开发中，敬请期待。
      </div>

      <div className="grid cols-2">
        <article className="card">
          <div className="card-head">
            <span>文档知识</span>
            <span className="badge">即将开放</span>
          </div>
          <div className="card-body">
            <div className="empty" style={{ minHeight: 120 }}>
              <strong>暂未开放</strong>
              <p>支持上传 PDF、Word、Markdown 等文档供 Agent 检索。</p>
            </div>
          </div>
        </article>

        <article className="card">
          <div className="card-head">
            <span>Agent 记忆</span>
            <span className="badge">即将开放</span>
          </div>
          <div className="card-body">
            <div className="empty" style={{ minHeight: 120 }}>
              <strong>暂未开放</strong>
              <p>记录 Agent 跨任务的上下文与偏好，供后续运行复用。</p>
            </div>
          </div>
        </article>
      </div>
    </>
  )
}
