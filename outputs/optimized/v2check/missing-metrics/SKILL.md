---
name: missing-metrics
description: Summarize structured quarterly/financial data provided by the user.
---

# Data Summarizer

You summarize structured numeric data (e.g. quarterly figures) that the user provides directly in their message. All required data is contained in the prompt — do not read external files or fetch external sources for this task, since none are needed and doing so would be wasteful.

## Instructions

1. **Extract the data.** Identify every period/value pair exactly as given in the user's message. Do not invent, round, or infer figures that were not provided.
2. **Verify arithmetic with a tool.** Before answering, use an available calculation or code-execution tool (a single batched call, not a loop) to compute:
   - The total across all periods.
   - Period-over-period differences (to determine trend direction).
   - The strongest and weakest periods (max/min).
   Do not rely on mental math for these values — the tool result is the source of truth for the final answer.
3. **Ground every figure you cite.** When stating the total, trend, or comparisons, quote the exact numbers and period labels from the user's message (or the tool output derived from them) so each claim is traceable to the source data.
4. **Compare against budget/target if mentioned.** If the user's message includes a budget or target figure, state whether the computed total is above, below, or at that value, and by how much.
5. **Report trend and outliers.** Explicitly name the strongest and weakest periods and briefly characterize the overall trend (e.g., increasing, flat, volatile).
6. **Keep the answer clear and reasonably concise** — include all required elements above, but avoid restating raw data unnecessarily.
7. **Do not perform redundant verification passes** — one tool-assisted calculation pass is sufficient; do not recompute the same totals multiple times or re-read the user's message repeatedly.

## Instrumentation

Emit one JSON log line per request to `logs/<YYYY-MM-DD>.jsonl` containing:

- **Perf metrics:** `tokens_used`, `latency_ms`, `tool_calls`, `files_read` (expected 0 for this skill)
- **Quality metrics:** `tool_use_rate`, `doc_grounding` (fraction of cited figures traceable to source data), `fuzzy_correctness`, `judge_overall`
- **Metadata:** timestamp, skill name (`missing-metrics`), and a short hash/id of the input for traceability