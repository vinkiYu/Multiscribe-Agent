# Review: P23-OTel

**执行包**：`docs/phases/P23-OTel.md`  
**完成日期**：2026-07-19  
**执行者**：Codex

## 1. 范围核对

| 文件路径 | 操作 | 用途 |
| :--- | :--- | :--- |
| `src/multiscribe_agent/observability/__init__.py` | 新增 | 导出 observability API |
| `src/multiscribe_agent/observability/optional.py` | 新增 | OTel/Prometheus 缺包探测 |
| `src/multiscribe_agent/observability/tracer.py` | 新增 | OTel tracer + no-op fallback |
| `src/multiscribe_agent/observability/meter.py` | 新增 | Counter/Histogram + Prometheus 文本 fallback |
| `src/multiscribe_agent/api/routes/metrics.py` | 新增 | `/metrics` endpoint |
| `src/multiscribe_agent/core/logging.py` | 修改 | structlog 注入当前 OTel trace_id |
| `src/multiscribe_agent/bootstrap.py` | 修改 | 启动 metrics/tracer |
| `src/multiscribe_agent/app.py` | 修改 | 挂载 metrics route，新增 `/healthz` |
| `src/multiscribe_agent/agents/executor.py` | 修改 | LLM/tool span 与指标记录 |
| `src/multiscribe_agent/services/publishing.py` | 修改 | publish success/failure/latency 指标 |
| `pyproject.toml` | 修改 | 新增 `observability` optional extra |
| `tests/observability/*` | 新增 | 降级、tracer、meter、endpoint 测试 |

白名单合规：上述文件均在 P23 白名单内。未修改 P23 黑名单中的业务 routes/reflector/workflow HTTP 入口。

## 2. 验收对照

| # | 验收条件 | 状态 | 证据 |
| :--- | :--- | :--- | :--- |
| 1 | `/metrics` 返回 200 + text/plain | 通过 | `tests/observability/test_metrics_endpoint.py` |
| 2 | 指标前缀 `multiscribe_`，含 token/latency/publish | 通过 | `tests/observability/test_meter.py` |
| 3 | OTel tracer 启动后 console/OTLP exporter | 部分通过 | `setup_tracer()` 已实现；当前环境未安装 OTel，走 no-op 降级 |
| 4 | 缺包降级仍能启动 | 通过 | `tests/observability/test_optional_degradation.py`、全量 pytest |
| 5 | structlog 日志中含 trace_id | 部分通过 | `core/logging.py` 注入 OTel trace_id；HTTP `X-Trace-Id` header 已测 |
| 6 | Agent executor / publisher 埋点 | 通过 | `agents/executor.py`、`services/publishing.py` |
| 7 | 全量 pytest + ruff + mypy | 部分通过 | pytest/mypy/ruff check 通过；全量 format 见第 3 节 |

## 3. 测试与质量门

```text
.venv\Scripts\python.exe -m pytest tests/observability -q -p no:cacheprovider --basetemp .pytest-tmp-p23
14 passed, 1 warning in 1.04s
```

```text
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .pytest-tmp-full2
288 passed, 4 deselected, 1 warning in 31.78s
```

```text
.venv\Scripts\python.exe -m ruff check .
warning: Encountered error: 拒绝访问。 (os error 5)
All checks passed!
```

```text
.venv\Scripts\python.exe -m ruff format --check .
error: Encountered error: 拒绝访问。 (os error 5)
Would reformat: src\multiscribe_agent\agents\pipelines\daily_digest.py
1 file would be reformatted, 235 files already formatted
```

```text
.venv\Scripts\python.exe -m ruff format --check <stage4 files>
47 files already formatted
```

```text
.venv\Scripts\python.exe -m mypy src
Success: no issues found in 135 source files
```

```text
.venv\Scripts\python.exe -m pip install -e ".[observability]"
F:\software\Multiscribe\MultiscribeAgent-main\.venv\Scripts\python.exe: No module named pip

uv --version
uv : 无法将“uv”项识别为 cmdlet...
```

## 4. 任务完成情况

- T1：`optional.detect()` 对缺失父模块做安全降级。
- T2：`MetricsRegistry` 记录 publish success/failure、LLM calls/tokens、tool calls、latency。
- T3：`setup_tracer()` 支持 OTel SDK、OTLP endpoint、console exporter 和 no-op fallback。
- T4-T6：`/metrics`、`/healthz`、structlog trace_id processor、bootstrap 初始化完成。
- T7-T8：executor/publisher 埋点完成，`pyproject.toml` 增加 observability optional extra。

## 5. 新增依赖

| 包 | 版本约束 | 用途 |
| :--- | :--- | :--- |
| `opentelemetry-api` | `>=1.27` | Tracing/Metrics API |
| `opentelemetry-sdk` | `>=1.27` | SDK provider/exporter |
| `opentelemetry-exporter-otlp` | `>=1.27` | OTLP exporter |
| `opentelemetry-instrumentation-fastapi` | `>=0.48b0` | 后续 FastAPI instrumentation |
| `prometheus-client` | `>=0.20` | Prometheus backend |

## 6. 风险与遗留

- 当前 `.venv` 无 pip，`uv` 也不可用，所以 optional extra 安装验证未完成。
- 因未安装 OTel，console exporter 仅代码路径可达，未产生真实 exporter 输出。
- `uv.lock` 未更新，原因同上：本地无 uv 且无 pip。

## 7. 自评

P23 代码、降级路径、指标端点和测试满足主要完成定义；安装验证因环境工具缺失标记为未完成。
