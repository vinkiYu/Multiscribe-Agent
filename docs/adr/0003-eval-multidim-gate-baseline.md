# ADR-0003 评测基线多维门禁:阈值与"只升不降"语义

- 状态:已采纳
- 日期:2026-08-14(P64.1),2026-09-22 补录
- 关联:`eval/curation_benchmark.py::_check_and_write_baseline`、`eval/metrics_schema.py`、`eval/ledger.py`、P64 系列任务包

## 背景

策展评测(P57)最初只有单一 F1 门禁:新跑分比基线跌超阈值即 `RegressionDetected`。P64 引入四层指标(结果/过程/效率/安全)后,单维门禁无法覆盖 token 暴涨、安全违规等退化。P57 Phase 7 曾靠 F1 门禁拦下一次错误标签(cap=2,F1 跌至 0.626),证明门禁价值,但阈值选取与多维语义需要定案。

## 决策

1. **多维 delta 门禁**:质量维度(F1/precision/recall/step_success)按相对降幅,阈值 0.05;成本维度(tokens/p95)按相对涨幅,阈值 0.20;另设绝对上限(max_tokens_per_sample=9000,max_p95_latency_ms=30000,来源:2026-08-14 gpt-5.4 压测 +20% 余量);阶段目标门(phase_f1≥0.80)在 promotion 期开启。
2. **拒绝即审计**:违规先写 `data/eval/ledgers/rejected_runs.jsonl`(含全部维度数值与违规维度),再抛 `RegressionDetected`;基线文件字节不动、不归档被拒 run。
3. **基线只升不降**:覆盖前自动快照(时间戳 json),趋势表只统计通过门禁的 run。
4. **安全层灰度**:SafetyGate(P64.1)只计数不阻断,违规候选逐条记录 id;升硬阻断需先攒误报率数据,另行决策。

## 被否方案

- 放宽阈值让漂移 run 通过(P64.2 中转 gpt-5.4 质量漂移期曾四次诱惑)— 否决:会掩盖真实回归,正确解法是 ledger 记录 + 换稳定窗口/多模型重跑。
- 只测 F1 — 否决:过程/效率/安全维度失控风险已在 P64.1 设计文档论证。

## 后果

- 实证战绩:拦截 P57 Phase 7 错误标签、P64.2 四次供应商漂移、P64.3 两次 phase_f1 未达标,零次带病覆盖。
- 已知边界:单次跑分随机波动 ±0.03,故质量阈值不能低于 0.05;多维相对门在并行下必须用 per-sample 聚合(全局 offset 切片会串扰,P64.2 已修复并单测锁定)。
