# Performance Metric Spec

Every target skill must emit structured performance telemetry so the optimizer
can measure baseline efficiency and quantify the impact of any proposed change.

---

## Required Metric Names

| Metric | Type | Unit | Description |
|---|---|---|---|
| `input_tokens` | integer | tokens | Tokens in the prompt sent to the model (system + messages) |
| `output_tokens` | integer | tokens | Tokens in the model's response |
| `total_tokens` | integer | tokens | `input_tokens + output_tokens` |
| `turns` | integer | count | Number of user messages in the interaction |
| `latency_ms` | float | milliseconds | Wall-clock time from request start to last byte received |
| `estimated_cost_usd` | float | USD | Estimated dollar cost using published per-token rates |

For routed calls, two additional metrics are required:

| Metric | Type | Unit | Description |
|---|---|---|---|
| `routing_tokens` | integer | tokens | Tokens consumed by the routing/classification call |
| `routing_latency_ms` | float | milliseconds | Latency of the routing call (overhead) |

---

## Event / Log Granularity

Emit one log record per **call event**, not per session. Five event types are defined:

| Event | When to emit |
|---|---|
| `eval` | Single-turn skill execution (baseline measurement) |
| `eval_multiturn` | Multi-turn conversation (aggregated across all turns) |
| `optimize` | Optimizer strategy run against a skill |
| `routed` | Hierarchical routing classification + execution |
| `session_summary` | Once per session after all per-skill runs complete |

---

## Field Schema (JSONL)

All records share a **common envelope**:

```jsonc
{
  "ts":         "<ISO-8601 UTC, ms precision>",   // e.g. "2026-03-14T10:31:05.412Z"
  "session_id": "<UUID4>",                        // shared across one run session
  "event":      "<eval|eval_multiturn|optimize|routed|session_summary>",
  "skill_name": "<stem of skill file>",           // e.g. "example_skill"
  "skill_path": "<relative path to .md file>"    // e.g. "skills/example_skill.md"
}
```

### `eval` — single-turn

```jsonc
{
  // ...envelope...
  "query":   "<user message string>",
  "model":   "<model ID>",
  "metrics": {
    "input_tokens":        452,
    "output_tokens":       118,
    "total_tokens":        570,
    "turns":               1,
    "latency_ms":          423.1,
    "estimated_cost_usd":  0.00083300
  }
}
```

### `eval_multiturn` — multi-turn (aggregated)

```jsonc
{
  // ...envelope...
  "query":   ["<turn 1>", "<turn 2>", "<turn 3>"],
  "model":   "<model ID>",
  "metrics": {
    "input_tokens":        1820,
    "output_tokens":       340,
    "total_tokens":        2160,
    "turns":               3,
    "latency_ms":          1450.7,
    "estimated_cost_usd":  0.00281200
  }
}
```

### `optimize` — optimizer strategy run

```jsonc
{
  // ...envelope...
  "strategy":        "<compress|cache|summarize|route>",
  "optimizer_model": "<model ID>",
  "before": {
    "char_count":     3241,
    "approx_tokens":  810
  },
  "after": {                          // shape varies by strategy (see below)
    "char_count":     980,
    "approx_tokens":  245
  },
  "efficiency": {
    "token_reduction":      565,
    "token_reduction_pct":  69.8,
    "char_reduction_pct":   69.7
  },
  "optimizer_cost": {
    "input_tokens":         892,
    "output_tokens":        310,
    "estimated_cost_usd":   0.00734400
  },
  "explanation_snippet":    "<first 200 chars of optimizer explanation>"
}
```

**`after` shape by strategy:**

- `compress`: `{ char_count, approx_tokens }`
- `cache`: `{ static_char_count, dynamic_char_count, cacheable_token_pct }`
- `summarize`: `{ char_count, approx_tokens }`
- `route`: omit `after`; use `routing_decision` sub-object instead

### `routed` — hierarchical routing + execution

```jsonc
{
  // ...envelope...
  "query": "<user message>",
  "routing": {
    "classifier_model":   "claude-haiku-4-5-20251001",
    "routed_model":       "<model ID>",
    "complexity":         "<simple|moderate|complex>",
    "confidence":         "<high|medium|low>",
    "rationale":          "<one sentence>",
    "routing_tokens":     54,
    "routing_latency_ms": 198.4
  },
  "execution": {
    "model":               "<model ID>",
    "input_tokens":        461,
    "output_tokens":       95,
    "total_tokens":        556,
    "latency_ms":          390.2,
    "estimated_cost_usd":  0.00074800
  },
  "totals": {
    "tokens":              610,
    "latency_ms":          588.6,
    "estimated_cost_usd":  0.00074800
  },
  "vs_always_sonnet": {               // optional; include when sonnet baseline available
    "token_delta":         0,
    "cost_delta_usd":      -0.00037200,
    "cost_savings_pct":    33.2
  }
}
```

### `session_summary` — end-of-session

```jsonc
{
  // ...envelope...
  "baseline": {
    "total_tokens":  570,
    "latency_ms":    423.1,
    "cost_usd":      0.00083300
  },
  "best_result": {
    "strategy":             "compress",
    "total_tokens":         195,
    "latency_ms":           310.0,
    "cost_usd":             0.00029200,
    "token_savings_pct":    65.8,
    "latency_savings_pct":  26.7
  }
}
```

---

## Units and Normalization Rules

- **`latency_ms`**: wall-clock milliseconds, float, rounded to 2 decimal places.
  Do not subtract routing overhead from execution latency — report both separately.
- **`estimated_cost_usd`**: float, 8 decimal places. Computed as:
  `(input_tokens × input_rate + output_tokens × output_rate) / 1_000_000`
  using the rates table below. Covers the execution call only unless noted.
- **`approx_tokens`**: `char_count // 4`. Fast estimate used only in `optimize` events
  where the optimizer itself does not expose token counts for the rewritten text.
- **`token_reduction_pct`**: `(before_approx - after_approx) / before_approx × 100`,
  rounded to 1 decimal place.
- **`cacheable_token_pct`**: `static_chars / (static_chars + dynamic_chars) × 100`.

### Model rate table (per million tokens, as of early 2026)

| Model ID | Input ($/M) | Output ($/M) |
|---|---|---|
| `claude-haiku-4-5-20251001` | 0.80 | 4.00 |
| `claude-sonnet-4-6` | 3.00 | 15.00 |
| `claude-opus-4-6` | 15.00 | 75.00 |

---

## Logging / Storage Expectations

- Format: **newline-delimited JSON** (`.jsonl`), one record per line, append-only.
- Location: `logs/<YYYY-MM-DD>.jsonl` (UTC date).
- One file per calendar day; never overwrite or truncate existing lines.
- Each line must be a valid, self-contained JSON object (no trailing commas,
  no multi-line values).
- `session_id` (UUID4) must be consistent across all records from one execution.

---

## Handling Missing or Partial Measurements

| Situation | Required behavior |
|---|---|
| API call fails | Do not emit a record. Log the error to stderr with the session ID. |
| `usage` field absent from API response | Emit the record with `input_tokens: null, output_tokens: null, total_tokens: null`. |
| Routing call succeeds but execution fails | Emit a `routed` record with `execution: null` and include the error message. |
| Latency cannot be measured | Emit `latency_ms: null`; do not omit the field. |
| Cost cannot be computed (unknown model) | Emit `estimated_cost_usd: null` and include `"model_unknown": true`. |
| No logs exist for a skill | The optimizer must propose instrumentation changes before attempting optimization review. |
