# Quality Objective Spec

This document defines the optimization objectives used when reviewing a skill's recent quality metrics and deciding how to improve it.

---

## Target Quality Outcomes

The primary goal is for every skill variant to produce answers that are:

1. **Grounded** — the agent retrieves relevant documentation before answering; it does not answer from parametric memory alone.
2. **Correct** — the answer matches the ground truth (fuzzy F1 ≥ 0.60; judge correctness ≥ 6/10).
3. **Cited** — the answer explicitly attributes claims to retrieved sources (citation score ≥ 0.5).
4. **Non-hallucinated** — the answer avoids hedging language and unsupported generalizations (hallucination risk ≤ 0.25).
5. **Complete** — the answer fully addresses the question without important omissions (judge completeness ≥ 6/10).
6. **Concise** — the answer is in the 50–250 word target range; not padded, not truncated.

---

## Priority Order for Trade-offs

When these objectives conflict, resolve them in this order:

1. **Tool use / grounding** — an answer that never searches is disqualified regardless of surface quality. If `tool_use_rate` < 0.90, this is the primary fix target.
2. **Correctness** — an answer that sounds confident but is wrong is worse than an incomplete correct answer.
3. **Hallucination avoidance** — speculative language without retrieved support is a blocking failure.
4. **Citation** — surface-level attribution improves trust and downstream debuggability.
5. **Completeness** — a partial answer from a grounded source is preferable to a complete hallucinated one.
6. **Conciseness** — optimize last; it matters, but only after correctness and grounding are satisfied.

---

## Acceptable Regressions

During optimization, a proposed variant may sacrifice one metric if a higher-priority metric improves meaningfully:

| Can regress | If this improves |
|---|---|
| `answer_length_score` (moderate) | `doc_grounding` or `fuzzy_correctness` |
| `citation_score` (slight) | `hallucination_risk` (significant drop) |
| `latency_seconds` | Any accuracy or grounding metric |
| `judge_conciseness` | `judge_correctness` or `judge_completeness` |

**Never acceptable** to regress `tool_use_rate`, `hallucination_risk`, or `judge_overall` in exchange for a conciseness or latency gain.

---

## Optimization Heuristics

The optimizer (see `app/optimizer/skill_optimizer.py`) applies the following heuristics when selecting and rewriting weak variants:

### Selecting Variants to Optimize
- Rank all variants by `overall_score` on the leaderboard (lower = worse).
- Default: target the bottom 2 variants per optimization round.
- A variant qualifies for optimization if it fails ≥ 2 of the pass-fail thresholds defined in `QUALITY_METRIC_SPEC.md`.

### Diagnosing the Root Cause
Use the following signal → diagnosis → fix mapping:

| Observed signal | Likely root cause | Suggested fix |
|---|---|---|
| `tool_use_rate` < 0.90 | Skill does not strongly instruct the agent to search | Add explicit "always search before answering" instruction; add examples showing tool use |
| `hallucination_risk` > 0.25 | Skill permits answering without retrieval; vague language tolerated | Add hard constraint: "Do not answer without retrieved evidence"; remove permissive phrasing |
| `doc_grounding` < 0.60 | Agent searches but retrieves wrong docs | Improve query-construction guidance; instruct agent to refine queries if initial results are poor |
| `citation_score` < 0.50 | Agent uses docs but doesn't cite them | Add instruction to cite the source doc name or section in every answer |
| `fuzzy_correctness` < 0.60 and `judge_correctness` < 6 | Answer is off-topic or misses key facts | Provide answer format guidance; show worked examples with ground-truth-aligned phrasing |
| `judge_completeness` < 6 | Answer truncates or misses sub-questions | Instruct agent to re-read the question and verify all parts are addressed before responding |
| `answer_length_score` < 0.8 | Answers are too short or too long | Add explicit word-range guidance (e.g., "respond in 50–250 words") |

### Incorporating Pairwise Feedback
- When a variant has pairwise losses, extract the `judge_reason` field from each loss.
- Common loss reasons should be reflected as targeted instructions or constraints in the rewritten skill.
- Prefer the structure and phrasing of the top-ranked (highest `overall_score`) variant as a reference when rewriting weak variants.

### Reference to the Best Variant
- Always include the current best variant's content in the optimizer prompt.
- The rewritten skill should adopt structural patterns from the best variant (e.g., if the best variant uses numbered steps, the improved variant should too).
- Do not wholesale copy the best variant — preserve the original variant's intent and scope.

---

## Decision Rules for Proposing Changes

The optimizer may propose the following types of changes to a skill:

### Prompt Changes
**Trigger:** `tool_use_rate` < 0.90 OR `hallucination_risk` > 0.25 OR repeated failure on the same question category.

**Actions:**
- Reword or strengthen mandatory search instruction.
- Add or sharpen "do not answer from memory" constraint.
- Add explicit citation format requirements.

### Workflow Changes
**Trigger:** `doc_grounding` < 0.60 OR `num_tool_calls` avg < 1.5 on multi-hop questions.

**Actions:**
- Add step-by-step search-then-reason workflow.
- Instruct agent to issue a follow-up search if the first result is insufficient.
- Specify query formulation guidelines (e.g., "search for the service name + operation name").

### Reference / Example Changes
**Trigger:** `fuzzy_correctness` < 0.60 OR `judge_correctness` < 6 across multiple question categories.

**Actions:**
- Add worked examples demonstrating correct tool use and answer format.
- Include examples from the benchmark's failing question categories (e.g., `direct_lookup`, `multi_hop`).
- Show what a "bad" answer looks like and why it fails.

### Evaluation / Constraint Changes
**Trigger:** `citation_score` < 0.50 OR `judge_grounding` < 6.

**Actions:**
- Add self-check instruction: "Before finishing, verify each claim is supported by a retrieved doc."
- Require the agent to name the source document for each factual claim.

---

## Optimization Loop Stopping Criteria

Stop iterating on a variant when:

- `overall_score` ≥ 80 (out of 100), OR
- All individual thresholds from `QUALITY_METRIC_SPEC.md` are met, OR
- Three consecutive optimization iterations produce < 2-point improvement in `overall_score`.

After stopping, the best-performing variant (by `overall_score`) becomes the canonical variant for that skill slot until the next evaluation cycle.
