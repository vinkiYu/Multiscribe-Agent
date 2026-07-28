# Review: `P36-采集并发化`

**执行包**：`docs/phases/P36-采集并发化.md`
**完成日期**：2026-07-29
**执行者**：Codex

## 1. 范围核对

### 1.1 实际改动文件清单

| 文件路径 | 操作 | 用途 |
| :--- | :--- | :--- |
| `src/multiscribe_agent/services/ingestion.py` | 修改 | 将跨适配器 `run_all` 改为 Semaphore 限制的异步并发执行，并保留配置预处理与异常隔离。 |
| `tests/services/test_ingestion.py` | 修改 | 增加并发耗时、故障隔离、并发峰值和禁用配置测试。 |
| `codex/reviews/P36-REVIEW.md` | 新增 | 本阶段验收证据与风险报告。 |

### 1.2 白名单合规性

- [x] 业务代码和测试只修改 P36 白名单文件。
- [x] 未修改 agents、dashboard、插件适配器、infra、scheduler、publisher、config、bootstrap、API、LLM 或 frontend 黑名单文件。
- [x] 工作区中已有的 frontend、`daily_digest.py`、压缩包、临时测试目录和 `.idea` 目录均未纳入本阶段提交。

## 2. 验收条件逐条对照

| # | 验收条件 | 状态 | 证据 |
| :--- | :--- | :--- | :--- |
| 1 | 4 个适配器各 sleep 0.5 秒并发执行，总耗时小于 1 秒 | ✅ | `test_run_all_runs_four_slow_adapters_concurrently_by_default`：四个 runtime adapter 的并发峰值为 4，耗时断言 `< 1.0`。 |
| 2 | 一个适配器抛异常，其他适配器仍返回结果 | ✅ | `test_run_all_isolates_one_concurrent_adapter_failure`：结果为 `{"failure": 0, "success": 1}`，任务日志同时有 error/success。 |
| 3 | `max_concurrency=2` 时并发峰值不超过 2 | ✅ | `test_run_all_respects_max_concurrency_semaphore`：4 个适配器执行后 `tracker["peak"] <= 2`。 |
| 4 | 不传 `max_concurrency` 默认使用 4 | ✅ | 默认并发测试不传该参数，并断言四个适配器同时运行。 |
| 5 | `enabled=False` 的适配器不执行 | ✅ | `test_run_all_skips_disabled_adapter_before_scheduling`：结果只含 enabled 项，调用计数为 1。 |
| 6 | 返回结果包含已执行适配器的 count，key 为 adapter_id | ✅ | 默认并发和并发度限制测试均断言 4 个 adapter_id 到 count=1 的完整映射。 |
| 7 | 全量 pytest、ruff、mypy 通过 | ⚠️ | 白名单 Ruff、格式检查、`mypy src` 和带仓库内 `--basetemp` 的全量 pytest 通过；无范围 Ruff 受既有临时插件文件和用户改动污染，详见第 3 节。 |

## 3. 测试与质量门

### 3.1 定向测试

```text
============================== 7 passed in 0.98s ==============================
```

命令：

```text
.\.venv\Scripts\python.exe -m pytest tests/services/test_ingestion.py -v -p no:cacheprovider --basetemp .pytest-tmp-p36
```

### 3.2 全量 pytest

```text
446 passed, 4 deselected, 1 warning in 40.82s
```

命令：

```text
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .pytest-tmp-p36-full
```

警告为现有 Starlette `TestClient` 与 httpx 的弃用提示。

### 3.3 P36 白名单 Ruff

```text
All checks passed!
```

命令：

```text
.\.venv\Scripts\python.exe -m ruff check src/multiscribe_agent/services/ingestion.py tests/services/test_ingestion.py
```

### 3.4 P36 格式检查

```text
2 files already formatted
```

命令：

```text
.\.venv\Scripts\python.exe -m ruff format --check src/multiscribe_agent/services/ingestion.py tests/services/test_ingestion.py
```

### 3.5 `mypy src`

```text
Success: no issues found in 161 source files
```

### 3.6 无范围 Ruff 的污染证据

```text
Found 48 errors.
26 files would be reformatted, 315 files already formatted
```

错误集中在 `.pytest-tmp-p35-full/`、`.pytest-tmp-p36-full/`、`.tmp-pytest/` 生成的临时插件，以及用户已有的 `src/multiscribe_agent/agents/pipelines/daily_digest.py` 和 `src/multiscribe_agent/api/routes/settings.py`。这些路径不属于 P36 白名单，未擅自清理或格式化。

## 4. 详细任务完成情况

- **T1：有限并发 `run_all`**：`IngestionService.run_all` 在并发前过滤 disabled 配置、解析 adapter_id、校验 Mapping 配置；有效任务通过 `asyncio.Semaphore(max(1, max_concurrency))` 包住 `run_single`，默认并发度为 4。见 `src/multiscribe_agent/services/ingestion.py:91-140`。
- **故障隔离**：使用 `asyncio.gather(..., return_exceptions=True)` 聚合；正常异常继续由 `run_single` 转成 count=0 和 error task log，gather 层只对未预期的 BaseException 记录 warning，不影响其他任务结果。
- **向后兼容**：现有调用方仍只传 `adapter_configs` 或 `task_log_id`，不传新参数即可获得默认值 4；`run_single`、适配器内部并发和仓储写锁均未改动。
- **测试**：新增受控延迟适配器和 tracker，覆盖并发速度、异常、Semaphore 峰值、默认值和 enabled 过滤。

## 5. 规范符合性自检

- [x] 新增代码有类型注解和 docstring。
- [x] 外部 I/O 仍通过既有异步 adapter/repository 边界执行，没有新增阻塞调用。
- [x] 并发使用 `asyncio.gather` 与 `asyncio.Semaphore`，未引入线程或新的运行时依赖。
- [x] 日志只记录异常类型和配置上下文，不记录密钥、响应正文或用户隐私。
- [x] 测试使用内存仓储和本地 sleep，不访问真实网络、LLM 或 webhook。

## 6. 新增依赖

无。`asyncio` 为 Python 标准库，未修改 `pyproject.toml` 或 `uv.lock`。

## 7. 风险、遗留与取舍

- **风险**：如果未来调用方传入同一个非空 `task_log_id` 给多个并发适配器，多个任务会竞争更新同一日志；当前已核实的日报和 dashboard 调用均不传该参数，P36 未扩大范围改调用方。
- **风险**：默认并发度 4 可能让 Follow/AI Search 等 LLM 型适配器同时触发 provider 限流；任务包明确采用固定上限，不在本阶段引入 provider 分类限流或配置项。
- **取舍**：结果仍在所有任务结束后返回 dict，没有使用 `as_completed` 暴露流式进度，保持既有 `run_all` 契约。
- **遗留**：无范围 Ruff 仍会扫描历史临时文件和用户已有未格式化改动；白名单静态门已通过。
- **未做的事**：未修改适配器内部并发、超时、数据库连接池、task log 结构、调用方或调度器。

## 8. BLOCKED 项

无。任务包契约完整，代码和测试均可在白名单内完成。

## 9. 对后续包的提示

- 后续如需运营调节并发度，可在配置层新增字段，再由调用方显式传 `max_concurrency`；本阶段默认值 4 已保持兼容。
- 后续若要实时展示适配器完成进度，可在不改变当前最终 dict 契约的前提下增加事件/回调层，不应直接改变 `run_all` 返回类型。

## 10. 自评

- 我认为本包满足 `P36-采集并发化.md` 的完成定义：✅
- 白名单实现、定向测试、全量回归、白名单 Ruff、格式检查和 mypy 均通过；仓库级 Ruff 的失败仅来自既有工作区污染，已如实记录。
