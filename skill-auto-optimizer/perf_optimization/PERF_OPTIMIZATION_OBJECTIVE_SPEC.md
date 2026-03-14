# Performance Optimization Objective Spec

This document defines the optimization objectives the auto-optimizer uses when
reviewing a skill's recent performance metrics and proposing changes.

---

## Target Performance Outcomes

The optimizer pursues three primary outcomes, measured against the skill's
**single-turn baseline** (`eval` event, default model):

| Outcome | Target | Measurement |
|---|---|---|
| **Token reduction** | ≥ 30% reduction in `total_tokens` | `(baseline - optimized) / baseline` |
| **Latency reduction** | ≥ 15% reduction in `latency_ms` | Wall-clock, end-to-end |
| **Cost reduction** | ≥ 20% reduction in `estimated_cost_usd` | Execution call only |

A skill is considered **optimized** when it meets at least two of the three targets.

---

## Priority Order for Trade-offs

When strategies conflict or cannot all be applied, prioritize in this order:

1. **Token reduction** — directly reduces both cost and latency; highest leverage.
2. **Cost reduction** — lower cost per call compounds across high-volume skills.
3. **Latency reduction** — important for interactive use; deprioritized for batch skills.

A latency regression of up to **10%** is acceptable if token reduction exceeds **40%**.
A cost increase of up to **5%** is acceptable if it eliminates turns (reduces multi-turn
interactions to single-turn).

---

## Optimization Strategies

Four strategies are available. The optimizer selects strategies based on skill
characteristics and observed metrics (see Decision Rules below).

### 1. Compress — Tool Schema Compression

**What it does:** Rewrites verbose prose instructions into compact, token-efficient
markdown (bullet points, abbreviations, removal of filler) without losing any
operational information.

**When to apply:**
- Skill system prompt exceeds 400 tokens
- `input_tokens` account for > 70% of `total_tokens` in baseline
- Skill contains long prose paragraphs with repeated or redundant phrasing

**Expected impact:**
- Token reduction: 40–70% on the system prompt
- Latency reduction: proportional to token reduction
- Risk: low — content-preserving rewrite

**Verification:** Re-run `eval` on the compressed skill and confirm:
- `total_tokens` decreased by ≥ 30%
- Response quality is not degraded (spot-check 3–5 queries)

---

### 2. Cache — Prompt Caching Preparation

**What it does:** Splits the skill into a **static block** (policies, tool descriptions,
constraints — never changes) and a **dynamic template** (per-request context with
`{{PLACEHOLDERS}}`). Adds `cache_control: {"type": "ephemeral"}` to the static block
for Anthropic's prompt caching API.

**When to apply:**
- Skill is called repeatedly with the same system prompt
- Static content accounts for > 60% of total prompt characters
- `input_tokens` are high and the skill is used at volume (> 100 calls/day)

**Expected impact:**
- Token cost on static block: ~10% of normal on 2nd+ call (90% discount)
- No latency improvement on first call; significant on subsequent calls
- Risk: low — structural change only, no content modification

**Verification:**
- Make two identical API calls using the `cache_control` structure
- Confirm `cache_read_input_tokens > 0` on the second call in the API response

---

### 3. Summarize — Context Summarization Pipeline

**What it does:** Inserts a lightweight pre-processing step before multi-turn calls.
A small model compresses the existing conversation history into a minimal bullet-point
summary, which replaces the raw history in subsequent turns.

**When to apply:**
- Skill is used in multi-turn conversations (> 2 turns average)
- `eval_multiturn` logs show `input_tokens` growing linearly with turns
- History contains resolved sub-tasks, pleasantries, or repeated context

**Expected impact:**
- Token reduction per turn: 50–80% on history portion after turn 3
- Slight latency overhead on the summary call (~100–200 ms)
- Risk: medium — information loss possible; always verify key facts are preserved

**Verification:**
- Run the summarized history through the skill and confirm no loss of critical
  context (account details, decisions made, open questions)

---

### 4. Route — Hierarchical Routing

**What it does:** Adds a cheap classification step (Haiku) before the main model
call. Classifies query complexity as `simple`, `moderate`, or `complex` and
dispatches to the appropriate model tier:

| Complexity | Model | Use when |
|---|---|---|
| `simple` | `claude-haiku-4-5-20251001` | Factual lookups, rule-based tasks, form filling |
| `moderate` | `claude-sonnet-4-6` | Multi-step reasoning, nuanced judgement |
| `complex` | `claude-opus-4-6` | Ambiguous edge cases, high-stakes decisions, legal/security |

**When to apply:**
- Skill handles a wide range of query types (not all require the same model)
- Baseline is run on Sonnet or Opus but many queries are simple
- `routed` logs show ≥ 40% of queries classified as `simple`

**Expected impact:**
- Cost reduction: 60–90% on simple queries routed to Haiku vs. Sonnet
- Routing overhead: ~50 tokens + 150–250 ms per call
- Risk: low-medium — occasional mis-classification; use `confidence: high` filter

**Verification:**
- Run routing against 10+ representative queries; confirm classification accuracy
- Check that `simple` queries produce correct responses on Haiku

---

## Decision Rules for Proposing Strategies

```
IF skill_prompt_tokens > 400:
    → always propose "compress" first

IF skill is called > 100 times/day AND static_content_pct > 60%:
    → propose "cache"

IF avg_turns > 2 AND multiturn_token_growth_rate > 1.5x per turn:
    → propose "summarize"

IF skill handles mixed query complexity AND baseline_model IN (sonnet, opus):
    → propose "route"

IF all metrics are already within targets:
    → propose no changes; document that skill is already optimized
```

Strategies can be combined. Recommended combinations:

| Scenario | Strategies |
|---|---|
| Verbose high-volume skill | compress + cache |
| Support/chat skill with long sessions | compress + summarize |
| General-purpose skill on expensive model | route (+ compress if verbose) |
| All of the above | compress → cache → route (apply in this order) |

---

## Acceptable Regressions

| Metric | Max acceptable regression | Condition |
|---|---|---|
| `latency_ms` | +10% | Only if `total_tokens` drops ≥ 40% |
| `estimated_cost_usd` | +5% | Only if `turns` is reduced |
| `output_tokens` | +15% | Acceptable if response quality improves |
| `total_tokens` | 0% regression | Never allow a strategy to increase total tokens |

---

## Optimization Heuristics

- **Compress before cache.** A smaller static block means the cache covers a higher
  fraction of total tokens at lower absolute cost.
- **Route before summarize.** If simple queries are routed to Haiku, they rarely
  need multi-turn summarization.
- **Never apply `summarize` without a content check.** Information loss in summaries
  is silent and can cause incorrect agent behavior.
- **Routing overhead breaks even at ~3 Haiku calls avoided per Sonnet call.**
  Only recommend routing if the traffic pattern justifies it.
- **Use `approx_tokens` (char_count / 4) only for pre-optimization sizing.**
  Always use API `usage` field for post-optimization verification.
