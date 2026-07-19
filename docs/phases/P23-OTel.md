# 执行包：P23 — 全链路 OTel 可观测性

> **阶段**：阶段四（与 P22 / P24 同期开发）
> **目标**：补齐 OTel Tracer + Meter + Prometheus `/metrics` 端点；trace_id 注入 structlog。
> **依赖**：P12（API 骨架）、P11（pipeline 已存在，添加 span hook）。
> **并行说明**：与 P22、P24 独立可开发；不影响 P21 评估运行。

---

## 一、目标与验收口径

**核心目标**：
- **Tracer**：OTel SDK 自动 + 手动混合；Agent run / round / tool 全 span。
- **Meter**：token 计数 / latency 分布 / 工具调用次数 / 推送成功率。
- **Prometheus 端点**：`GET /metrics` 返回标准 text 格式。
- **日志关联**：trace_id 自动注入 structlog contextvars。

**验收口径**：
- `pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp prometheus-client opentelemetry-instrumentation-fastapi` 安装成功。
- 启动后 `GET /metrics` 返回 200，text/plain，包含 `multiscribe_*` 前缀指标。
- 启动后 `GET /healthz` 返回 200；调用 `POST /api/digest/run` 触发 digest，span 在 console exporter 输出。
- structlog 日志中含 `trace_id` 字段。

---

## 二、验收条件

| # | 验收 | 证据 |
|---|---|---|
| 1 | `GET /metrics` 返回 200 + text/plain | curl |
| 2 | 指标前缀 `multiscribe_`，含 token / latency / publish 三类 | `/metrics` 输出 |
| 3 | OTel Tracer 启动后 console 输出 span（Agent run → round → tool） | 启动日志 |
| 4 | `OTEL_EXPORTER_OTLP_ENDPOINT` 配置后，trace 导出到 OTLP collector | 环境变量切换 |
| 5 | structlog 日志含 `trace_id` 字段 | 启动 + digest run 日志 |
| 6 | OTel 包为**可选依赖**：缺包时降级到 metrics-only 模式（不抛错） | 缺包启动 OK |
| 7 | 全量 pytest + ruff + mypy 通过 | `pytest -q` |

---

## 三、可改范围（白名单）

| 文件路径 | 操作 |
|---|---|
| `src/multiscribe_agent/observability/__init__.py` | **新增**（导出 public API） |
| `src/multiscribe_agent/observability/tracer.py` | **新增**（OTel Tracer 启动 + span helper） |
| `src/multiscribe_agent/observability/meter.py` | **新增**（指标注册 + Counter/Histogram） |
| `src/multiscribe_agent/observability/optional.py` | **新增**（探测 OTel/prom 可用性 + 降级开关） |
| `src/multiscribe_agent/api/routes/metrics.py` | **新增**（`/metrics` 端点） |
| `src/multiscribe_agent/core/logging.py` | **修改**（追加 `trace_id_filter`，仅在启用 OTel 时激活） |
| `src/multiscribe_agent/bootstrap.py` | **修改**（启动时初始化 tracer + meter） |
| `src/multiscribe_agent/app.py` | **修改**（注册 `/metrics` 路由；FastAPI middleware 注入 trace_id） |
| `src/multiscribe_agent/agents/executor.py` | **修改**（关键节点 start_span，token 计数到 meter） |
| `src/multiscribe_agent/services/publishing.py` | **修改**（publish success/failure 计数器） |
| `pyproject.toml` | **修改**（追加 OTel 可选 extra） |
| `tests/observability/__init__.py` | **新增** |
| `tests/observability/test_tracer.py` | **新增** |
| `tests/observability/test_meter.py` | **新增** |
| `tests/observability/test_metrics_endpoint.py` | **新增** |
| `tests/observability/test_optional_degradation.py` | **新增** |

---

## 四、禁止改动（黑名单）

- `src/multiscribe_agent/agents/reflector.py`、`src/multiscribe_agent/agents/workflows.py`（O24 才动）
- `src/multiscribe_agent/api/routes/agents.py`、`digest.py`（业务路由，不直接挂钩 OTel）
- `frontend/`、`docs/`、`codex/`（除本任务包外的所有文档）

---

## 五、详细任务

### T1：optional.py（缺包降级探测）

```python
# src/multiscribe_agent/observability/optional.py
"""Detect optional observability dependencies and provide degradation flags."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ObservabilityCapabilities:
    tracer: bool
    meter: bool
    prometheus_endpoint: bool


def detect() -> ObservabilityCapabilities:
    """Probe the runtime for OTel and prometheus-client availability."""
    try:
        import opentelemetry.trace  # noqa: F401
        tracer = True
    except ImportError:
        tracer = False

    try:
        import opentelemetry.metrics  # noqa: F401
        meter = True
    except ImportError:
        meter = False

    try:
        import prometheus_client  # noqa: F401
        prom = True
    except ImportError:
        prom = False

    return ObservabilityCapabilities(
        tracer=tracer,
        meter=meter,
        prometheus_endpoint=prom,
    )
```

### T2：meter.py（指标定义）

```python
# src/multiscribe_agent/observability/meter.py
"""Centralized metric registration using opentelemetry.metrics or prometheus_client."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class MetricsRegistry:
    """Hold metric handles; safe to call record() regardless of backend."""

    capabilities: Any  # ObservabilityCapabilities from optional.detect()
    _counters: dict[str, Any]
    _histograms: dict[str, Any]

    @classmethod
    def create(cls, capabilities: Any) -> "MetricsRegistry":
        return cls(
            capabilities=capabilities,
            _counters={
                "publish_success": _build_counter(capabilities, "multiscribe_publish_success_total"),
                "publish_failure": _build_counter(capabilities, "multiscribe_publish_failure_total"),
                "llm_calls": _build_counter(capabilities, "multiscribe_llm_calls_total"),
                "tool_calls": _build_counter(capabilities, "multiscribe_tool_calls_total"),
            },
            _histograms={
                "llm_latency": _build_histogram(
                    capabilities, "multiscribe_llm_latency_seconds"
                ),
                "publish_latency": _build_histogram(
                    capabilities, "multiscribe_publish_latency_seconds"
                ),
            },
        )

    def record_publish(self, success: bool, duration_seconds: float) -> None:
        key = "publish_success" if success else "publish_failure"
        _increment(self._counters[key])
        _observe(self._histograms["publish_latency"], duration_seconds)

    def record_llm_call(self, tokens: int, duration_seconds: float) -> None:
        _increment(self._counters["llm_calls"], tokens)
        _observe(self._histograms["llm_latency"], duration_seconds)

    def record_tool_call(self, tool_name: str) -> None:
        _increment(self._counters["tool_calls"], 1)


def _build_counter(capabilities: Any, name: str) -> Any:
    if not capabilities.meter:
        return _NoopCounter()
    try:
        from opentelemetry import metrics as otel_metrics  # type: ignore[import-not-found]
        meter = otel_metrics.get_meter("multiscribe-agent")
        return meter.create_counter(name, unit="1")
    except Exception:  # pragma: no cover - optional backend
        return _NoopCounter()


def _build_histogram(capabilities: Any, name: str) -> Any:
    if not capabilities.meter:
        return _NoopHistogram()
    try:
        from opentelemetry import metrics as otel_metrics  # type: ignore[import-not-found]
        meter = otel_metrics.get_meter("multiscribe-agent")
        return meter.create_histogram(name, unit="s")
    except Exception:  # pragma: no cover
        return _NoopHistogram()


def _increment(counter: Any, amount: int = 1) -> None:
    if hasattr(counter, "add"):
        try:
            counter.add(amount)
        except Exception:
            pass


def _observe(histogram: Any, value: float) -> None:
    if hasattr(histogram, "record"):
        try:
            histogram.record(value)
        except Exception:
            pass


class _NoopCounter:
    def add(self, *_args: Any, **_kwargs: Any) -> None:
        return None


class _NoopHistogram:
    def record(self, *_args: Any, **_kwargs: Any) -> None:
        return None
```

### T3：tracer.py（Tracer 启动 + span helper）

```python
# src/multiscribe_agent/observability/tracer.py
"""OTel tracer setup with graceful no-op fallback."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator

from multiscribe_agent.observability.optional import detect


def setup_tracer() -> Any:
    """Initialize the global OTel tracer provider, or return a no-op tracer."""
    capabilities = detect()
    if not capabilities.tracer:
        return _NoopTracer()

    try:
        from opentelemetry import trace  # type: ignore[import-not-found]
        from opentelemetry.sdk.resources import Resource  # type: ignore[import-not-found]
        from opentelemetry.sdk.trace import TracerProvider  # type: ignore[import-not-found]
        from opentelemetry.sdk.trace.export import (  # type: ignore[import-not-found]
            BatchSpanProcessor,
            ConsoleSpanExporter,
        )
    except ImportError:
        return _NoopTracer()

    resource = Resource.create({"service.name": "multiscribe-agent"})
    provider = TracerProvider(resource=resource)
    if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # type: ignore[import-not-found]
                OTLPSpanExporter,
            )
            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        except ImportError:
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    else:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    return trace.get_tracer("multiscribe-agent")


@contextmanager
def trace_span(name: str, attributes: dict[str, Any] | None = None) -> Iterator[Any]:
    """Start a span if a tracer is configured; otherwise a no-op context."""
    capabilities = detect()
    if not capabilities.tracer:
        yield _NoopSpan()
        return

    try:
        from opentelemetry import trace  # type: ignore[import-not-found]
    except ImportError:
        yield _NoopSpan()
        return

    tracer = trace.get_tracer("multiscribe-agent")
    with tracer.start_as_current_span(name, attributes=attributes or {}) as span:
        yield span


class _NoopTracer:
    def start_as_current_span(self, *_args: Any, **_kwargs: Any) -> "_NoopSpan":
        return _NoopSpan()


class _NoopSpan:
    def set_attribute(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def set_status(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def record_exception(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def end(self) -> None:
        return None

    def __enter__(self) -> "_NoopSpan":
        return self

    def __exit__(self, *_exc_info: Any) -> None:
        return None
```

### T4：metrics 端点

```python
# src/multiscribe_agent/api/routes/metrics.py
"""Prometheus scrape endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Response

from multiscribe_agent.observability.optional import detect

router = APIRouter(tags=["observability"])


@router.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    """Render Prometheus text exposition; degrade to empty 503 if backend missing."""
    capabilities = detect()
    if not capabilities.prometheus_endpoint:
        return Response(content="", media_type="text/plain", status_code=503)

    try:
        from prometheus_client import (  # type: ignore[import-not-found]
            CONTENT_TYPE_LATEST,
            generate_latest,
        )
    except ImportError:
        return Response(content="", media_type="text/plain", status_code=503)

    body = generate_latest()
    return Response(content=body, media_type=CONTENT_TYPE_LATEST)
```

### T5：core/logging.py 注入 trace_id filter

```python
# src/multiscribe_agent/core/logging.py  在 structlog.configure(...) 之前插入：

def _inject_trace_id(_logger: Any, _method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Add the current trace_id (if any) to every log event."""
    try:
        from opentelemetry import trace  # type: ignore[import-not-found]
    except ImportError:
        return event_dict
    span = trace.get_current_span()
    if span is None:
        return event_dict
    ctx = span.get_span_context()
    if ctx and ctx.is_valid:
        event_dict.setdefault("trace_id", format(ctx.trace_id, "032x"))
    return event_dict

# 在 processors 链最前面追加 _inject_trace_id：
processors = [
    _inject_trace_id,
    structlog.contextvars.merge_contextvars,
    # ... 其余既有 processors ...
]
```

### T6：bootstrap.py 初始化 observability

```python
# src/multiscribe_agent/bootstrap.py  bootstrap() 函数中追加（最后阶段）：

from multiscribe_agent.observability.optional import detect
from multiscribe_agent.observability.meter import MetricsRegistry
from multiscribe_agent.observability.tracer import setup_tracer

ctx.observability_capabilities = detect()
ctx.metrics = MetricsRegistry.create(ctx.observability_capabilities)
ctx.tracer = setup_tracer()
```

并在 `app.py` 启动时调用一次：

```python
# src/multiscribe_agent/app.py  create_app() 内：

from multiscribe_agent.api.routes.metrics import router as metrics_router
from multiscribe_agent.bootstrap import ServiceContext

app.include_router(metrics_router)

# FastAPI middleware：在请求作用域内为 structlog contextvars 注入 trace_id
@app.middleware("http")
async def _inject_trace_id(request, call_next):
    from multiscribe_agent.observability.tracer import setup_tracer  # 触发 setup
    # 让 OTel 自动 instrumentation 接管；保留 contextvars 透传
    response = await call_next(request)
    return response
```

### T7：在 Agent executor / publisher 关键点埋点

```python
# src/multiscribe_agent/agents/executor.py  在 LLM 调用前后：

from multiscribe_agent.observability.tracer import trace_span
from multiscribe_agent.bootstrap import _current_metrics  # 单例

# LLM call site:
with trace_span("llm.generate", {"agent_id": agent_id, "model": model}):
    response = await provider.generate(messages, system_instruction=...)
    _current_metrics().record_llm_call(tokens=response.usage_tokens, duration_seconds=...)

# Tool call site:
with trace_span("tool.invoke", {"tool": tool_name}):
    output = await tool.invoke(args)
    _current_metrics().record_tool_call(tool_name)
```

```python
# src/multiscribe_agent/services/publishing.py  在 publish 调用前后：

from multiscribe_agent.observability.tracer import trace_span
from multiscribe_agent.bootstrap import _current_metrics

start = time.monotonic()
with trace_span("publisher.publish", {"publisher": publisher.metadata.name}):
    result = await publisher.publish(content, options)
duration = time.monotonic() - start
_current_metrics().record_publish(success=result.get("ok", False), duration_seconds=duration)
```

### T8：pyproject.toml 可选依赖

```toml
[project.optional-dependencies]
observability = [
    "opentelemetry-api>=1.27",
    "opentelemetry-sdk>=1.27",
    "opentelemetry-exporter-otlp>=1.27",
    "opentelemetry-instrumentation-fastapi>=0.48b0",
    "prometheus-client>=0.20",
]
```

---

## 六、测试与质量门

```bash
.venv\Scripts\python.exe -m pip install -e ".[observability]"

.venv\Scripts\python.exe -m pytest tests/observability -v -p no:cacheprovider --basetemp .pytest-tmp-p23

# 全量
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider

# 静态门
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .
.venv\Scripts\python.exe -m mypy src
```

**手动冒烟**：
```bash
.venv\Scripts\python.exe -m multiscribe_agent serve &
curl http://localhost:8000/metrics | head -30
# 期望：看到 multiscribe_publish_success_total / multiscribe_llm_calls_total 等指标
```

---

## 七、完成定义

- [ ] 白名单 16 个文件全部创建/修改
- [ ] `pytest tests/observability` 全绿（≥ 14 用例）
- [ ] `pytest -q` 全量无回归
- [ ] ruff / mypy 全绿
- [ ] 缺 OTel 包时仍能启动（degradation 路径走通）
- [ ] `curl /metrics` 返回 multiscribe_* 指标
- [ ] `codex/reviews/P23-REVIEW.md` 填写完毕

---

## 八、文件清单

```
src/multiscribe_agent/observability/__init__.py          [新增]
src/multiscribe_agent/observability/optional.py          [新增]
src/multiscribe_agent/observability/tracer.py            [新增]
src/multiscribe_agent/observability/meter.py             [新增]
src/multiscribe_agent/api/routes/metrics.py              [新增]
src/multiscribe_agent/core/logging.py                    [修改]
src/multiscribe_agent/bootstrap.py                       [修改]
src/multiscribe_agent/app.py                             [修改]
src/multiscribe_agent/agents/executor.py                 [修改]
src/multiscribe_agent/services/publishing.py             [修改]
pyproject.toml                                           [修改]
tests/observability/__init__.py                          [新增]
tests/observability/test_tracer.py                       [新增]
tests/observability/test_meter.py                        [新增]
tests/observability/test_metrics_endpoint.py             [新增]
tests/observability/test_optional_degradation.py         [新增]
```