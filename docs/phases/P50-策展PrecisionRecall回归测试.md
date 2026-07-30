# 执行包：P50 — 策展 Precision/Recall 回归测试

> **阶段**：阶段五（方向 4：轻量评测集 Eval）
> **目标**：建带 ground-truth 标注的候选池 fixture，重跑真实策展人 LLM，算 precision/recall/F1，验证 prompt 修改不导致策展质量回归。
> **依赖**：P31.2（已通过，curate 契约加固）、P48（已通过，eval 基础设施）。
> **预估**：1.5 个工作日。
> **来源**：方向 4 探查——两套断连的 eval 系统，CuratorJudge 是死代码，无 ground-truth 标注。

---

## 一、现状诊断（经代码核实，2026-07-30）

| 系统 | 状态 | 问题 |
|---|---|---|
| P21 eval 框架（`eval/`）| 可跑 `multiscribe-agent eval` | 未接 daily_digest；8 个合成一句话 fixture；无候选池；无 selection 标签 |
| P48 curation eval（`_LoopIterationAccumulator`）| 已接 daily_digest | 记录 Loop 自评分（1-10），非 ground-truth |
| CuratorJudge（`curator_judge.py`）| 代码完整、单测过 | **死代码**——`enabled=False`，全代码库无人调用 |

**缺失（4 项全缺）**：候选池 + expected 标注的 fixture 格式；重跑策展人的 harness；precision/recall 计算；回归检测。

---

## 二、用户已确认的 2 个决策

1. **做 Precision/Recall 回归测试**（有 ground truth），**不接线 CuratorJudge**（LLM 主观打分，Layer 2 后续排期）。
2. **用真实 LLM 策展人**：Eval 调 `CURATE_PROMPT` + 真实策展人 provider，拿回选中 ID 集，与 expected 对比。测的是真实策展质量（非纯逻辑单测）。

---

## 三、任务拆解（4 个子任务）

### T1：P50.1 — 候选池 fixture 格式 + 标注数据集

**新增文件**：

| 文件 | 说明 |
|---|---|
| `src/multiscribe_agent/eval/curation_dataset.py` | `CurationCandidate`（id/title/description/url/source，镜像 UnifiedData）、`CurationSample`（candidates + expected_selected_ids + expected_rejected_ids + notes）、`CurationDataset`（name/description/samples）；`load_curation_dataset(path)` YAML 加载器 |
| `data/eval/datasets/curation_recall.yaml` | 标注数据集，引用 fixture JSON |
| `tests/eval/fixtures/cr_001.json` ~ `cr_005.json` | 5 个真实风格候选池 fixture（每个含 10-20 篇候选 + expected_selected/rejected）|

**fixture 格式**（JSON，字段镜像 UnifiedData）：
```json
{
  "candidates": [
    {"id": "a1", "title": "GPT-5 发布", "description": "OpenAI 发布 GPT-5...", "url": "https://...", "source": "rss"},
    {"id": "a2", "title": "某非 AI 通用软件更新", "description": "...", "url": "https://...", "source": "rss"}
  ],
  "expected_selected_ids": ["a1"],
  "expected_rejected_ids": ["a2"]
}
```

**关键约束**：
- `expected_selected_ids` ∩ `expected_rejected_ids` 必须为空（校验）
- 候选池混入非 AI 内容（测 CURATE_PROMPT 的排除能力）
- fixture 内容贴近真实 RSS（中文 AI 资讯 + 干扰项）

### T2：P50.2 — Precision/Recall 评分器

**新增文件**：

| 文件 | 说明 |
|---|---|
| `src/multiscribe_agent/eval/curation_scorer.py` | `CurationScore(precision, recall, f1, selected_ids, expected_selected_ids, passed)`；`score_curation(selected_ids, expected_selected_ids) -> CurationScore` |

**计算**：
- `precision = |selected ∩ expected_selected| / |selected|`（选中里有多少该选）
- `recall = |selected ∩ expected_selected| / |expected_selected|`（该选的里选了多少）
- `f1 = 2 * precision * recall / (precision + recall)`（调和平均）
- `passed = f1 >= 0.7`（阈值，可配）
- 边界：selected 空时 precision=0；expected 空时 recall=1.0

### T3：P50.3 — 策展人 LLM 调用 harness + benchmark runner

**新增文件**：

| 文件 | 说明 |
|---|---|
| `src/multiscribe_agent/eval/curation_benchmark.py` | `run_curation(provider, sample, target_count) -> set[str]`（调真实策展人，返回选中 ID 集）；`run_curation_benchmark(provider, dataset, reports_dir, baseline_path, threshold) -> CurationBenchmarkSummary` |

**`run_curation` 流程**（复用 daily_digest 的策展逻辑，不依赖 pipeline 实例化）：
1. 把 `CurationCandidate` 列表投影成 `_curate_item_dict` 格式（id/title/summary/url/source）
2. `CURATE_PROMPT.format(items=..., feedback="无", target_count=target_count)`
3. `provider.generate([AIMessage(role="user", content=prompt)], system_instruction=...)` 调真实 LLM
4. `_json_array(response.content)` 解析 → 提取每条 `id` → 返回 `set[str]`

**benchmark runner**（复用 P21 的 `run_benchmark` 模式）：
- 遍历 samples，调 `run_curation` + `score_curation`
- 写 Markdown 报告（列：ID / precision / recall / F1 / 状态）
- 回归检测：baseline F1 - current F1 > threshold → `RegressionDetected`

**关键约束**：
- 复用 `_resolve_eval_provider`（cli.py:241）解析真实策展人 provider
- 复用 `CURATE_PROMPT`（不改 prompt 文本）
- `_curate_item_dict` 投影逻辑复刻在 curation_benchmark.py（避免 import pipeline 整个模块拉入 pipeline 依赖）

**JSON 解析参考**：daily_digest 的 `_json_array`（`daily_digest.py` 内）解析 LLM 输出为 JSON 数组。curation_benchmark 应复刻一个轻量版（`json.loads` + 校验是 list + 提取每条的 `id` 字段），不 import daily_digest。

### T4：P50.4 — CLI 命令 + 测试

**改动/新增文件**：

| 文件 | 说明 |
|---|---|
| `src/multiscribe_agent/cli.py` | 新增 `eval-curation` 命令（`--dataset curation-recall --target-count 12 --regression-threshold 0.10`）|
| `tests/eval/test_curation_scorer.py` | precision/recall/F1 计算 + 边界（空集/完全匹配/完全错配）|
| `tests/eval/test_curation_dataset.py` | YAML 加载 + 标注校验（selected/rejected 不重叠）|
| `tests/eval/test_curation_benchmark.py` | 用 FakeProvider 测 harness（不调真实 LLM）+ 回归检测 |

**关键约束**：
- CLI 的 `eval-curation` 与现有 `eval` 并列，不修改现有 `eval` 命令（零回归）
- 测试用 FakeProvider（返回预设 JSON 数组）测 harness 逻辑，**不调真实 LLM**（CI 友好）
- 真实 LLM 跑由用户手动 `multiscribe-agent eval-curation --dataset curation-recall`

---

## 四、白名单与黑名单

### 白名单（可改/新增文件，共 13 个）

```
src/multiscribe_agent/eval/curation_dataset.py             [T1, 新增]
src/multiscribe_agent/eval/curation_scorer.py              [T2, 新增]
src/multiscribe_agent/eval/curation_benchmark.py           [T3, 新增]
src/multiscribe_agent/cli.py                               [T4, 加 eval-curation 命令]
data/eval/datasets/curation_recall.yaml                    [T1, 新增]
tests/eval/fixtures/cr_001.json                            [T1, 新增]
tests/eval/fixtures/cr_002.json                            [T1, 新增]
tests/eval/fixtures/cr_003.json                            [T1, 新增]
tests/eval/fixtures/cr_004.json                            [T1, 新增]
tests/eval/fixtures/cr_005.json                            [T1, 新增]
tests/eval/test_curation_scorer.py                         [T2, 新增]
tests/eval/test_curation_dataset.py                        [T1, 新增]
tests/eval/test_curation_benchmark.py                      [T3/T4, 新增]
docs/phases/P50-策展PrecisionRecall回归测试.md              [本任务包文档]
```

### 黑名单（禁止改动）

- `src/multiscribe_agent/agents/pipelines/daily_digest.py`（不改策展 pipeline）
- `src/multiscribe_agent/agents/pipelines/prompts.py`（不改 CURATE_PROMPT，只 import 复用）
- `src/multiscribe_agent/agents/curator_judge.py`（不接线，Layer 2 后续）
- `src/multiscribe_agent/eval/dataset.py`/`evaluator.py`/`benchmark.py`/`judge_prompts.py`（不改现有 P21 框架）
- `src/multiscribe_agent/agents/workflow/`、`executor.py`、`reflector.py`
- `src/multiscribe_agent/api/`、`frontend/`、`domain/models.py`、`llm/providers/`

---

## 五、验收条件

| # | 验收 | 证据 |
|---|---|---|
| 1 | `CurationDataset` 能从 YAML 加载，candidates 字段镜像 UnifiedData | `test_curation_dataset.py::test_load_curation_dataset` |
| 2 | `expected_selected_ids` ∩ `expected_rejected_ids` 校验为空时 raise | `test_curation_dataset.py::test_overlapping_labels_rejected` |
| 3 | precision = TP/(TP+FP)，selected 空时 = 0 | `test_curation_scorer.py::test_precision` |
| 4 | recall = TP/(TP+FN)，expected 空时 = 1.0 | `test_curation_scorer.py::test_recall` |
| 5 | F1 = 调和平均，完全匹配时 = 1.0 | `test_curation_scorer.py::test_f1_perfect_match` |
| 6 | `run_curation(fake_provider, sample)` 返回策展人选中的 ID 集 | `test_curation_benchmark.py::test_run_curation_extracts_selected_ids` |
| 7 | `run_curation_benchmark` 遍历 samples、写报告、检测回归 | `test_curation_benchmark.py::test_benchmark_detects_regression` |
| 8 | CLI `eval-curation --dataset curation-recall` 可调用（`--help` 显示）| 手动/集成验证 |
| 9 | 现有 `eval` 命令 + 全部 P21 测试无回归 | 原始测试输出 |
| 10 | 全量 pytest + ruff + mypy 通过 | 原始输出 |

---

## 六、测试与质量门

```bash
# 定向测试
.venv\Scripts\python.exe -m pytest tests/eval/ -v -p no:cacheprovider --basetemp .pytest-tmp-p50

# 全量回归
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
.venv\Scripts\python.exe -m ruff check src tests
.venv\Scripts\python.exe -m ruff format --check src tests
.venv\Scripts\python.exe -m mypy src

# 手动真实 LLM 跑（需配置 curation provider API key）
multiscribe-agent eval-curation --dataset curation-recall
```

---

## 七、完成定义

- [ ] 白名单文件全部创建/修改
- [ ] 10 条验收条件全部通过
- [ ] 全量 pytest 无回归（预期 592 + ~12 新测试）
- [ ] ruff / mypy 全绿
- [ ] 5 个真实风格 fixture（含中文 AI 资讯 + 干扰项）
- [ ] `codex/reviews/P50-REVIEW.md` 填写完毕

---

## 八、风险与取舍

1. **真实 LLM 跑的非确定性**：策展人 LLM 每次返回可能略不同（temperature>0），同一 fixture 多次跑 precision 可能波动。回归检测阈值 0.10 容忍正常波动；CI 跑用 FakeProvider 测逻辑，真实 LLM 跑是手动/定期。
2. **fixture 标注的主观性**：expected_selected/rejected 是人工标注，标注者判断会影响"正确"定义。5 个 fixture 是最小可行集，后续可扩充。
3. **不接线 CuratorJudge**：按用户决策，CuratorJudge（LLM-as-judge 主观打分）留作 Layer 2。本包的 precision/recall 有 ground truth，比主观打分更可靠。
4. **CURATE_PROMPT 复用**：harness 直接 `from prompts import CURATE_PROMPT`，不改 prompt。`_curate_item_dict` 投影逻辑复刻在 curation_benchmark.py（避免 import 整个 daily_digest 模块拉入 pipeline 依赖）。
5. **target_count 影响**：真实策展人受 target_count（默认 12）影响选多少篇。precision 对此不敏感（看选中质量），recall 敏感（选少了 recall 降）。fixture 的 expected_selected 数量应贴近 target_count。
6. **不改现有 P21 框架**：`curation_*` 模块与 `dataset.py`/`evaluator.py`/`benchmark.py` 并列，互不依赖。现有 `eval` 命令零改动。

---

## 九、文件清单

```
src/multiscribe_agent/eval/curation_dataset.py             [新增: T1]
src/multiscribe_agent/eval/curation_scorer.py              [新增: T2]
src/multiscribe_agent/eval/curation_benchmark.py           [新增: T3]
src/multiscribe_agent/cli.py                               [修改: T4]
data/eval/datasets/curation_recall.yaml                    [新增: T1]
tests/eval/fixtures/cr_001.json                            [新增: T1]
tests/eval/fixtures/cr_002.json                            [新增: T1]
tests/eval/fixtures/cr_003.json                            [新增: T1]
tests/eval/fixtures/cr_004.json                            [新增: T1]
tests/eval/fixtures/cr_005.json                            [新增: T1]
tests/eval/test_curation_scorer.py                         [新增: T2]
tests/eval/test_curation_dataset.py                        [新增: T1]
tests/eval/test_curation_benchmark.py                      [新增: T3/T4]
docs/phases/P50-策展PrecisionRecall回归测试.md              [本任务包文档]
```