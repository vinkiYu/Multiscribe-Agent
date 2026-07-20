# Review: P28-数据层与插件生态

**执行包**：`docs/phases/P28-数据层与插件生态.md`  
**完成日期**：2026-07-20  
**执行者**：Codex

## 1. 范围核对

### 1.1 实际改动文件

| 文件 | 操作 | 说明 |
| --- | --- | --- |
| `src/multiscribe_agent/infra/db.py` | 修改 | 连接池路由、FTS tokenization、审计兼容 |
| `src/multiscribe_agent/infra/connection_pool.py` | 新增 | 多读连接 + 单写连接 |
| `src/multiscribe_agent/infra/text_tokenize.py` | 新增 | jieba 可选分词与降级 |
| `src/multiscribe_agent/knowledge/document_processor.py` | 修改 | KB FTS 写入前分词 |
| `src/multiscribe_agent/memory/repositories/memory_entries.py` | 修改 | Memory FTS 写入/查询分词 |
| `src/multiscribe_agent/plugins/base.py` | 修改 | 重导出并使用版本常量 |
| `src/multiscribe_agent/plugins/registry.py` | 修改 | API 版本兼容性检查 |
| `src/multiscribe_agent/plugins/sandbox.py` | 新增 | subprocess JSON 协议沙箱 |
| `src/multiscribe_agent/bootstrap.py` | 修改 | 连接池初始化接线 |
| `src/multiscribe_agent/domain/models.py` | 修改 | `PluginMetadata.api_version`、`min_system_version` |
| `pyproject.toml` | 修改 | pytest-cov、pytest-benchmark、text(jieba) 可选依赖 |
| `tests/infra/*`、`tests/plugins/*`、`tests/perf/*` | 新增 | 定向、沙箱和三项性能基准测试 |

### 1.2 白名单偏差说明

任务包将 `PluginMetadata` 写在 `plugins/base.py`，但仓库真实定义位于 `domain/models.py`；因此修改 `domain/models.py` 是完成版本字段所必需的最小范围扩展。任务包列出的 `memory/repositories/__init__.py` 未承载 FTS 写入逻辑，实际修改了同目录的 `memory_entries.py`。两处偏差均未改变 API 路由或业务层边界，已在本 Review 显式记录。

## 2. 验收条件逐条对照

| # | 验收条件 | 状态 | 证据 |
| --- | --- | --- | --- |
| 1 | N 个读连接 + 1 个写连接，WAL 并发读取 | PASS | `infra/connection_pool.py:23-103`；`tests/infra/test_connection_pool.py:9-47` |
| 2 | 写操作串行化，避免 locked | PASS | `connection_pool.py:104-124` 的单 writer lock/timeout；同一连接池定向测试 |
| 3 | 中文 FTS 写入前 jieba 分词并保持降级 | PASS | `text_tokenize.py:11-34`、`db.py:285-323`；`tests/infra/test_fts_chinese.py:22-49` |
| 4 | `PluginMetadata.api_version` 与兼容检查 | PASS | `domain/models.py:321-337`、`plugins/registry.py:23-29`；`tests/plugins/test_plugin_version_check.py:32-47` |
| 5 | subprocess 沙箱执行 JSON 插件 | PASS | `plugins/sandbox.py:26-67`；`tests/plugins/test_plugin_sandbox.py:12-43` |
| 6 | pytest-cov 输出并达到首期覆盖率门槛 | PASS | 覆盖率命令输出 `TOTAL 6559 787 88%`，高于 P28 完成定义的 75% |
| 7 | 三个热路径 benchmark | PASS | `tests/perf/test_context_trim_benchmark.py`、`test_dag_sort_benchmark.py`、`test_rrf_retrieval_benchmark.py`；见第 3.3 节 |
| 8 | 全量 pytest、ruff、mypy 通过 | PASS | 见第 3 节 |

## 3. 测试与质量门

### 3.1 全量 pytest

```text
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .pytest-tmp-rerun
325 passed, 4 deselected, 1 warning in 32.98s
```

### 3.2 覆盖率

```text
.venv\Scripts\python.exe -m pytest -q --cov=multiscribe_agent --cov-report=term-missing --cov-fail-under=75 -p no:cacheprovider --basetemp .pytest-tmp-coverage
TOTAL 6559 787 88%
```

覆盖率门槛为 75%，本次聚合结果为 88%。个别边界模块（例如沙箱失败分支）低于 80%，作为后续测试补全风险保留，不掩盖聚合结果。

### 3.3 性能基准

```text
.venv\Scripts\python.exe -m pytest tests\perf --benchmark-only -q -p no:cacheprovider --basetemp .pytest-tmp-bench
3 passed in 3.35s
```

本次三项均执行：context trim 100 messages、DAG topological sort 50 nodes、RRF fusion 100 candidates。

### 3.4 静态质量门

```text
.venv\Scripts\python.exe -m ruff check .
All checks passed!

.venv\Scripts\python.exe -m ruff format --check .
265 files already formatted

.venv\Scripts\python.exe -m mypy src
Success: no issues found in 146 source files

git diff --check
通过（exit code 0）
```

## 4. 详细任务完成情况

- **T1 连接池**：读 lane 使用 semaphore + N 个 `query_only` 连接，写 lane 使用单一 `asyncio.Lock`；所有连接启用 WAL、busy timeout 和外键约束；`Database` 自动路由读写。
- **T2 中文 FTS**：jieba 延迟导入，缺包时回退到 SQLite Unicode tokenizer；KB/Memory 的索引写入和 MATCH 查询使用同一 tokenization 规则。
- **T3 插件版本**：metadata 默认 `api_version=1.0`、`min_system_version=0.1.0`；Adapter/Publisher/Storage/Tool 注册入口统一拒绝不兼容 API 版本。
- **T4 沙箱**：子进程通过 stdin/stdout JSON 协议执行，捕获启动失败、超时、非零退出和非法 JSON；默认由调用方选择是否使用。
- **T5 覆盖率**：`pytest-cov` 已加入 dev optional dependency，并验证总覆盖率 88%。
- **T6 性能回归**：三个 benchmark fixture 可独立使用 `--benchmark-only` 执行，不阻塞普通测试。

## 5. 规范符合性自检

- [x] 新增/修改源码通过 `mypy --strict` 和 ruff。
- [x] 读写连接边界清晰，审计递归使用当前 writer connection，避免池内死锁。
- [x] jieba 为可选能力，缺包部署仍可启动并使用基础 FTS。
- [x] 沙箱不默认替换内置插件路径，避免给普通调用引入不可控性能开销。
- [x] 新增行为有定向测试、全量回归和性能证据。

## 6. 新增依赖

| 依赖 | 位置 | 用途 |
| --- | --- | --- |
| `pytest-cov>=4.1` | `[project.optional-dependencies].dev` | 覆盖率报告与门禁 |
| `pytest-benchmark>=4.0` | `[project.optional-dependencies].dev` | 性能回归基准 |
| `jieba>=0.42` | `[project.optional-dependencies].text` | 中文 FTS 分词 |

当前环境已安装并验证这些依赖。环境没有 `uv`，所以 `uv.lock` 未更新，这是可复现安装链路的遗留风险。

## 7. 风险、遗留与取舍

- `PluginMetadata.min_system_version` 已进入领域模型，但本包只按 `api_version` 做注册兼容检查；系统版本比较策略需要后续定义清楚后再启用。
- `SandboxConfig.memory_limit_mb` 当前作为配置契约保留，Windows/跨平台安全限制尚未真正施加 OS-level memory quota；当前验收只要求 subprocess 隔离和错误处理。
- 聚合覆盖率达标，但 `plugins/sandbox.py` 等新模块仍有异常分支未覆盖，建议下一阶段增加超时、坏 JSON、非零退出和 spawn 失败测试。
- jieba 分词会改变 FTS 查询 token 形态；已有 fallback 保证无 jieba 时可用，但线上升级时应重建旧索引以获得一致召回。
- pytest 有一个既有 Starlette/httpx deprecation warning，不影响本阶段门禁。

## 8. BLOCKED

无。`uv.lock` 未更新仅是当前环境缺少 uv 的可复现性风险，不阻塞代码验证。

## 9. 对后续包的提示

- 安装/发布流程应同步 `text` optional extra，并在 lockfile 可用时刷新 `uv.lock`。
- 建议把插件系统版本比较（`min_system_version`）和沙箱资源限制拆成独立验收项，避免把声明字段误当成已执行的 OS 隔离。

## 10. 自评

本包六项 P1 改造均已实现；定向测试、全量回归、覆盖率和三项 benchmark 均有证据，静态质量门全绿。**判定：PASS（按 P28 首期聚合覆盖率门槛），建议带上述风险进入后续阶段。**
