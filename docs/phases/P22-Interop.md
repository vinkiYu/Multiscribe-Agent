# 执行包：P22 — Interop 互操作层

> **阶段**：阶段四（与 P23 / P24 同期开发）
> **目标**：让外部 AI（Claude/GPT）通过标准 OpenAI Function Calling 协议调用 Multiscribe。
> **依赖**：P12（REST API 骨架）、P5（插件发现）、P16/P18（MCP 工具可复用）。
> **并行说明**：与 P23、P24 独立开发；不阻塞 P21 评估。

---

## 一、目标与验收口径

**核心目标**：
- 外部 AI 通过 `sk_*` API Key 自助注册 → 管理员审批 → 工具发现 → 执行网关的完整链路。
- 工具以 **OpenAI Function Calling schema** 导出，Claude / GPT / DeepSeek 通用。
- 与 P18 MCP 不重复：P18 服务于 AI Agent within Multiscribe；P22 服务于外部 AI 调用 Multiscribe。

**验收口径**：
- `POST /api/ai/v1/register` 生成 `sk_xxx`，sha256 hash 入库。
- `GET /api/ai/v1/tools` 返回 OpenAI tools 数组（基于已有 adapter/publisher 元数据）。
- `POST /api/ai/v1/execute` 统一入口，按 tool 名路由到实际 handler。
- 默认白名单模式：新注册即通过；管理员可切换到审批模式。

---

## 二、验收条件

| # | 验收 | 证据 |
|---|---|---|
| 1 | `POST /api/ai/v1/register` 返回 `{api_key, key_id}`，明文仅返回一次 | 单测 |
| 2 | sha256 hash 持久化在 `interop_keys` 表 | SQLite inspection |
| 3 | `GET /api/ai/v1/tools` 返回 OpenAI tools 数组，name/description/parameters 三段齐全 | HTTP 集成测试 |
| 4 | `POST /api/ai/v1/execute` 按 tool_name 调用对应 handler，返回 `{ok, output}` | 单测 + HTTP |
| 5 | 错误情况：`unknown_tool` / `invalid_key` / `rate_limited` 三个明确错误码 | 单测 |
| 6 | 默认模式 `whitelist`：新 key 直接 `approved=True`；模式 `approval` 时管理员需 PUT 审批 | 单测 |
| 7 | 速率限制：默认 60 req/min/key（Redis 缺失时退化为内存） | 单测 |
| 8 | 全量 pytest + ruff + mypy 通过 | `pytest -q` |

> **修订记录**：
> - **rev1**（2026-07-19）：白名单补列 `app.py`，因 T7/文件清单要求挂载 `/api/ai/v1` router，不修改则验收 7 不可触发。

---

## 三、可改范围（白名单）

| 文件路径 | 操作 |
|---|---|
| `src/multiscribe_agent/services/interop.py` | **新增**（API Key 注册/审批/验证） |
| `src/multiscribe_agent/services/interop_rate_limit.py` | **新增**（滑动窗口内存限流器） |
| `src/multiscribe_agent/services/interop_registry.py` | **新增**（tool schema 注册 + 路由） |
| `src/multiscribe_agent/api/routes/ai_v1.py` | **新增**（register / tools / execute 三个端点） |
| `src/multiscribe_agent/domain/models.py` | **修改**（追加 `InteropKey` frozen model） |
| `src/multiscribe_agent/infra/db.py` | **修改**（追加 `interop_keys` 表 + 迁移） |
| `src/multiscribe_agent/bootstrap.py` | **修改**（初始化 interop_service 单例） |
| `src/multiscribe_agent/app.py` | **修改**（注册 `/api/ai/v1` router；缺此条路由无法挂载，验收无法触发） |
| `tests/interop/__init__.py` | **新增** |
| `tests/interop/test_api_v1_register.py` | **新增** |
| `tests/interop/test_api_v1_tools.py` | **新增** |
| `tests/interop/test_api_v1_execute.py` | **新增** |
| `tests/interop/test_service_interop.py` | **新增** |
| `tests/interop/test_rate_limit.py` | **新增** |

---

## 四、禁止改动（黑名单）

- `src/multiscribe_agent/api/routes/mcp.py`（P18 已存在 MCP 端点；不要混淆）
- `src/multiscribe_agent/api/security.py`（人类用户 JWT；AI Key 用独立中间件）
- `src/multiscribe_agent/agents/`、`src/multiscribe_agent/pipelines/`（不调用 AI 工具）
- `frontend/`、`docs/`、`codex/`（除本任务包外的所有文档）

---

## 五、详细任务

### T1：domain/models.py 追加 InteropKey

```python
# src/multiscribe_agent/domain/models.py 末尾追加

class InteropKey(BaseModel):
    key_id: str  # 公开发布的 id，如 "ik_abc123"
    key_hash: str  # sha256(secret)，不入明文
    description: str
    created_at: int
    approved: bool
    rate_limit_per_minute: int = 60
    last_used_at: int | None = None
    request_count: int = 0
```

### T2：infra/db.py 追加 interop_keys 表

```python
# 在现有 _SCHEMA 字符串末尾追加：

CREATE TABLE IF NOT EXISTS interop_keys (
    key_id TEXT PRIMARY KEY,
    key_hash TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL,
    approved INTEGER NOT NULL DEFAULT 0,
    rate_limit_per_minute INTEGER NOT NULL DEFAULT 60,
    last_used_at INTEGER,
    request_count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_interop_keys_approved ON interop_keys(approved);
```

### T3：services/interop_rate_limit.py（滑动窗口）

```python
# src/multiscribe_agent/services/interop_rate_limit.py
"""In-memory sliding-window rate limiter for interop API keys."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass


class RateLimitExceeded(RuntimeError):
    """Raised when a key exceeds its configured per-minute quota."""


@dataclass(slots=True)
class SlidingWindowLimiter:
    """Track request timestamps per key in a bounded deque."""

    window_seconds: int = 60
    _hits: dict[str, deque[float]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self._hits = defaultdict(deque)

    def check(self, key_id: str, limit: int) -> None:
        """Drop expired hits then enforce the limit; raise if exceeded."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        hits = self._hits[key_id]
        while hits and hits[0] < cutoff:
            hits.popleft()
        if len(hits) >= limit:
            raise RateLimitExceeded(
                f"key {key_id} exceeded {limit} req/{self.window_seconds}s"
            )
        hits.append(now)

    def reset(self) -> None:
        self._hits.clear()
```

### T4：services/interop.py（注册/审批/验证）

```python
# src/multiscribe_agent/services/interop.py
"""API Key issuance, approval, and verification for external AI access."""

from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from multiscribe_agent.domain.models import InteropKey
from multiscribe_agent.infra.db import get_connection

Mode = Literal["whitelist", "approval"]


@dataclass(frozen=True, slots=True)
class IssuedKey:
    api_key: str  # 明文，仅创建时返回一次
    key_id: str  # 公开标识


class InteropError(RuntimeError):
    """Raised for all interop authentication and authorization failures."""


def generate_key(description: str, mode: Mode = "whitelist") -> IssuedKey:
    """Create a new API key, persisting only its sha256 hash."""
    secret = "sk_" + secrets.token_urlsafe(32)
    key_id = "ik_" + secrets.token_urlsafe(8)
    key_hash = hashlib.sha256(secret.encode("utf-8")).hexdigest()
    approved = mode == "whitelist"
    record = InteropKey(
        key_id=key_id,
        key_hash=key_hash,
        description=description,
        created_at=int(time.time()),
        approved=approved,
    )
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO interop_keys "
            "(key_id, key_hash, description, created_at, approved, rate_limit_per_minute) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                record.key_id,
                record.key_hash,
                record.description,
                record.created_at,
                int(record.approved),
                record.rate_limit_per_minute,
            ),
        )
        conn.commit()
    return IssuedKey(api_key=secret, key_id=key_id)


def verify_key(api_key: str) -> InteropKey:
    """Look up a key by hash; raise InteropError if missing, wrong, or unapproved."""
    if not api_key.startswith("sk_"):
        raise InteropError("api_key must start with sk_")
    key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT key_id, key_hash, description, created_at, approved, "
            "rate_limit_per_minute, last_used_at, request_count "
            "FROM interop_keys WHERE key_hash = ?",
            (key_hash,),
        ).fetchone()
    if row is None:
        raise InteropError("invalid api_key")
    record = InteropKey(
        key_id=row["key_id"],
        key_hash=row["key_hash"],
        description=row["description"],
        created_at=row["created_at"],
        approved=bool(row["approved"]),
        rate_limit_per_minute=row["rate_limit_per_minute"],
        last_used_at=row["last_used_at"],
        request_count=row["request_count"],
    )
    if not record.approved:
        raise InteropError("api_key not yet approved")
    return record


def approve_key(key_id: str) -> bool:
    """Mark a pending key as approved. Returns True if a row was updated."""
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE interop_keys SET approved = 1 WHERE key_id = ?",
            (key_id,),
        )
        conn.commit()
        return cursor.rowcount > 0


def touch_usage(key_id: str) -> None:
    """Increment request count and update last_used_at (best-effort)."""
    now = int(time.time())
    with get_connection() as conn:
        conn.execute(
            "UPDATE interop_keys SET request_count = request_count + 1, last_used_at = ? "
            "WHERE key_id = ?",
            (now, key_id),
        )
        conn.commit()
```

### T5：services/interop_registry.py（tool schema 注册）

```python
# src/multiscribe_agent/services/interop_registry.py
"""Register and dispatch tools exposed to external AI clients."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

ToolHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class ToolSchema:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema object


class UnknownToolError(KeyError):
    """Raised when an external AI requests an unregistered tool."""


class ToolRegistry:
    """In-process tool registry; safe to share across requests."""

    def __init__(self) -> None:
        self._tools: dict[str, tuple[ToolSchema, ToolHandler]] = {}

    def register(self, schema: ToolSchema, handler: ToolHandler) -> None:
        self._tools[schema.name] = (schema, handler)

    def list_schemas(self) -> list[dict[str, Any]]:
        """Return OpenAI tools-format list: [{type, function:{name, description, parameters}}]."""
        return [
            {
                "type": "function",
                "function": {
                    "name": schema.name,
                    "description": schema.description,
                    "parameters": schema.parameters,
                },
            }
            for schema, _ in self._tools.values()
        ]

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if tool_name not in self._tools:
            raise UnknownToolError(f"unknown tool: {tool_name}")
        _, handler = self._tools[tool_name]
        return await handler(arguments)


# Built-in tool factories --------------------------------------------------

def build_default_registry(context: Any) -> ToolRegistry:
    """Create the default registry with adapter/publisher tools wired to ServiceContext."""
    registry = ToolRegistry()

    registry.register(
        ToolSchema(
            name="list_sources",
            description="List all configured content sources (RSS, GitHub, AI search).",
            parameters={"type": "object", "properties": {}, "required": []},
        ),
        lambda _args: _list_sources_handler(context),
    )
    registry.register(
        ToolSchema(
            name="kb_search",
            description="Search the persistent knowledge base by query.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1},
                    "top_k": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
                },
                "required": ["query"],
            },
        ),
        lambda args: _kb_search_handler(context, args),
    )
    registry.register(
        ToolSchema(
            name="list_publishers",
            description="List configured publishers (Feishu, WeCom, WeChat, ...).",
            parameters={"type": "object", "properties": {}, "required": []},
        ),
        lambda _args: _list_publishers_handler(context),
    )
    return registry


async def _list_sources_handler(context: Any) -> dict[str, Any]:
    if context.plugin_manager is None:
        return {"sources": []}
    sources = [
        {"name": adapter.metadata.name, "kind": "adapter"}
        for adapter in context.plugin_manager.adapters()
    ]
    return {"sources": sources}


async def _kb_search_handler(context: Any, args: dict[str, Any]) -> dict[str, Any]:
    if context.kb_service is None:
        return {"hits": [], "degraded": True}
    hits = await context.kb_service.search(args["query"], top_k=int(args.get("top_k", 10)))
    return {
        "hits": [
            {
                "chunk_id": h.chunk_id,
                "document_id": h.document_id,
                "content": h.content,
                "score": h.score,
            }
            for h in hits
        ],
        "degraded": context.kb_service.capabilities.degraded,
    }


async def _list_publishers_handler(context: Any) -> dict[str, Any]:
    if context.plugin_manager is None:
        return {"publishers": []}
    return {
        "publishers": [
            {"name": pub.metadata.name, "kind": "publisher"}
            for pub in context.plugin_manager.publishers()
        ]
    }
```

### T6：api/routes/ai_v1.py（三个端点）

```python
# src/multiscribe_agent/api/routes/ai_v1.py
"""External AI access: registration, tool discovery, execution gateway."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException

from multiscribe_agent.api.deps import get_context
from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.services.interop import (
    InteropError,
    approve_key,
    generate_key,
    touch_usage,
    verify_key,
)
from multiscribe_agent.services.interop_rate_limit import (
    RateLimitExceeded,
    SlidingWindowLimiter,
)
from multiscribe_agent.services.interop_registry import (
    ToolRegistry,
    UnknownToolError,
)

router = APIRouter(prefix="/api/ai/v1", tags=["interop"])


def _resolve_limiter(context: ServiceContext) -> SlidingWindowLimiter:
    """Return the shared limiter stored on the service context."""
    if context.interop_limiter is None:
        raise HTTPException(status_code=503, detail="interop limiter unavailable")
    return context.interop_limiter


@router.post("/register")
async def register(payload: dict[str, Any]) -> dict[str, Any]:
    """Mint a new external AI API key. The plaintext secret is shown once."""
    description = str(payload.get("description", "")).strip()[:200]
    mode = "whitelist" if payload.get("auto_approve", True) else "approval"
    issued = generate_key(description, mode=mode)  # type: ignore[arg-type]
    return {"api_key": issued.api_key, "key_id": issued.key_id, "approved": mode == "whitelist"}


@router.put("/keys/{key_id}/approve")
async def approve(key_id: str) -> dict[str, str]:
    if not approve_key(key_id):
        raise HTTPException(status_code=404, detail="key not found")
    return {"status": "approved"}


@router.get("/tools")
async def tools(context: ServiceContext = Depends(get_context)) -> dict[str, Any]:
    """Return the OpenAI-format tool list."""
    if context.interop_registry is None:
        raise HTTPException(status_code=503, detail="tool registry unavailable")
    return {"tools": context.interop_registry.list_schemas()}


@router.post("/execute")
async def execute(
    payload: dict[str, Any],
    context: ServiceContext = Depends(get_context),
    x_api_key: str | None = Header(default=None),
) -> dict[str, Any]:
    """Authenticate, rate-limit, then dispatch a single tool call."""
    if not x_api_key:
        raise HTTPException(status_code=401, detail="missing X-API-Key")
    try:
        record = verify_key(x_api_key)
    except InteropError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    limiter = _resolve_limiter(context)
    try:
        limiter.check(record.key_id, record.rate_limit_per_minute)
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    if context.interop_registry is None:
        raise HTTPException(status_code=503, detail="tool registry unavailable")
    registry: ToolRegistry = context.interop_registry

    tool_name = str(payload.get("name", "")).strip()
    if not tool_name:
        raise HTTPException(status_code=400, detail="name is required")
    arguments = payload.get("arguments", {})
    if not isinstance(arguments, dict):
        raise HTTPException(status_code=400, detail="arguments must be an object")

    touch_usage(record.key_id)
    try:
        output = await registry.execute(tool_name, arguments)
    except UnknownToolError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "tool": tool_name, "output": output}
```

### T7：bootstrap.py 注入互操作组件

```python
# src/multiscribe_agent/bootstrap.py  ServiceContext 类内追加字段

@dataclass
class ServiceContext:
    # ... existing fields ...
    interop_limiter: SlidingWindowLimiter | None = None
    interop_registry: ToolRegistry | None = None

# 初始化处（在 bootstrap() 中追加）
from multiscribe_agent.services.interop_rate_limit import SlidingWindowLimiter
from multiscribe_agent.services.interop_registry import (
    ToolRegistry,
    build_default_registry,
)

# 在已经构建好 plugin_manager 之后：
ctx.interop_limiter = SlidingWindowLimiter(window_seconds=60)
ctx.interop_registry = build_default_registry(ctx)
```

并在 `app.py` 注册 router：`app.include_router(ai_v1.router)`。

---

## 六、测试与质量门

```bash
.venv\Scripts\python.exe -m pytest tests/interop -v -p no:cacheprovider --basetemp .pytest-tmp-p22

# 全量
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider

# 静态门
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .
.venv\Scripts\python.exe -m mypy src
```

---

## 七、完成定义

- [ ] 白名单 13 个文件全部创建/修改
- [ ] `pytest tests/interop` 全绿（≥ 18 用例）
- [ ] `pytest -q` 全量无回归
- [ ] ruff / mypy 全绿
- [ ] 手动 curl：`POST /api/ai/v1/register` 返回 `api_key`；`GET /api/ai/v1/tools` 返回 OpenAI 数组；`POST /api/ai/v1/execute` 调用 `kb_search`
- [ ] `codex/reviews/P22-REVIEW.md` 填写完毕

---

## 八、文件清单

```
src/multiscribe_agent/services/interop.py            [新增]
src/multiscribe_agent/services/interop_rate_limit.py  [新增]
src/multiscribe_agent/services/interop_registry.py   [新增]
src/multiscribe_agent/api/routes/ai_v1.py            [新增]
src/multiscribe_agent/domain/models.py               [修改]
src/multiscribe_agent/infra/db.py                    [修改]
src/multiscribe_agent/bootstrap.py                   [修改]
src/multiscribe_agent/app.py                         [修改]
tests/interop/__init__.py                            [新增]
tests/interop/test_api_v1_register.py                [新增]
tests/interop/test_api_v1_tools.py                   [新增]
tests/interop/test_api_v1_execute.py                 [新增]
tests/interop/test_service_interop.py                [新增]
tests/interop/test_rate_limit.py                     [新增]
```