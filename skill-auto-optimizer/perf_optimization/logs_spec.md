# Skill Optimizer — Log Format Specification

## Overview

All runs emit **newline-delimited JSON** (`.jsonl`), one record per line, to
`logs/<YYYY-MM-DD>.jsonl`. Every record shares a common envelope; event-specific
fields are nested under typed sub-objects.

---

## File & Naming

```
logs/
├── 2026-03-14.jsonl    # one file per calendar day (UTC)
├── 2026-03-15.jsonl
└── ...
```

- Append-only; never overwrite existing lines.
- Each line is a valid, self-contained JSON object (no trailing commas, no
  multi-line values).

---

## Common Envelope (every record)

| Field        | Type   | Required | Description                                      |
|--------------|--------|----------|--------------------------------------------------|
| `ts`         | string | ✅        | ISO-8601 UTC timestamp, ms precision             |
| `session_id` | string | ✅        | UUID4, shared across all events in one `run_samples` execution |
| `event`      | string | ✅        | One of: `eval`, `eval_multiturn`, `optimize`, `routed` |
| `skill_name` | string | ✅        | Stem of the skill file, e.g. `"example_skill"`   |
| `skill_path` | string | ✅        | Relative path to the source `.md` file           |
| `query`      | string | ✅ (eval) | The user message(s) used for this run. List for multiturn. |

---

## Event: `eval`  — single-turn baseline

```jsonc
{
  "ts": "2026-03-14T10:31:05.412Z",
  "session_id": "a1b2c3d4-...",
  "event": "eval",
  "skill_name": "example_skill",
  "skill_path": "skills/example_skill.md",
  "query": "I bought the Pro plan two weeks ago and I want a refund.",
  "model": "claude-haiku-4-5-20251001",
  "metrics": {
    "input_tokens": 452,
    "output_tokens": 118,
    "total_tokens": 570,
    "turns": 1,
    "latency_ms": 423.1,
    "estimated_cost_usd": 0.000833
  }
}
```

---

## Event: `eval_multiturn`  — multi-turn baseline

```jsonc
{
  "ts": "2026-03-14T10:31:09.800Z",
  "session_id": "a1b2c3d4-...",
  "event": "eval_multiturn",
  "skill_name": "example_skill",
  "skill_path": "skills/example_skill.md",
  "query": [
    "I want a refund.",
    "My email is jane@example.com. I bought it 10 days ago.",
    "The reason is the product didn't work as advertised."
  ],
  "model": "claude-haiku-4-5-20251001",
  "metrics": {
    "input_tokens": 1820,
    "output_tokens": 340,
    "total_tokens": 2160,
    "turns": 3,
    "latency_ms": 1450.7,
    "estimated_cost_usd": 0.002812
  }
}
```

---

## Event: `optimize`  — optimizer strategy run

```jsonc
{
  "ts": "2026-03-14T10:31:22.100Z",
  "session_id": "a1b2c3d4-...",
  "event": "optimize",
  "skill_name": "example_skill",
  "skill_path": "skills/example_skill.md",
  "strategy": "compress",
  "optimizer_model": "claude-sonnet-4-6",
  "before": {
    "char_count": 3241,
    "approx_tokens": 810
  },
  "after": {
    "char_count": 980,
    "approx_tokens": 245
  },
  "efficiency": {
    "token_reduction": 565,
    "token_reduction_pct": 69.8,
    "char_reduction_pct": 69.7
  },
  "optimizer_cost": {
    "input_tokens": 892,
    "output_tokens": 310,
    "estimated_cost_usd": 0.007344
  },
  "explanation_snippet": "Replaced all prose with bullet points; removed repeated ..."
}
```

```jsonc
{
  "ts": "2026-03-14T10:31:35.200Z",
  "session_id": "a1b2c3d4-...",
  "event": "optimize",
  "skill_name": "example_skill",
  "skill_path": "skills/example_skill.md",
  "strategy": "cache",
  "optimizer_model": "claude-sonnet-4-6",
  "before": {
    "char_count": 3241,
    "approx_tokens": 810
  },
  "after": {
    "static_char_count": 2900,
    "dynamic_char_count": 180,
    "cacheable_token_pct": 89.5
  },
  "efficiency": {
    "cache_hit_savings_pct": 90.0,
    "note": "Savings apply from 2nd call onward at ~10% cost on static block"
  },
  "optimizer_cost": {
    "input_tokens": 912,
    "output_tokens": 295,
    "estimated_cost_usd": 0.007146
  },
  "explanation_snippet": "Static block: all policies, allowed/disallowed actions ..."
}
```

---

## Event: `routed`  — hierarchical routing + execution

```jsonc
{
  "ts": "2026-03-14T10:31:48.900Z",
  "session_id": "a1b2c3d4-...",
  "event": "routed",
  "skill_name": "example_skill",
  "skill_path": "skills/example_skill.md",
  "query": "What are your pricing plans?",
  "routing": {
    "classifier_model": "claude-haiku-4-5-20251001",
    "routed_model": "claude-haiku-4-5-20251001",
    "complexity": "simple",
    "confidence": "high",
    "rationale": "Factual lookup with no judgement required.",
    "routing_tokens": 54,
    "routing_latency_ms": 198.4
  },
  "execution": {
    "model": "claude-haiku-4-5-20251001",
    "input_tokens": 461,
    "output_tokens": 95,
    "total_tokens": 556,
    "latency_ms": 390.2,
    "estimated_cost_usd": 0.000748
  },
  "totals": {
    "tokens": 610,
    "latency_ms": 588.6,
    "estimated_cost_usd": 0.000748
  },
  "vs_always_sonnet": {
    "token_delta": 0,
    "cost_delta_usd": -0.000372,
    "cost_savings_pct": 33.2
  }
}
```

---

## Efficiency Delta Record (optional, end-of-session summary)

Written once per session after all runs complete.

```jsonc
{
  "ts": "2026-03-14T10:32:10.000Z",
  "session_id": "a1b2c3d4-...",
  "event": "session_summary",
  "skill_name": "example_skill",
  "baseline": {
    "total_tokens": 570,
    "latency_ms": 423.1,
    "cost_usd": 0.000833
  },
  "best_result": {
    "strategy": "compress",
    "total_tokens": 195,
    "latency_ms": 310.0,
    "cost_usd": 0.000292,
    "token_savings_pct": 65.8,
    "latency_savings_pct": 26.7
  }
}
```

---

## Field Glossary

| Field | Unit | Notes |
|---|---|---|
| `latency_ms` | milliseconds | Wall-clock from request start to last byte received |
| `estimated_cost_usd` | USD | Execution call only; excludes optimizer overhead unless noted |
| `approx_tokens` | tokens | `char_count / 4` — fast estimate, not from API |
| `token_reduction_pct` | % | `(before - after) / before * 100` |
| `cache_hit_savings_pct` | % | Estimated savings assuming 100% cache hit on static block |
| `turns` | integer | Number of user messages in the conversation |
