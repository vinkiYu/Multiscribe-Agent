# 执行包：P53-C — 数据源 FTS 搜索

> **阶段**：新功能（数据层 FTS 接入）
> **目标**：把已有的 `SourceDataRepository.search_fts()` 暴露给前端：新建 HTTP 路由 + 前端「数据源搜索」页面，复用现成的 FTS5 / jieba / tsvector 索引。
> **依赖**：无。
> **预估**：0.5 个工作日。

---

## 一、为什么需要这个包

`SourceDataRepository.search_fts()` 已完整实现（SQLite FTS5 + Postgres tsvector + jieba 中文分词 + highlight snippet），但**从未被任何 HTTP 路由调用**。

后果：
- 数据源采集的所有内容（每日几百~几千条）无法被运营按关键词搜索
- 调试 / 排查问题时无法快速定位「某条内容是否被成功采集」
- 跟 `KnowledgePage` / `MemoryPage` 已有搜索 UI 相比，唯独数据源缺一个入口

P53-C 关闭这个空白：1 个新路由 + 1 个新页面 + 1 个 sidebar 入口 + 1 段 CSS。

---

## 二、现状基线（已核实）

| 项 | 位置 | 现状 |
|---|---|---|
| FTS 索引 | `infra/db.py:765-822` | SQLite FTS5 + Postgres tsvector 双路径全就位 |
| jieba 分词 | `infra/text_tokenize.py:22-29` | 全文 tokenize 自动应用 |
| `_normalize_fts_parameters` | `infra/db.py:333-345` | 自动 tokenize FTS query 参数 |
| `SourceDataRepository.search_fts()` | `infra/repositories/source_data.py:191-200` | Repository 方法就绪 |
| HTTP 路由 `/api/source-data/search` | — | **不存在** |
| 前端 sidebar | `App.tsx:25-31` | 无「数据搜索」入口 |
| 现有 `KnowledgePage` 搜索 UI | `shared/ui.tsx:216` | 已有 Search icon + input + button 模式 |

---

## 三、任务拆解（2 个子任务）

### T1：P53-C.1 — 后端路由

#### `src/multiscribe_agent/api/routes/source_data.py`（新建）

```python
"""Authenticated routes for source_data FTS search."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from multiscribe_agent.api.dependencies import ServiceContext, get_context

router = APIRouter(prefix="/source-data", tags=["source-data"])


@router.get("/search")
async def search_source_data(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(default=20, ge=1, le=100),
    context: ServiceContext = Depends(get_context),
) -> list[dict[str, object]]:
    """Return FTS search results over source_data with highlighted snippets."""
    if not q.strip():
        raise HTTPException(status_code=400, detail="query cannot be empty")
    if context.source_data_repo is None:
        raise HTTPException(status_code=503, detail="source_data unavailable")
    try:
        rows = await context.source_data_repo.search_fts(q, limit=limit)
    except Exception:
        # FTS5 invalid syntax etc — treat as no results
        return []
    return [_source_data_to_dict(row) for rows in rows] if False else [_source_data_to_dict(row) for row in rows]


def _source_data_to_dict(row) -> dict[str, object]:
    return {
        "id": row.id,
        "title": row.title,
        "url": row.url,
        "description": row.description,        # already contains <mark>...</mark> highlight
        "source": row.source,
        "category": row.category,
        "published_date": row.published_date,
        "ingestion_date": row.ingestion_date,
        "adapter_name": row.adapter_name,
    }
```

#### `src/multiscribe_agent/api/__init__.py`

```python
# 现有 imports 末尾追加
from multiscribe_agent.api.routes.source_data import router as source_data_router
# 现有 include_router 末尾追加
router.include_router(source_data_router)
```

### T2：P53-C.2 — 前端页面

#### `frontend/src/services/api.ts`

```typescript
export interface SourceData {
  id: string
  title: string
  url: string
  description: string         // contains <mark>...</mark> highlight
  source: string
  category: string
  published_date: string
  ingestion_date: string
  adapter_name: string
}

export const sourceDataApi = {
  search(q: string, limit = 20): Promise<SourceData[]> {
    return request<SourceData[]>('/source-data/search', { params: { q, limit } })
  },
}
```

#### `frontend/src/pages/source-search.tsx`（新建）

复制 `KnowledgePage` 的 `<Search /> + <input /> + 按钮` 模式：

```tsx
import { useCallback, useEffect, useState, type ReactElement } from 'react'
import { Search, Files } from 'lucide-react'
import { ApiError, sourceDataApi, type SourceData } from '../services/api'

export function SourceSearchPage(): ReactElement {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SourceData[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSearch = useCallback(async () => {
    if (!query.trim()) return
    setLoading(true)
    setError(null)
    try {
      const rows = await sourceDataApi.search(query, 20)
      setResults(rows)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : '搜索失败')
    } finally {
      setLoading(false)
    }
  }, [query])

  return (
    <div className="data-stack">
      <section className="data-panel">
        <div className="data-summary">
          <Search /><span>数据源搜索</span>
        </div>
        <div className="search-bar">
          <input
            placeholder="输入关键词搜索数据源（支持 FTS5 语法 AND/OR/NOT）"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') void handleSearch() }}
          />
          <button type="button" className="button compact" onClick={handleSearch}>
            搜索
          </button>
        </div>
      </section>

      {error && <p className="empty-inline">{error}</p>}

      {results !== null && (
        <section className="data-panel">
          <div className="data-summary">
            <Files /><span>找到 {results.length} 条结果</span>
          </div>
          {results.length === 0 ? (
            <p className="empty-inline">未找到匹配结果</p>
          ) : (
            <div className="data-list">
              {results.map((item) => (
                <article className="data-row" key={item.id}>
                  <div>
                    <a className="content-link" href={item.url} target="_blank" rel="noreferrer">
                      <strong>{item.title}</strong>
                    </a>
                    {/* dangerouslySetInnerHTML: highlight <mark> tags from backend */}
                    <p dangerouslySetInnerHTML={{ __html: item.description }} />
                    <div className="tag-list">
                      <span className="tag">{item.source}</span>
                      <span className="tag">{item.adapter_name}</span>
                    </div>
                  </div>
                  <span className="row-meta">{item.published_date}</span>
                </article>
              ))}
            </div>
          )}
        </section>
      )}
    </div>
  )
}
```

#### `frontend/src/styles.css`

```css
/* === Source search === */
.search-bar {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 2px solid var(--line);
}
.search-bar input {
  flex: 1;
  padding: 8px 12px;
  border: 2px solid var(--ink);
  border-radius: 5px;
  font-size: 14px;
  font-weight: 600;
  background: var(--paper);
  color: var(--ink);
}
.search-bar input:focus {
  outline: 3px solid var(--sun);
  outline-offset: 0;
}
```

#### `frontend/src/App.tsx`

```tsx
// 顶部 import 加 Search 图标
import { Search } from 'lucide-react'  // 已存在；确认存在

// NavKey 加 'source-search'
export type NavKey = ... | 'source-search'

// workbenchItems 加新项
{ key: 'source-search', label: '数据搜索', icon: Search },

// copy Record 加
source-search: { title: '数据源搜索', description: '全文搜索数据源采集内容' },

// main 区加
{active === 'source-search' && <SourceSearchPage key={refreshVersion} />}
```

---

## 四、白名单与黑名单

### 白名单（可改/新增，共 7 个）

```
src/multiscribe_agent/api/routes/source_data.py           [T1, 新建]
src/multiscribe_agent/api/__init__.py                    [T1, 注册路由]
frontend/src/services/api.ts                              [T2, SourceData 类型 + sourceDataApi]
frontend/src/pages/source-search.tsx                     [T2, 新建]
frontend/src/styles.css                                   [T2, .search-bar 样式]
frontend/src/App.tsx                                     [T2, NavKey + workbenchItems + copy + 渲染]
docs/phases/P53-C-数据源FTS搜索.md                     [本任务包]
```

### 黑名单（禁止改动）

- `infra/repositories/source_data.py`（不动 search_fts 已有实现）
- `infra/text_tokenize.py`（不动）
- `infra/db.py`（不动 schema）
- `infra/postgres/schema_fts.py`（不动）
- `knowledge/fts_query.py`（不动）
- `frontend/src/shared/ui.tsx`（不动）
- `frontend/src/pages/content.tsx`（不动）
- `frontend/src/pages/knowledge.tsx` / `memory.tsx`（不动）
- 后端其他模块

---

## 五、验收条件

| # | 验收 | 证据 |
|---|---|---|
| 1 | `GET /api/source-data/search?q=AI&limit=20` 返回 `SourceData[]` | curl + 响应 |
| 2 | FTS highlight 在 `description` 字段返回（含 `<mark>` 标签）| 响应内容 |
| 3 | 空 query 返回 400 | curl 验证 |
| 4 | FTS5 非法语法抛异常被捕获 → 返回空列表 | try/except |
| 5 | `sourceDataApi.search(q, limit)` 类型正确 | `tsc -b` |
| 6 | App.tsx `NavKey` 含 `source-search` | 文件内容 |
| 7 | 侧边栏显示「数据搜索」入口 | 页面加载 |
| 8 | 搜索结果渲染（无数据时「未找到」）+ highlight 视觉可见 | 视觉 |
| 9 | `npm run build` 通过 | 构建输出 |
| 10 | 全量 pytest + ruff + mypy 通过 | 输出 |

---

## 六、测试与质量门

```bash
# 路由定向测试
.venv\Scripts\python.exe -m pytest tests/api/test_source_data_search.py -v -p no:cacheprovider

# 全量回归
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .pytest-tmp-p53c

# 静态门
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .
.venv\Scripts\python.exe -m mypy src

# 前端
cd frontend
npm run build
npm run lint
```

视觉验收（手动）：
- 左侧 sidebar 出现「数据搜索」入口
- 进入页面 → 输入「AI」按回车或点搜索 → 看到带 `<mark>` 高亮的结果列表
- 无匹配时显示「未找到匹配结果」空态
- 输入 FTS5 非法语法（如只有 `*`）→ 不报 500，返回空结果

---

## 七、完成定义

- [ ] 白名单 7 个文件全部创建/修改
- [ ] 10 条验收条件全部通过
- [ ] 数据源搜索可端到端跑通
- [ ] 全量 pytest 无回归
- [ ] `codex/reviews/P53-C-REVIEW.md` 填写完毕

---

## 八、风险与取舍

1. **FTS5 非法语法**：用户可能输入 `*` 或 `AND OR` 等无效语法，导致 FTS5 `MATCH` 抛异常。路由用 `try/except Exception` 兜底，返回 `[]` 而非 500。Codex 可加 1 个单元测试验证兜底行为。
2. **highlight 用 `dangerouslySetInnerHTML`**：后端返回的 `<mark>` 来自 SQLite FTS5 `snippet()` / Postgres `ts_headline()`，是受控字符串（来自原始 description）。XSS 风险来自原始 description，而 description 已存数据库时可视为可信。
3. **未分词时退化为 Unicode**：jieba 未装时退化为 Unicode tokenization，搜索质量下降但不阻断。
4. **CJK + FTS5 MATCH**：jieba 通过 `_normalize_fts_parameters` 在执行前自动注入，与 index 一致。无需额外配置。
5. **未做内容搜索侧栏**：当前只搜 `source_data`，不搜 `daily_digest_archives.items`（无 FTS 索引）。如未来要扩展，加独立端点即可。
6. **不加搜索历史 / 自动补全**：MVP 范围。后续可加。
7. **`describe "source-search"`**：依赖任务包执行时确认 `Search` 图标已在 App.tsx 导入。如果未导入，Codex 在 `App.tsx` 顶部 import 加一行。

---

## 九、文件清单

```
src/multiscribe_agent/api/routes/source_data.py            [新增: T1 路由]
src/multiscribe_agent/api/__init__.py                     [修改: T1 include_router]
frontend/src/services/api.ts                              [修改: T2 类型+API]
frontend/src/pages/source-search.tsx                      [新增: T2 页面]
frontend/src/styles.css                                   [修改: T2 .search-bar]
frontend/src/App.tsx                                      [修改: T2 NavKey+入口]
docs/phases/P53-C-数据源FTS搜索.md                       [新增: 本任务包]
```