# Review: P26-Harness 与工作流稳定性

**执行包**：`docs/phases/P26-Harness与工作流稳定性.md`  
**完成日期**：2026-07-20  
**执行者**：Codex

## 1. 范围核对

### 1.1 实际改动文件

| 文件 | 操作 | 说明 |
| --- | --- | --- |
| `src/multiscribe_agent/agents/executor.py` | 修改 | 重复工具调用检测、预算预警事件 |
| `src/multiscribe_agent/agents/events.py` | 修改 | 注册 `loop_detected`、`budget_warning` 事件类型 |
| `src/multiscribe_agent/core/event_bus.py` | 新增 | 异步发布/订阅与异常隔离 |
| `src/multiscribe_agent/agents/workflow/loop_node.py` | 修改 | Loop checkpoint 写入与恢复 |
| `src/multiscribe_agent/agents/workflow/iteration_store.py` | 新增 | 迭代记录 CRUD 与 `resume_loop` |
| `src/multiscribe_agent/infra/db.py` | 修改 | `workflow_iterations` 表及索引 |
| `src/multiscribe_agent/bootstrap.py` | 修改 | 装配进程级 EventBus |
| `tests/agents/test_executor_deadlock_detection.py` | 新增 | 死锁与预算事件测试 |
| `tests/core/test_event_bus.py` | 新增 | 发布、线程安全、异常隔离测试 |
| `tests/agents/workflow/test_loop_persistence.py` | 新增 | 持久化与重启恢复测试 |

上述文件均在 P26 白名单内；`infra/db.py` 和 `bootstrap.py` 同时承载 P27/P28 的必要接线。未修改 P26 黑名单中的 `context.py`、DAG engine、API routes 或 frontend。

## 2. 验收条件逐条对照

| # | 验收条件 | 状态 | 证据 |
| --- | --- | --- | --- |
| 1 | 连续 3 次同工具同参数产生 `loop_detected` 并退出 | PASS | `executor.py:36-37, 124, 193-210`；`tests/agents/test_executor_deadlock_detection.py:21-35` |
| 2 | 预算占用达到 80% 产生非阻塞 `budget_warning` | PASS | `executor.py:127-138`；`tests/agents/test_executor_deadlock_detection.py:38-52` |
| 3 | `digest.completed` 发布后订阅者收到 payload | PASS | `core/event_bus.py:40-49`；`tests/core/test_event_bus.py:13-31` |
| 4 | EventBus 异步、线程安全、订阅异常隔离 | PASS | `core/event_bus.py:22-74` 使用 `RLock`、快照和 `asyncio.gather`；`tests/core/test_event_bus.py:33-50` |
| 5 | 每轮 Loop 结果写入 `workflow_iterations` | PASS | `loop_node.py:108-128`；`iteration_store.py:27-58`；`infra/db.py:503-516` |
| 6 | 重启后从最近 checkpoint 继续 | PASS | `loop_node.py:70-91` 恢复输入和轮次；`iteration_store.py:83-112`；`tests/agents/workflow/test_loop_persistence.py:40-68` |
| 7 | 全量 pytest、ruff、mypy 通过 | PASS | 见第 3 节原始输出 |

## 3. 测试与质量门

### 3.1 全量 pytest

命令：

```text
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .pytest-tmp-rerun
```

原始结果：

```text
325 passed, 4 deselected, 1 warning in 32.98s
```

说明：使用项目内 `--basetemp` 是为了避开当前 Windows 用户临时目录的权限限制；测试本身无失败。

### 3.2 静态质量门

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

- **T1 ReAct 死锁检测**：以工具名和规范化参数的 SHA-256 前缀形成签名，窗口内连续三次相同签名时先发事件再返回，不抛异常。
- **T2 Token 预算事件**：每轮开始消费既有 `HarnessContext.should_warn_budget(0.8)`，只发通知，执行流继续。
- **T3 领域事件总线**：订阅注册/移除和单例替换使用 `RLock`；发布时复制订阅快照，并行执行 callback；单个 callback 异常只记录日志。
- **T4 Loop 持久化**：新增带主键 `(workflow_run_id, step_id, round)` 的表；恢复时读取最新记录，保留 feedback 并从下一轮继续；重复 checkpoint 使用 upsert。

## 5. 规范符合性自检

- [x] 类型标注完整，`mypy --strict` 通过。
- [x] 异步路径使用 `async def`，未引入同步 I/O。
- [x] 事件订阅异常被隔离；不把 token、secret 写入日志。
- [x] API 路由和前端未被事件总线直接耦合。
- [x] 新增行为有定向单测，并通过全量回归。

## 6. 依赖

无新增运行时依赖。

## 7. 风险、遗留与取舍

- EventBus 是进程内总线，不提供跨进程或持久消息语义；多 worker 部署仍需外部 broker，这是后续扩展边界。
- `IterationStore` 通过 `execute_loop_step(..., iteration_store=..., workflow_run_id=...)` 提供恢复能力；现有 workflow engine 默认不传入 store，以保持兼容，生产入口需要在后续接线时显式注入。
- `loop_detected` 只识别连续相同签名，不判断语义等价或参数中的非确定性字段；这是任务包要求的最小死锁判定。
- pytest 输出有一个既有 `httpx`/Starlette deprecation warning，不影响通过结果。

## 8. BLOCKED

无。环境临时目录权限问题已通过项目内 `--basetemp` 绕过，不构成代码阻塞。

## 9. 对后续包的提示

- 后续 workflow engine 若接入恢复，应使用同一 `workflow_run_id` 和 `step_id`，并保留 `IterationStore` 的幂等 upsert 语义。
- 事件主题建议集中维护常量，避免跨模块字符串拼写漂移。

## 10. 自评

本包满足 P26 任务包的完成定义：四项 P1 缺陷均有实现和定向测试，全量回归与静态质量门通过。**判定：PASS，建议进入后续阶段。**
