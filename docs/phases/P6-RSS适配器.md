# P6 — RSS 适配器（首个真实采集插件）

> **状态**：未开始 · **依赖**：P1, P2, P5

## 目标

实现 RSS 适配器：抓取真实 RSS feed → 转换为 UnifiedData → 经仓储入库。这是 MVP 的数据入口，验证「采集→入库」链路打通。

## 前置依赖

P1（UnifiedData/SourceData），P2（SourceDataRepository），P5（BaseAdapter/Registry/discovery）。

## 可改范围（白名单）

- `src/multiscribe_agent/plugins/builtin/adapters/rss.py`（RSSAdapter）
- `src/multiscribe_agent/plugins/builtin/adapters/__init__.py`（如需导出）
- `src/multiscribe_agent/services/__init__.py`
- `src/multiscribe_agent/services/ingestion.py`（IngestionService：协调 adapter + repository，run_single/run_all）
- `pyproject.toml`（追加：`feedparser>=6.0`，`httpx>=0.27`）
- `tests/plugins/test_rss_adapter.py`
- `tests/services/test_ingestion.py`
- `tests/fixtures/`（放 1-2 个本地 RSS XML 样本文件供测试）

## 禁止改动（黑名单）

- 不动 plugins/base.py/registry.py/discovery.py（P5 已定）。
- 不实现其他适配器（Follow/GitHub/AI 搜索 → P14）。
- 不创建发布器（P7/P8）。
- 测试默认不打真实网络（用本地 XML fixture + respx mock httpx）。

## 详细任务

### T1. `plugins/builtin/adapters/rss.py` — RSSAdapter

```python
class RSSAdapter(BaseAdapter):
    metadata = PluginMetadata(
        id="rss", type=PluginType.ADAPTER, name="RSS 订阅源",
        description="抓取标准 RSS/Atom feed",
        icon="rss_feed",
        config_fields=[
            ConfigField(key="rss_url", label="Feed URL", type="url", required=True, scope="item"),
            ConfigField(key="source_name", label="来源名", type="text", required=False, scope="item"),
            ConfigField(key="category", label="分类", type="text", required=False, scope="item"),
        ],
    )
    async def fetch(self, config) -> str:  # 返回 raw XML/解析后结构
    def transform(self, raw, config=None) -> list[UnifiedData]:
```

- `fetch`：用 `httpx.AsyncClient`（支持代理）GET feed URL，超时 30s，返回 raw 文本（或 feedparser 解析结果）。
- `transform`：用 `feedparser` 解析，每条 entry → UnifiedData：
  - `id` = entry.guid / link / id（取首个非空）。
  - `title`, `url`(link), `description`(summary/first 300 chars), `published_date`(published_parsed → ISO), `source`(feed.title 或 config.source_name), `category`(config.category 或 feed.title), `author`。
  - `metadata` 含 tags。
- `fetch_and_transform`（基类已实现，错误返回 `[]`）。

### T2. `services/ingestion.py` — IngestionService

```python
class IngestionService:
    def __init__(self, adapter_registry, source_data_repo, task_log_repo): ...
    async def run_single(self, adapter_id: str, config: dict, task_log_id: str | None = None) -> int:
        """跑单适配器：fetch_and_transform → save_batch → 记 task_log，返回写入数。"""
    async def run_all(self, adapter_configs: list[dict], task_log_id=None) -> dict[str,int]:
        """跑全部已配置适配器，逐个跑（错误不中断），返回 {adapter_id: count}。"""
```

- 错误容错：单 adapter 失败记 task_log status=error，继续其他。
- task_log：create（running）→ 完成时 update（success/error + result_count + end_time + duration）。

### T3. 测试

- `tests/fixtures/hackernews.xml`、`tests/fixtures/sample_feed.xml`：本地小 RSS 文件（可用真实 HN feed 的精简版，注意版权）。
- `tests/plugins/test_rss_adapter.py`：
  - `fetch`（respx mock httpx 返回 fixture XML）成功。
  - `transform` 正确映射字段（id/title/url/published_date/source）。
  - `fetch_and_transform` 端到端产出 UnifiedData 列表。
  - 网络错误返回 `[]` 不抛。
  - 标记真实抓取为 `@pytest.mark.e2e`。
- `tests/services/test_ingestion.py`：
  - `run_single`（fake adapter + in-memory repo）写入 source_data，task_log 正确。
  - `run_all` 一个 adapter 失败不影响其他。
  - save_batch 去重（同 id 二次写入不增）。

## 验收条件

1. RSSAdapter 抓取真实格式 feed（用 fixture）→ 正确转 UnifiedData（字段齐全，published_date 规范化）。
2. 网络失败容错（返回空，不崩）。
3. IngestionService run_single/run_all 工作，task_log 记录完整，去重生效。
4. RSSAdapter 被 discovery 自动注册（出现在 AdapterRegistry.list_metadata）。
5. 全测试绿，默认零真实网络。

## 测试方式

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src
uv run pytest tests/plugins/test_rss_adapter.py tests/services/test_ingestion.py -q
```
可选 e2e（手动）：
```bash
uv run pytest tests/plugins/test_rss_adapter.py -q -m e2e
```
原始输出贴 review。

## 完成定义

验收全满足；RSS→入库链路有测试证据。后续 P11 流水线的「抓取」节点复用本 IngestionService。
