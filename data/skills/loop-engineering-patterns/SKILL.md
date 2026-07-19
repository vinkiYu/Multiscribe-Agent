---
name: loop-engineering-patterns
description: Multi-round self-evaluation strategies and loop exit-condition guidance
bins: ["workflow.loop", "agent.reflection"]
---

# Loop Engineering Patterns

Use loop engineering when an agent step benefits from bounded self-evaluation instead of one-shot generation.

## Exit Priority

1. Prefer `score_threshold` for quality targets. Stop once the score is high enough.
2. Use `convergence_delta` to stop when another round is unlikely to help.
3. Keep `max_rounds` as the hard safety bound.

## Practical Defaults

| Task | max_rounds | score_threshold | convergence_delta |
|---|---:|---:|---:|
| Simple summary | 2 | 7.5 | 0.3 |
| Complex analysis | 4 | 8.5 | 0.5 |
| Multi-step reasoning | 5 | 9.0 | 0.7 |

## Anti-Patterns

- `max_rounds=1` removes the benefit of reflection.
- `score_threshold=10` tends to waste tokens.
- Very small deltas can stop useful refinement too early.

## Evaluation Link

When P21 reports a score below threshold, call `feedback_loop.trigger_refinement()` and prefer a `digest-retry` workflow before escalating to human review.
