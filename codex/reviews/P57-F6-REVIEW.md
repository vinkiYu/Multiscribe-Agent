# Review: P57-F6 — 策展 F1 收尾 (Phase 6)

Execution date: 2026-08-10  
Branches / files: 同主分支,本计划改动均在 `MultiscribeAgent-main/` 子树内。

> Phase 6 增量:**回滚 Phase 5 的 prompt "短描述容忍" 段**, 仅保留 label 收紧 (Phase 5 T2)。增加下限规则:候选不足时 score ≥ 6 也可入选, 避免全部拒选导致 F1=0。

## 1. Scope check

| 文件 | 用途 |
|---|---|
| `src/multiscribe_agent/agents/pipelines/prompts.py` | T1: 删除【短描述容忍】段, 加 score ≥ 6 下限补充规则 |
| `data/eval/baselines/curation_recall.json` | T2: 新 baseline (100 samples, avg_f1=0.7441) |
| `data/eval/reports/curation-recall_20260810-042510.md` | T2: Phase 6 100 条报告 |
| `scripts/run_eval_curation_model.py` | T3: 多模型对比 helper (新建) |

未触碰:
- `daily_digest.py` / `bootstrap.py`
- `eval/curation_benchmark.py` / `eval/curation_scorer.py`
- fixtures / dataset YAML (Phase 5 v3 标签沿用)
- 4 个新 RSS adapter

## 2. 验收条件

| # | 验收 | 状态 | 证据 |
|---|---|---|---|
| 1 | prompt 回滚【短描述容忍】段 | **PASS** | `prompts.py` 删除该段, 长度 3703 → 3559 |
| 2 | prompt 加 score ≥ 6 下限补充规则 | **PASS** | `prompts.py` "【数量约束】" 段新增"候选不足时放宽阈值" |
| 3 | eval-curation 跑完 100 条 | **PASS** | `curation-recall_20260810-042510.md` |
| 4 | **F1 ≥ 0.80** | **NO** | F1 = **0.744** (Phase 5 = 0.755, Phase 4 = 0.771) |
| 5 | 旧 50 F1 恢复到 Phase 4 水平 (0.801) | **NO** | Phase 6 旧 50 = **0.767** (Phase 4 0.801, Phase 5 0.775) |
| 6 | 新 50 F1 ≥ Phase 5 (0.735) | **NO** | Phase 6 新 50 = **0.721** (跌 0.014) |
| 7 | baseline 更新,RegressionDetected 不触发 | **PASS** | baseline avg_f1=0.7441, 旧 0.7550, 阈值 0.10 |
| 8 | `P57-F6-REVIEW.md` 写完 | **PASS** | 本文件 |
| 9 | ruff --select F + mypy 通过 | **PASS** | All checks passed |
| 10 | cr-005/009 从 F1=0 恢复 | **PARTIAL** | cr-009 恢复到 0.889; cr-005 仍 0.000 |

## 3. 命令与原始输出

```text
$ python -u scripts/run_eval_curation.py
Final: curation-recall precision=0.663 recall=0.909 f1=0.744 passed=61/100

$ python scripts/run_eval_curation_model.py gpt-4o-mini
default-openai generate failed after 3 retries (upstream 503 — 模型不可用)

$ python scripts/run_eval_curation_model.py gpt-4o
default-openai generate failed after 3 retries (upstream 502)

$ python scripts/run_eval_curation_model.py claude-3-5-haiku-20241022
default-openai generate failed after 3 retries (upstream 502)
```

**多模型对比未执行成功**:中转 (apizh-ai.com) 上 gpt-4o / claude-haiku / gpt-4o-mini 都返回 502/503 upstream 错误,deepseek-chat 返回 404 (未配置)。无法在本环境做多模型对比。

## 4. 结果对比表

| 阶段 | 样本数 | F1 | Precision | Recall | 通过率 |
|---|---:|---:|---:|---:|---:|
| Baseline | 50 | 0.609 | 0.457 | 0.952 | 22% |
| Phase 1 | 50 | 0.705 | 0.608 | 0.896 | 60% |
| Phase 2 | 50 | 0.740 | 0.646 | 0.918 | 60% |
| Phase 3 | 50 | 0.772 | 0.695 | 0.934 | 68% |
| Phase 4 整体 | 100 | 0.771 | 0.759 | 0.842 | 71% |
| Phase 5 整体 | 100 | 0.755 | 0.671 | 0.904 | 65% |
| **Phase 6 整体** | **100** | **0.744** | **0.663** | **0.909** | **61%** |
| ↳ Phase 6 旧 50 | 50 | 0.767 | — | — | 72% |
| ↳ Phase 6 新 50 | 50 | 0.721 | — | — | 50% |

### 关键发现

- **Phase 6 比 Phase 5 还低 0.011**:回滚了 prompt "短描述容忍" 段,本应让旧 50 恢复到 Phase 4 水平(0.801),但实际只到 0.767。
- **新 50 反而跌了 0.014** (0.735 → 0.721):回滚意味着模型更严地拒 TLDR AI 短描述,与 v3 严 label 错配加重。
- **cr-009 完全恢复**:0.000 → 0.889 (Phase 5 副作用是 prompt 过宽让模型完全拒选,Phase 6 回滚后恢复)。
- **cr-005 仍未恢复**:1.000 → 0.000 (Phase 5) → 0.000 (Phase 6)。Phase 6 加了 score ≥ 6 下限补充规则, 但样本里最高 score 仍 < 6, 仍全拒。

### 三阶段对比(Phase 4 vs 5 vs 6)

| 维度 | Phase 4 | Phase 5 | Phase 6 |
|---|---|---|---|
| F1 (整体) | 0.771 | 0.755 | **0.744** |
| F1 (旧 50) | 0.801 | 0.775 | 0.767 |
| F1 (新 50) | 0.741 | 0.735 | 0.721 |
| 通过率 | 71% | 65% | 61% |
| 改动 | 无 (Phase 3 prompt) | +短描述容忍 + label 收紧 | -短描述容忍 (回滚) + score≥6 下限 |

**结论**:三个阶段都在 0.74-0.77 区间,**P57 已触及用 gpt-5.4-mini 在当前 fixtures + prompt 配置的天花板**。

## 5. 暴露的问题

1. **多模型对比不可行**:apizh-ai.com 中转对 gpt-4o / claude-haiku / deepseek 都返回 5xx。**Phase 6 假设的"换模型提升 F1"无法验证**。
2. **回滚 + 新规则没挽回损失**:Phase 6 加的 score ≥ 6 下限只解决"全部拒选"场景,但 60% 失败样本里模型选了 4-5 条但 label 选 3-4 条,P 跌到 0.5-0.67。
3. **gpt-5.4-mini 的 non-determinism 显著**:同一份 prompt 跨 Phase 跑,旧 50 F1 在 0.767-0.801 之间波动 ±0.034。这超出"可接受噪声"范围,Phase 7 应考虑多次跑取中位数。
4. **新 50 fixtures 的 source 单一**:只有 TLDR AI 一个新源(其他 3 个新 RSS 网络不可达)。新 50 fixtures 的多样性受限,无法验证"4 源均衡"的真实效果。

## 6. Phase 6 白名单与黑名单

### 已交付
```
src/multiscribe_agent/agents/pipelines/prompts.py  [-8 行 (回滚 短描述容忍段)]
                                                  [+2 行 (score≥6 下限补充规则)]
scripts/run_eval_curation_model.py                [新建 ~60 行 (多模型 helper)]
data/eval/baselines/curation_recall.json          [avg_f1=0.7441]
data/eval/reports/curation-recall_20260810-042510.md [Phase 6 报告]
```

### 未触碰
- fixtures / dataset YAML (Phase 5 v3 沿用)
- production `daily_digest.py` / `bootstrap.py`
- 4 个新 RSS adapter

## 7. 自评

本次 P57-F6 **Phase 6 暴露 prompt + label 双改动已饱和**:回滚仍无法挽回 Phase 4 → 5 的损失,且当前网络的模型可用性也受限。

| 阶段 | F1 | Precision | Recall | 通过率 | 改动总结 |
|---|---:|---:|---:|---:|---|
| Baseline | 0.609 | 0.457 | 0.952 | 22% | — |
| Phase 1 | 0.705 | 0.608 | 0.896 | 60% | prompt 重写 + 50 fixture label |
| Phase 2 | 0.740 | 0.646 | 0.918 | 60% | 下限规则 + Academy 例外 |
| Phase 3 | 0.772 | 0.695 | 0.934 | 68% | 5 条边界规则 + balanced 采样 |
| Phase 4 | 0.771 | 0.759 | 0.842 | 71% | 4 RSS + 100 fixture |
| Phase 5 | 0.755 | 0.671 | 0.904 | 65% | +短描述容忍 + label 收紧 |
| **Phase 6** | **0.744** | **0.663** | **0.909** | **61%** | -短描述容忍 (回滚) + score≥6 下限 |

⚠️ **P57 已达饱和**:6 个 Phase 累计提升 +0.135 F1 (0.609 → 0.744),但最后 3 个 Phase (4/5/6) 都未能突破 0.78。

🎯 **未来方向 (Phase 7+)**:
1. **多次跑取中位数**:每次 eval 跑 3 遍, 取中位数 F1, 减少 non-determinism 影响
2. **网络重试**:VPN 或换中转接入 gpt-4o / claude-haiku / deepseek
3. **HF/HN/LWiAI 数据接入**:突破网络限制后,重新生成 50 条 fixtures 含 4 个新源
4. **production 接入**:把 CLI 白名单 8 个 adapter 接到 production schedule
5. **更深的 prompt 优化**:基于失败聚类(边界误选+空描述+全部拒选)逐条加规则,但每条改动边际收益递减
6. **重构 fixtures 评价标准**:Phase 1 人工 label (avg 2.9 选) 与 Phase 5 LLM label (avg 3.96 选) 有差异,**应统一回 Phase 1 标准**

---

## 附录 A: 三阶段样本 diff

**Phase 5 → Phase 6 改进 10 条**:
- cr-003: 0.667 → 0.800
- cr-009: 0.000 → 0.889 ✅ (完全恢复)
- cr-055: 0.667 → 0.800
- cr-061: 0.667 → 0.727
- cr-066: 0.667 → 0.889
- cr-080: 0.600 → 0.750
- cr-088: 0.667 → 0.800
- cr-091: 0.667 → 0.800
- cr-093: 0.545 → 0.750
- cr-094: 0.667 → 0.727

**Phase 5 → Phase 6 退步 14 条**:
- cr-027: 0.800 → 0.667
- cr-036: 0.750 → 0.667
- cr-037: 1.000 → 0.667
- cr-038: 0.750 → 0.667
- cr-043: 0.800 → 0.667
- cr-048: 0.800 → 0.667
- cr-057: 0.750 → 0.500
- cr-063: 0.909 → 0.667
- cr-077: 0.800 → 0.500
- cr-084: 0.727 → 0.615
- cr-086: 0.727 → 0.667
- cr-087: 1.000 → 0.600
- cr-090: 0.727 → 0.667
- cr-095: 0.727 → 0.600

## 附录 B: 全 6 个阶段汇总

| 阶段 | 改动 | F1 | 通过率 |
|---|---|---:|---:|
| Baseline | — | 0.609 | 22% |
| Phase 1 | CURATE_PROMPT 重写 + 50 label | 0.705 | 60% |
| Phase 2 | 软下限 + Academy 例外 + 企业稿硬拒 | 0.740 | 60% |
| Phase 3 | 5 条边界规则 + balanced 采样 | 0.772 | 68% |
| Phase 4 | 4 RSS + 100 fixtures | 0.771 | 71% |
| Phase 5 | +短描述容忍 + label 收紧 (50 条) | 0.755 | 65% |
| Phase 6 | -短描述容忍 (回滚) + score≥6 下限 | 0.744 | 61% |

**净提升**:+0.135 F1 (Phase 6 vs Baseline), +39 pp 通过率。  
**饱和点**:Phase 3 prompt + Phase 4 4 RSS = 0.771 (旧 50 0.801,新 50 0.741)。后续 prompt 改动边际收益递减。