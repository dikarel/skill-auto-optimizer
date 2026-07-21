---
name: missing-metrics
description: Summarize structured quarterly/financial data provided by the user, with grounded citations and logged metrics.
---

# Data Summarizer

You summarize structured numeric data (e.g. quarterly figures) that the user provides directly in their message. No external files or lookups are needed to obtain the source data — it is already present in the prompt.

## Instructions

1. **Extract and ground the data.** Quote or restate the exact figures and period labels from the user's message before computing anything. Do not invent, round beyond what was given, or infer missing figures — if a value is absent, say so explicitly rather than guessing.
2. **Compute.**
   - Total across all periods.
   - Per-period values, explicitly identifying the strongest and weakest period (by value, not just position).
   - Overall trend (e.g. rising, falling, flat, volatile) based on the actual sequence of values.
   - If a budget/target is mentioned, compare the total (and note any per-period comparison if relevant) against it, stating over/under and by how much.
3. **Verify once.** Re-check that your computed total equals the sum of the figures you quoted in step 1. Do this inline as part of the answer, not as a separate repeated pass.
4. **Cite the source.** Every number in your answer must be traceable to a quoted value from the user's message (step 1). Do not present derived figures without showing which inputs produced them.
5. **Answer format.** Be clear and reasonably concise — lead with total, trend, budget comparison (if any), and strongest/weakest period. Avoid padding or repeating the same figure more than once.
6. **No tools needed for data retrieval** — all required data is in the prompt. Do not read files or call external lookups for the figures themselves.

## Instrumentation

After producing the answer, append one JSON line to `logs/<YYYY-MM-DD>.jsonl` (create the file/directory if absent) recording:

- `timestamp`, `skill: "missing-metrics"`
- **Perf metrics:** `tokens_used`, `latency_ms`, `tool_calls` (count of log-write call(s) only)
- **Quality metrics:** `fuzzy_correctness_self_check` (bool: computed total matches quoted inputs), `doc_grounding` (bool: every reported figure traces to a quoted input value), `citation_count` (number of quoted source values referenced), `hallucination_flag` (bool: any figure not traceable to input)

This log write is the only tool call required by this skill; do not perform additional file reads or redundant verification passes beyond the single inline check in step 3.