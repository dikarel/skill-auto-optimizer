# Quality Metric Spec

This document defines the required quality metrics every target skill must emit during evaluation.

---

## Required Metric Names

Every evaluation run produces one record per (question × skill variant) pair. The following fields are required:

### Rule-Based Metrics

| Metric | Type | Range | Description |
|---|---|---|---|
| `tool_used` | bool | true/false | Whether tool was called at least once |
| `tool_use_rate` | float | 0.0–1.0 | 1.0 if tool was called, else 0.0 |
| `citation_score` | float | 0.0–1.0 | Presence of citation language in the answer (capped at 1.0 after 2+ matches) |
| `hallucination_risk` | float | 0.0–1.0 | Heuristic risk score; higher = more likely hallucinating |
| `doc_grounding` | float | 0.0–1.0 | Fraction of relevant doc IDs actually retrieved |
| `answer_length_score` | float | 0.0–1.0 | Heuristic for appropriate answer length |
| `fuzzy_correctness` | float | 0.0–1.0 | Token-overlap F1 between answer and ground truth |
| `num_tool_calls` | int | ≥ 0 | Total number of tool calls made |
| `retrieved_doc_ids` | list[str] | — | Doc IDs retrieved across all tool calls |
| `latency_seconds` | float | ≥ 0.0 | Wall-clock time for the agent run |
| `error` | str \| null | — | Error message if the run failed, else null |

### LLM Judge Scores (0–10 scale)

| Metric | Description |
|---|---|
| `judge_correctness` | Accuracy relative to the ground truth answer |
| `judge_completeness` | How fully the answer addresses the question |
| `judge_grounding` | Degree to which answer is supported by retrieved docs |
| `judge_conciseness` | Whether the answer is appropriately concise |
| `judge_overall` | Holistic quality score from the LLM judge |
| `judge_reasoning` | 1–2 sentence explanation from the judge |

---

## Evaluation Criteria

### Citation Score
- Scans the answer (case-insensitive) for citation keywords such as: `"according to"`, `"based on"`, `"as described in"`, `"the documentation states"`, `"per the"`, `"as noted in"`, `"source:"`, `"references"`, etc.
- Score = `min(1.0, matches / 2)` — two or more citation markers earns full score.

### Hallucination Risk
- Scans the answer for hedging/vague phrases such as: `"typically"`, `"generally speaking"`, `"i believe"`, `"i think"`, `"usually"`, `"best practice"`, `"normally"`, etc.
- +2 phantom hits added if the tool was never called.
- Score = `min(1.0, matches / 4)` — lower is better.

### Doc Grounding
- `len(retrieved ∩ relevant) / len(relevant)`
- Returns 0.0 if no relevant doc IDs are specified for the question.

### Answer Length Score
- < 20 words → 0.2
- 20–49 words → 0.6
- 50–250 words → 1.0 (target range)
- 251–400 words → 0.8
- > 400 words → 0.6

### Fuzzy Correctness
- Token-level F1: `2 * precision * recall / (precision + recall)` on lowercased word tokens.
- Returns 0.0 if either answer or ground truth is empty.

---

## Field Schema

### Per-Run Record

```json
{
  "run_tag": "string",
  "question_id": "string",
  "question": "string",
  "ground_truth": "string",
  "relevant_doc_ids": ["string"],
  "difficulty": "easy | medium | hard",
  "category": "direct_lookup | multi_hop | ...",
  "skill_variant": "string",
  "answer": "string",
  "iterations": "int",
  "tool_used": "bool",
  "tool_use_rate": "float [0,1]",
  "citation_score": "float [0,1]",
  "hallucination_risk": "float [0,1]",
  "doc_grounding": "float [0,1]",
  "answer_length_score": "float [0,1]",
  "fuzzy_correctness": "float [0,1]",
  "num_tool_calls": "int",
  "retrieved_doc_ids": ["string"],
  "latency_seconds": "float",
  "error": "string | null",
  "judge_correctness": "int [0,10] | null",
  "judge_completeness": "int [0,10] | null",
  "judge_grounding": "int [0,10] | null",
  "judge_conciseness": "int [0,10] | null",
  "judge_overall": "int [0,10] | null",
  "judge_reasoning": "string | null"
}
```

### Leaderboard Record (aggregated per variant)

```json
{
  "skill_variant": "string",
  "num_runs": "int",
  "tool_use_rate": "float",
  "citation_rate": "float",
  "hallucination_risk": "float",
  "doc_grounding": "float",
  "fuzzy_correctness": "float",
  "judge_correctness": "float",
  "judge_overall": "float",
  "avg_latency": "float",
  "overall_score": "float",
  "rank": "int"
}
```

---

## Composite (Overall) Score

The leaderboard `overall_score` is a weighted sum (higher = better):

| Component | Weight | Notes |
|---|---|---|
| `tool_use_rate` | × 15 | Max 15 pts |
| `citation_rate` | × 10 | Max 10 pts |
| `1 - hallucination_risk` | × 15 | Max 15 pts |
| `doc_grounding` | × 20 | Max 20 pts |
| `fuzzy_correctness` | × 10 | Max 10 pts |
| `judge_overall` | × 3 | Max 30 pts (0–10 × 3) |

**Max total: 100 points.**

---

## Scoring / Pass-Fail Rules

A skill variant is considered healthy if:

| Metric | Threshold |
|---|---|
| `tool_use_rate` | ≥ 0.90 (tool called in ≥ 90% of runs) |
| `hallucination_risk` | ≤ 0.25 |
| `doc_grounding` | ≥ 0.60 |
| `judge_overall` (avg) | ≥ 6.0 / 10 |
| `fuzzy_correctness` | ≥ 0.60 (matches `correctness_threshold` in `eval_config.yaml`) |

A variant that fails **two or more** of these thresholds is a candidate for optimization.

---

## Logging / Storage

- Per-run results are written to `outputs/eval_results_<run_tag>.json` as a flat JSON array.
- Pairwise comparison results are written to `outputs/pairwise_<run_tag>.json`.
- Optimization logs (which variants were improved, iteration number, paths) accumulate in `outputs/optimization_log.json`.
- All files are append-friendly; new runs produce new timestamped files; `optimization_log.json` is an appended array.

---

## Handling Uncertain or Missing Quality Signals

| Situation | Behavior |
|---|---|
| LLM judge call fails | All `judge_*` fields set to `null`; run is still included in aggregate (nulls are excluded from averages) |
| Agent errors mid-run | `error` field is populated; `answer` may be empty string; rule metrics computed on empty answer (mostly 0.0) |
| No relevant doc IDs for a question | `doc_grounding` returns 0.0 and is excluded from variant-level quality assessments where doc IDs are missing |
| Answer is empty | `citation_score`, `hallucination_risk`, `answer_length_score`, `fuzzy_correctness` all return 0.0 |
| Pairwise judge cannot parse JSON | Defaults to `"tie"` with `a_score = b_score = 5` and an error explanation |
