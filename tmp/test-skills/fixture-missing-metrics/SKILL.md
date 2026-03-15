```markdown
---
name: data-summarizer
description: Grounded summary of structured data with cited metrics.
---

<!-- cache_control: ephemeral -->

# Data Summarizer

Trigger: user requests summary of structured data, reports, or lists.

## Instructions

- Parse input as given; no external files unless user provides a path.
- Compute totals, averages, top items, outliers, trends.
- **Ground every number**: cite inputs (e.g., "Total: $7.5M = $1.2M + $1.8M + $2.1M + $2.4M").
- If budget/target given, compute variance (absolute + %).
- Flag missing/ambiguous data; never invent figures.
- List top 3 items by value; note outliers.
- Trends: period-over-period with deltas.
- Match expected precision; use standard arithmetic; no over-elaboration.
- **Target 100–150 words.** Omit sections adding no new info.
- Do **not** list every per-period delta individually; summarize with average growth rate and note only the most notable period change.

## Output Schema

```
Summary for: <topic>
Period: <range>

Key Metrics:
- Total: <value> [= <cited addends>]
- Average: <value> [= <total> ÷ <n>]
- Budget Variance: <+/- value> (<% over/under>) [if provided]
- Top Item: <name> (<value>, <% of total>)

Trends:
- <direction>: avg <delta> per period (~<avg %>); notable: <single most notable shift>

Highlights:
- <bullet 1>
- <bullet 2>

Recommendations:
- <1–2 sentences; omit if none warranted>
```

Output "N/A — not provided" for any section lacking input data.

## Quality Guardrails

- Every numeric claim must trace to input (citation target ≥ 0.50).
- No extrapolation, hallucination, or unstated rounding.
- Preserve edge cases: zero values, negative growth, missing periods.
- Keep concise; prefer an average over repeating each period's delta.

## Instrumentation

Emit per run:
- **Perf**: `input_tokens`, `output_tokens`, `total_tokens`, `turns`, `latency_ms`, `estimated_cost_usd`
- **Quality**: `citation_count`, `grounding_references`, `tool_call_count`, `hallucination_flags`
- **Log**: `logs/<YYYY-MM-DD>.jsonl` — one JSON record per eval with all above fields plus `quality_pass` (bool), `judge_overall` (int).
```