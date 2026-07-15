# Review: P1-配置与领域模型

**执行包**：`docs/phases/P1-配置与领域模型.md`
**完成日期**：2026-07-15
**执行者**：Codex
**当前状态**：BLOCKED（P1 验收 5 条均通过，但 P0 pre-commit 的隔离 mypy 环境缺少 `pydantic-settings`，无法按仓库规范提交）

## 1. 范围核对

### 1.1 实际改动文件清单

| 文件路径 | 操作 | 用途 |
| :--- | :--- | :--- |
| `src/multiscribe_agent/domain/__init__.py` | 新增 | domain 包声明 |
| `src/multiscribe_agent/domain/models.py` | 新增 | 全部核心 Pydantic 领域契约 |
| `src/multiscribe_agent/domain/ports.py` | 新增 | 5 个异步仓储 Protocol |
| `src/multiscribe_agent/config.py` | 新增 | 默认配置、环境覆盖和 KV override 接口 |
| `src/multiscribe_agent/core/__init__.py` | 新增 | core 包声明 |
| `src/multiscribe_agent/core/errors.py` | 新增 | 领域异常层级 |
| `tests/domain/test_models.py` | 新增 | 模型 happy path、边界与可变默认值测试 |
| `tests/test_config.py` | 新增 | 默认配置、环境覆盖、override 测试 |

- [x] 8 个文件全部在 P1 白名单内。
- [x] 未修改 P0 文件、`pyproject.toml`、`uv.lock`、`docs/`。
- [x] 未创建 infra/db、llm、agents、plugins。
- [x] `git status` 仅显示上述 8 个未跟踪白名单文件。
- [ ] 未提交：真实 pre-commit hook 会因 P0 配置缺少 `pydantic-settings` 而失败，未使用 `--no-verify` 绕过。

## 2. 验收条件逐条对照

| # | 验收条件 | 状态 | 证据 |
| :--- | :--- | :--- | :--- |
| 1 | 全部模型/Protocol/errors 定义齐全且 mypy strict 通过 | PASS | 18 个领域模型、5 个 Protocol、9 个异常类；`Success: no issues found in 9 source files` |
| 2 | domain import 不触发 infra/llm/sqlite/httpx | PASS | 指定隔离命令输出 `clean` |
| 3 | Settings 默认值 + env + KV override 层工作 | PASS | `tests/test_config.py` 5 项测试；定向测试 18/18 通过 |
| 4 | 模型关键字段与原 TS `src/types/` 对齐 | PASS | 对照 `agent.ts/config.ts/index.ts/skill.ts/schedule.ts/memory.ts/knowledge.ts`；snake_case 映射及 P1 新字段已实现 |
| 5 | ruff/mypy/pytest 全绿 | PASS | ruff、format、mypy、定向 18/18、全量 21/21 均通过 |

## 3. 测试与质量门（原始输出）

### 3.1 `uv run ruff check .`

```text
All checks passed!
```

### 3.2 `uv run ruff format --check .`

```text
13 files already formatted
```

### 3.3 `uv run mypy src`

```text
Success: no issues found in 9 source files
```

### 3.4 `uv run pytest tests/domain tests/test_config.py -q`

```text
..................                                                       [100%]
18 passed in 0.16s
```

### 3.5 `uv run pytest -q`

```text
.....................                                                    [100%]
21 passed in 0.19s
```

### 3.6 domain 依赖隔离

命令：

```text
uv run python -c "import multiscribe_agent.domain.models as m; import sys; bad=[x for x in sys.modules if x in ('sqlite3','httpx','aiosqlite')]; assert not bad, bad; print('clean')"
```

输出：

```text
clean
```

### 3.7 模型 docstring 审计

```text
all model docstrings present
```

### 3.8 `uv run pre-commit run --all-files`（额外提交门）

```text
ruff check...............................................................Passed
ruff format..............................................................Passed
mypy.....................................................................Failed
- hook id: mypy
- exit code: 1

src\multiscribe_agent\config.py:8: error: Cannot find implementation or library stub for module named "pydantic_settings"  [import-not-found]
src\multiscribe_agent\config.py:8: note: See https://mypy.readthedocs.io/en/stable/running_mypy.html#missing-imports
src\multiscribe_agent\config.py:97: error: Class cannot subclass "BaseSettings" (has type "Any")  [misc]
src\multiscribe_agent\config.py:144: error: Returning Any from function declared to return "SystemSettings"  [no-any-return]
Found 3 errors in 1 file (checked 9 source files)

trim trailing whitespace.................................................Passed
fix end of files.........................................................Passed
check yaml...............................................................Passed
check toml...............................................................Passed
check for added large files..............................................Passed
```

根因证据：`.pre-commit-config.yaml` 的 mypy `additional_dependencies` 只有 `pydantic>=2.7` 和 `types-click`，未安装 P1 已在 P0 runtime dependencies 中声明的 `pydantic-settings>=2.3`。项目 `.venv` 中运行同一 mypy 命令全绿，故不是源码类型错误。

## 4. 详细任务完成情况

- **T1 领域模型**：`domain/models.py:19` 起定义 UnifiedData、AI 契约、Agent/Workflow、Tool、MCP、Skill、持久化实体、Schedule、Memory/KB 占位；全部有 docstring，所有可变默认值用 `Field(default_factory=...)`。
- **T2 仓储端口**：`domain/ports.py:10` 起定义 Kv、EntityJson、SourceData、TaskLog、ApiKey 5 个异步 Protocol。ApiKey 签名依据 P2 契约补齐 `get_by_token/update_last_used/list_all`。
- **T3 异常**：`core/errors.py:4` 起定义 1 个基类和 8 个具体领域异常。
- **T4 配置**：`config.py:11` 起定义 4 类配置模型；`config.py:97` 定义 SystemSettings；`config.py:121` 提供不读取环境的纯默认常量；`config.py:124` 提供三层 ConfigService。
- **T5 测试**：`tests/domain/test_models.py:42` 起覆盖全部模型及指定边界；`tests/test_config.py:6` 起覆盖默认数量/ID、环境覆盖、集合隔离与异步 KV override。

## 5. 规范符合性

- [x] 全量类型注解，直接 mypy strict 全绿。
- [x] 动态 JSON 仅限模型 metadata/config/raw 和仓储边界；函数签名中的动态值收紧为 `object`，满足 ANN401。
- [x] domain 只依赖标准库、Pydantic 和自身模型，不导入 infra/llm/agents/plugins。
- [x] 无外部 I/O、真实网络、数据库或明文密钥。
- [x] 公共模型、Protocol、方法、异常与配置服务均有 docstring。

## 6. 新增依赖

无。P1 仅使用 P0 已声明的 `pydantic` 与 `pydantic-settings`，`pyproject.toml` 和 `uv.lock` 均未变化。

## 7. 风险、遗留与取舍

- **阻塞/回归**：P0 pre-commit mypy 环境没有随 P1 引入的已声明运行时依赖更新，原地 pre-commit 不再全绿。
- **建议修复**：授权将 `.pre-commit-config.yaml` 加入 P1 修订白名单，并在 mypy hook 的 `additional_dependencies` 增加 `pydantic-settings>=2.3`，随后重跑 pre-commit 和全部质量门再提交。
- **取舍**：Publisher 默认集合以原项目 `github/wechat/rss` 加 P7/P8 的 `feishu_bot/wecom_bot` 组成任务要求的 5 个；Adapter 保留原项目 4 个。
- **取舍**：KV 和动态更新 Protocol 的直接参数使用 `object` 而非裸 `Any`，JSON 字典内部仍允许动态值；这是为满足项目 ANN401 硬门。
- **遗留**：`load_overrides()` P1 返回空字典；P2 按任务包接入 KV 并补保存接口。
- **未做**：未实现 DB、LLM、Agent、插件或 P2 配置持久化。

## 8. BLOCKED 项

- **阻塞点**：修复 `.pre-commit-config.yaml` 超出 P1 白名单；已安装真实 Git pre-commit hook，因此不能规范提交当前改动。
- **等待决策**：请授权 P1 修订白名单增加 `.pre-commit-config.yaml`，或由规划先提供独立基线修复提交。

## 9. 对后续包的提示

- P2 可直接实现 `domain.ports` 的 5 个 Protocol，并在 `ConfigService.load_overrides()` 接入 `system_settings` KV。
- WorkflowStep 已预留 `max_iterations/exit_condition`；P10/P11 无需改领域契约。
- 默认插件 ID 已固定，后续注册中心和 Publisher 应复用这些 ID。

## 10. 自评

- P1 自身 5 条验收条件：全部满足。
- 阶段完成定义：**FAIL/BLOCKED**，原因是 pre-commit 基线回归尚未修复且无法在当前白名单内修复。
- Git commit：未创建；未暂存文件；未绕过 hooks。

## 给 ZCode 的判定请求

请重点判断是否批准把 `.pre-commit-config.yaml` 纳入 P1 修订范围，并仅增加 mypy hook 的 `pydantic-settings>=2.3` 依赖。批准后 Codex 将做单行配置修复、重跑 pre-commit/四项质量门、创建 `feat(domain): add core models and settings` 聚焦提交，再更新本 review 为可放行状态。
