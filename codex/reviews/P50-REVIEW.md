# P50 Review: 策展 Precision/Recall 回归测试

## 结论

阶段实现完成，建议通过。P50 新增了带人工 ground truth 的策展评测链路，使用与每日策展相同的 `CURATE_PROMPT` 和 provider 接口，独立计算 Precision、Recall、F1，并支持 Markdown 报告与 baseline 回归门禁。没有接入 `CuratorJudge`，也没有修改现有 P21 评测框架或每日推送 pipeline。

## 变更范围

- `src/multiscribe_agent/eval/curation_dataset.py`
  - 增加 `CurationCandidate`、`CurationSample`、`CurationDataset`。
  - 支持 YAML 数据集元数据和 JSON fixture 引用加载。
  - 校验候选 ID 唯一、selected/rejected 不重叠、标签必须属于候选池。
- `src/multiscribe_agent/eval/curation_scorer.py`
  - 增加确定性的 `CurationScore` 与 `score_curation`。
  - 计算 Precision、Recall、F1；覆盖空选集和空期望集边界。
- `src/multiscribe_agent/eval/curation_benchmark.py`
  - 增加轻量 LLM harness `run_curation`，投影候选字段、调用现有 `CURATE_PROMPT`、解析模型 JSON 数组并提取 ID。
  - 增加 `run_curation_benchmark`，逐样本评分、生成 Markdown 报告、写入 baseline，并在平均 F1 下降超过阈值时抛出 `RegressionDetected`。
- `src/multiscribe_agent/cli.py`
  - 增加并列命令 `eval-curation`，支持数据集、报告目录、baseline、目标数量和回归阈值参数。
- `data/eval/datasets/curation_recall.yaml`
  - 增加 5 个标注样本入口。
- `tests/eval/fixtures/cr_001.json` 至 `cr_005.json`
  - 增加 5 组中文 AI 资讯与非 AI 干扰项混合候选池，每组 10 条候选并带 expected labels。
- `tests/eval/test_curation_dataset.py`
- `tests/eval/test_curation_scorer.py`
- `tests/eval/test_curation_benchmark.py`
  - 覆盖数据集、标签校验、指标边界、FakeProvider harness、报告、回归检测和 CLI help。

## 验收证据

| # | 验收条件 | 证据 |
|---|---|---|
| 1 | YAML 加载数据集，候选字段兼容 UnifiedData 投影 | `tests/eval/test_curation_dataset.py::test_load_curation_dataset` |
| 2 | selected/rejected 重叠时拒绝 | `tests/eval/test_curation_dataset.py::test_overlapping_labels_rejected` |
| 3 | Precision 为 TP/(selected) 且空 selected 为 0 | `tests/eval/test_curation_scorer.py::test_precision`、`test_empty_selection_and_expected_boundaries` |
| 4 | Recall 为 TP/(expected) 且空 expected 为 1 | `tests/eval/test_curation_scorer.py::test_recall`、`test_empty_selection_and_expected_boundaries` |
| 5 | F1 为调和平均，完全匹配为 1 | `tests/eval/test_curation_scorer.py::test_f1_perfect_match` |
| 6 | harness 返回 provider 策展结果中的 ID 集合，并投影候选到 prompt | `tests/eval/test_curation_benchmark.py::test_run_curation_extracts_selected_ids` |
| 7 | benchmark 逐样本写报告并检测 F1 回归 | `tests/eval/test_curation_benchmark.py::test_benchmark_detects_regression` |
| 8 | `eval-curation` 命令可发现、参数可见 | `tests/eval/test_curation_benchmark.py::test_eval_curation_help_is_available` |
| 9 | 既有 `eval` 命令和 P21 测试无回归 | `tests/eval/` 中既有 benchmark、dataset、evaluator、feedback_loop 测试均通过 |
| 10 | 全量测试及质量门禁通过 | 见下方测试记录 |

## 测试记录

```text
pytest tests/eval/ -v -p no:cacheprovider --basetemp .pytest-tmp-p50
27 passed

HF_HUB_OFFLINE=1 pytest -q -p no:cacheprovider --basetemp .pytest-tmp-p50-full
602 passed, 6 deselected, 1 warning

python -m ruff check src tests
All checks passed

python -m ruff format --check src tests
359 files already formatted

python -m mypy src
Success: no issues found in 185 source files
```

## 风险与边界

1. 本次自动化测试使用 `FakeProvider`，没有消耗真实 API，也没有验证某个具体模型在真实网络环境下的输出稳定性；真实运行需配置 provider API key 后执行 `multiscribe-agent eval-curation --dataset curation-recall`。
2. `expected_selected_ids` 是人工标注，当前只有 5 组 fixture；它能提供可重复回归信号，但不能替代更大规模标注集或线上行为指标。
3. 默认 baseline 阈值为平均 F1 下降 `0.10`，`target_count` 默认 12；真实评测时应保持数据集版本、模型和参数可追踪。
4. 模型输出必须包含 JSON 对象数组且每项有非空 `id`；无法解析时 benchmark 明确失败，不会静默当作空选择。
5. 数据目录受仓库 `.gitignore` 的通用 `data/` 规则影响，`curation_recall.yaml` 需要在提交时显式 force-add，确保任务白名单中的标注入口被纳入版本控制。

## 未做事项

- 未接入 `CuratorJudge`（按 P50 决策留给后续 Layer 2）。
- 未修改 `daily_digest.py`、`prompts.py`、P21 的 `dataset.py/evaluator.py/benchmark.py` 或现有工作流执行器。
- 未推送 GitHub。
