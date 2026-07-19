# Review: P21-评估框架

**执行包**：`docs/phases/P21-评估框架.md`  
**完成日期**：2026-07-19  
**执行者**：Codex

## 1. 范围核对

| 文件路径 | 操作 | 用途 |
| :--- | :--- | :--- |
| `src/multiscribe_agent/eval/__init__.py` | 新增 | 导出评估 public API |
| `src/multiscribe_agent/eval/__main__.py` | 新增 | 支持 `python -m multiscribe_agent eval` |
| `src/multiscribe_agent/eval/dataset.py` | 新增 | YAML 数据集加载与 schema 校验 |
| `src/multiscribe_agent/eval/evaluator.py` | 新增 | summary/relevance/stability 三维度 LLM-as-Judge |
| `src/multiscribe_agent/eval/benchmark.py` | 新增 | 批量评估、回归检测、Markdown 报告 |
| `src/multiscribe_agent/eval/judge_prompts.py` | 新增 | Judge prompt rubrics |
| `data/eval/datasets/tech_weekly.yaml` | 新增 | 5 个技术周报样本 |
| `data/eval/datasets/summary_quality.yaml` | 新增 | 3 个摘要质量样本 |
| `src/multiscribe_agent/cli.py` | 修改 | 增加 `eval` 子命令和数据集别名解析 |
| `tests/eval/*` | 新增 | dataset/evaluator/benchmark/feedback_loop 测试与 8 个 fixture |

白名单合规：上述文件均在 P21 白名单或 `tests/eval/fixtures/*.json` 通配范围内；未触碰 P21 黑名单中的 Pipeline/API/Frontend 文件。

## 2. 验收对照

| # | 验收条件 | 状态 | 证据 |
| :--- | :--- | :--- | :--- |
| 1 | `multiscribe-agent eval --dataset tech-weekly` 可执行 | 部分通过 | `python -m multiscribe_agent eval --help` 退出码 0；真实 eval 会调用 LLM，未做外网实跑 |
| 2 | `dataset.py` 可加载 YAML | 通过 | `tests/eval/test_dataset.py` |
| 3 | 三维度评分返回 accuracy/conciseness/format/relevance/stability | 通过 | `tests/eval/test_evaluator.py` |
| 4 | 回归检测下降 >10% 抛 `RegressionDetected` | 通过 | `tests/eval/test_benchmark.py::test_benchmark_detects_regression` |
| 5 | 报告输出到 `data/eval/reports/{dataset}_{timestamp}.md` | 通过 | `tests/eval/test_benchmark.py::test_benchmark_writes_summary_and_report` |
| 6 | 不修改 Pipeline，仅读 pipeline_state JSON | 通过 | P21 实现只读 `tests/eval/fixtures/*.json` |
| 7 | 全量 pytest + ruff + mypy | 部分通过 | pytest/mypy/ruff check 通过；全量 format 被既有白名单外文件阻塞，见第 3 节 |

## 3. 测试与质量门

```text
.venv\Scripts\python.exe -m pytest tests/eval -q -p no:cacheprovider --basetemp .pytest-tmp-p21
11 passed in 0.28s
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

## 4. 任务完成情况

- T1-T2：实现 YAML dataset schema 与三套 judge prompts。
- T3：实现 `score_summary`、`score_relevance`、`score_stability`、`evaluate_sample`，统一抛 `JudgeError`。
- T4：实现 `run_benchmark`、Markdown report、baseline 更新与 `RegressionDetected`。
- T5：CLI 增加 `eval` 子命令，并兼容 `summary-quality`/`summary_quality` 命名。
- T6-T7：新增 2 个 dataset、8 个 fixture、11 个 P21 测试。

## 5. 风险与遗留

- CLI help 在 PowerShell 输出中文有编码乱码，但退出码为 0，功能可执行。
- 未做真实 LLM eval 外网实跑；当前证据来自 mock provider 单测。
- `PyYAML` 当前来自环境已有依赖，代码用 `type: ignore[import-untyped]` 处理缺类型桩。

## 6. 自评

我认为 P21 代码和测试满足主要完成定义；全量 format 门因白名单外既有脏文件未完全满足，需要单独处理该文件后再复跑。
