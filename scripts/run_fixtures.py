#!/usr/bin/env python3
"""
Fixture Evaluation and Optimization Pipeline
=============================================
For each fixture in SKILLS_TEST_SUITE.md:
  1. Evaluate the SKILL.md against its benchmark task
  2. Compute quality metrics (QUALITY_METRIC_SPEC.md) and perf metrics (PERF_METRIC_SPEC.md)
  3. Compute the harness perf_score (SKILLS_TEST_SUITE.md scorecard)
  4. Run the optimizer — rewrites SKILL.md in place (no variants)
  5. Re-evaluate the optimized skill
  6. Print a before/after scorecard

Run from repo root:
  python scripts/run_fixtures.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: make skill_optimizer importable and load its .env
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
SKILL_OPT = ROOT / "skill_optimizer"
sys.path.insert(0, str(SKILL_OPT))

from dotenv import load_dotenv
load_dotenv(SKILL_OPT / ".env")

import anthropic

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
FIXTURES_DIR   = ROOT / "tmp" / "test-skills"
OUTPUTS_DIR    = ROOT / "outputs" / "fixture_results"
LOGS_DIR       = ROOT / "logs"
SPEC_DIR       = ROOT / "skill-auto-optimizer"

OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
EVAL_MODEL      = os.getenv("AGENT_MODEL",     "claude-sonnet-4-6")
JUDGE_MODEL     = os.getenv("JUDGE_MODEL",     "claude-sonnet-4-6")
OPTIMIZER_MODEL = os.getenv("OPTIMIZER_MODEL", "claude-sonnet-4-6")

# Per-million-token pricing (PERF_METRIC_SPEC.md rate table, early 2026)
PRICING: dict[str, dict[str, float]] = {
    "claude-haiku-4-5-20251001": {"input": 0.80,  "output": 4.00},
    "claude-sonnet-4-6":         {"input": 3.00,  "output": 15.00},
    "claude-opus-4-6":           {"input": 15.00, "output": 75.00},
}

# ---------------------------------------------------------------------------
# Fixture definitions (benchmark task, expected answer, seed defect summary)
# ---------------------------------------------------------------------------
FIXTURES: dict[str, dict] = {
    "fixture-chatty-reference-loader": {
        "benchmark_task": (
            "What is the rate limit for the public API endpoint for fetching user data?"
        ),
        "expected_answer": (
            "The public API rate limit is 1000 requests per hour per API key. "
            "The burst limit is 100 requests per minute."
        ),
        "seed_defect_description": (
            "SKILL.md instructs the agent to read all 5 reference files before answering every "
            "question — even simple single-reference questions. Instructions are repeated twice "
            "(duplicate 'always read all references'). No performance or quality metrics are emitted."
        ),
        "requires_tools": True,   # should call read_file; no-tool penalty applies
        "n_samples": 3,
    },
    "fixture-serial-scriptless": {
        "benchmark_task": (
            "Summarize the contents of the /tmp/synthetic-dir directory, "
            "which contains 10 small log files covering authentication, API calls, "
            "billing, cache, and error events."
        ),
        "expected_answer": (
            "The directory contains 10 log files: auth.log (authentication events), "
            "api.log (API call traces), billing.log (payment events), cache.log "
            "(cache hit/miss stats), and error.log (error stack traces), each ~2–8 KB. "
            "Files collectively record system operational activity."
        ),
        "seed_defect_description": (
            "SKILL.md mandates sequential per-file reads with a mandatory full second pass "
            "for verification. Explicitly bans batching and helper scripts. "
            "For 10 files this means 20 individual file reads. No metrics emitted."
        ),
        "requires_tools": True,   # should batch-read files via shell; no-tool penalty applies
        "n_samples": 3,
    },
    "fixture-missing-metrics": {
        "benchmark_task": (
            "Summarize the following quarterly sales data: "
            "Q1: $1.2M, Q2: $1.8M, Q3: $2.1M, Q4: $2.4M. Total budget was $6.5M."
        ),
        "expected_answer": (
            "Total annual revenue: $7.5M, exceeding the $6.5M budget by $1M (15.4% over). "
            "Q4 was the strongest quarter at $2.4M. "
            "Consistent quarter-over-quarter growth averaging approximately 26%."
        ),
        "seed_defect_description": (
            "SKILL.md has reasonable instructions but emits no logs, no performance metrics, "
            "and no quality signals. There is no defined eval or benchmark path."
        ),
        "requires_tools": False,  # data is self-contained in the prompt; no tool penalty
        "n_samples": 3,
    },
    "fixture-quality-regression-trap": {
        "benchmark_task": (
            "What happens when a user account has zero transactions but still has an active "
            "subscription? What billing actions occur at the next cycle?"
        ),
        "expected_answer": (
            "An account with zero transactions and an active subscription still incurs the "
            "full subscription charge at the next billing cycle. The subscription remains "
            "active, the user retains all subscription benefits, and the billing date is "
            "unaffected by the absence of transactions. The standard payment retry policy "
            "applies if the charge fails."
        ),
        "seed_defect_description": (
            "SKILL.md instructs the agent to 'prefer brief answers and skip edge cases.' "
            "The exact benchmark question (active subscription + zero transactions) is "
            "explicitly used as an example of an edge case to omit. No metrics emitted."
        ),
        "requires_tools": False,  # policy question answered from knowledge; no tool penalty
        "n_samples": 3,
    },
    "fixture-travel-planning": {
        "benchmark_task": (
            "Build a 7-day itinerary for two travelers leaving from Minneapolis, covering "
            "three cities in Ohio, March 17–23 2022, total budget $5,100, pet-friendly "
            "accommodations required, no flights, preferred cuisines: American, Mediterranean, "
            "Chinese, Italian. Output the result as JSON at /app/output/itinerary.json."
        ),
        "expected_answer": (
            "A valid JSON itinerary with exactly 7 day objects covering Cleveland, Columbus, "
            "and Cincinnati. All accommodations are pet-friendly. No flight legs. "
            "Cumulative cost ≤ $5,100. Each day includes breakfast/lunch/dinner from the "
            "specified cuisines and 2–3 attractions. Output written to /app/output/itinerary.json."
        ),
        "seed_defect_description": (
            "SKILL.md has no instruction to call any search tools before constructing the "
            "itinerary. Hard constraints (no-flights, pet-friendly, $5,100 budget) are not "
            "marked as blocking requirements. No required JSON output schema is specified. "
            "No self-check step. No metrics emitted."
        ),
        "requires_tools": True,   # must search for real place data; no-tool penalty applies
        "n_samples": 3,
    },
}

# ---------------------------------------------------------------------------
# Quality metric helpers (from QUALITY_METRIC_SPEC.md)
# ---------------------------------------------------------------------------
CITATION_KEYWORDS = [
    "according to", "based on", "as described in", "the documentation states",
    "per the", "as noted in", "as mentioned in", "the doc", "source:", "references",
    "documentation says", "docs say", "as outlined",
]

HALLUCINATION_RISK_PHRASES = [
    "typically", "generally speaking", "in most cases", "as a rule of thumb",
    "usually", "i believe", "i think", "it's common", "best practice",
    "standard practice", "normally", "as you know", "most companies",
]


def compute_citation_score(text: str) -> float:
    lower = text.lower()
    matches = sum(1 for kw in CITATION_KEYWORDS if kw in lower)
    return min(1.0, matches / 2.0)


def compute_hallucination_risk(
    text: str, tool_called: bool = False, requires_tools: bool = True
) -> float:
    lower = text.lower()
    matches = sum(1 for p in HALLUCINATION_RISK_PHRASES if p in lower)
    # Only penalise absent tool use when the fixture genuinely requires external data.
    # Skills whose benchmark data is fully self-contained in the prompt should not be
    # penalised for not calling tools.
    if requires_tools and not tool_called:
        matches += 2
    return min(1.0, matches / 4.0)


def compute_answer_length_score(text: str) -> float:
    if not text:
        return 0.0
    words = len(text.split())
    if words < 20:    return 0.2
    elif words < 50:  return 0.6
    elif words <= 250: return 1.0
    elif words <= 400: return 0.8
    else:             return 0.6


def compute_fuzzy_correctness(answer: str, ground_truth: str) -> float:
    if not answer or not ground_truth:
        return 0.0
    def tok(t: str) -> set[str]:
        return set(re.findall(r"\b\w+\b", t.lower()))
    a, g = tok(answer), tok(ground_truth)
    if not g:
        return 0.0
    overlap = a & g
    prec = len(overlap) / len(a) if a else 0.0
    rec  = len(overlap) / len(g)
    if prec + rec == 0:
        return 0.0
    return round(2 * prec * rec / (prec + rec), 3)


def compute_estimated_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    rates = PRICING.get(model, {"input": 3.00, "output": 15.00})
    return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000


def compute_perf_score(
    wall_clock_s: float, tool_calls: int, files_read: int, bytes_read: int
) -> float:
    """Harness-level perf_score from SKILLS_TEST_SUITE.md."""
    return 1000 / (1 + wall_clock_s + 0.25 * tool_calls + 0.01 * files_read + 0.0001 * bytes_read)


def compute_quality_score(
    tool_use_rate: float,
    citation_score: float,
    hallucination_risk: float,
    doc_grounding: float,
    fuzzy_correctness: float,
    judge_overall: float | None,
) -> float:
    """
    Composite quality score (0–100) from QUALITY_METRIC_SPEC.md leaderboard formula.

    Weights:
      tool_use_rate        × 15  → max 15
      citation_score       × 10  → max 10
      (1-hallucination)    × 15  → max 15
      doc_grounding        × 20  → max 20
      fuzzy_correctness    × 10  → max 10
      judge_overall        ×  3  → max 30  (judge is 0–10)
    Total max: 100
    """
    components = [
        tool_use_rate * 15,
        citation_score * 10,
        (1.0 - hallucination_risk) * 15,
        doc_grounding * 20,
        fuzzy_correctness * 10,
    ]
    if judge_overall is not None:
        components.append(judge_overall * 3)
    return round(sum(components), 2)


# Imperative read verbs — a .md reference only counts as a file read when it appears
# near one of these verbs.  This prevents lookup tables that list available files
# (but don't instruct reading them all) from inflating files_read.
_READ_VERBS = re.compile(r'\b(?:read|load|open|cat|fetch)\b', re.IGNORECASE)


def count_skill_file_references(skill_text: str, skill_dir: Path) -> tuple[int, int]:
    """
    Static analysis: count .md files that the skill text explicitly instructs to read,
    using imperative verb proximity as the signal.  Returns (file_count, total_bytes).

    A reference is only counted when one of the _READ_VERBS appears within 80 characters
    of the filename — this excludes lookup tables and examples that merely name files
    without instructing the agent to load them.
    """
    refs = re.findall(r'[\w/.-]+\.md', skill_text)
    found: list[Path] = []
    total_bytes = 0
    for ref in refs:
        candidate = skill_dir / ref
        if not candidate.exists() or candidate == skill_dir / "SKILL.md":
            continue
        idx = skill_text.find(ref)
        surrounding = skill_text[max(0, idx - 80): idx + 80]
        if _READ_VERBS.search(surrounding) and candidate not in found:
            found.append(candidate)
            total_bytes += candidate.stat().st_size
    return len(found), total_bytes


# ---------------------------------------------------------------------------
# JSONL logger (PERF_METRIC_SPEC.md / logs_spec.md)
# ---------------------------------------------------------------------------
_session_id = str(uuid.uuid4())

def log_event(event: str, skill_name: str, skill_path: str, payload: dict) -> None:
    record = {
        "ts":         datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "session_id": _session_id,
        "event":      event,
        "skill_name": skill_name,
        "skill_path": str(skill_path),
        **payload,
    }
    log_file = LOGS_DIR / f"{datetime.now(timezone.utc).date()}.jsonl"
    with open(log_file, "a") as f:
        f.write(json.dumps(record) + "\n")


# ---------------------------------------------------------------------------
# LLM Judge
# ---------------------------------------------------------------------------
LLM_JUDGE_PROMPT = """\
You are evaluating an AI assistant's response to a benchmark task.

Task: {task}

Expected answer (ground truth): {expected_answer}

Actual response from the agent:
{response}

Score on 0–10:
1. Correctness: accuracy versus the expected answer
2. Completeness: does it fully address all parts of the task
3. Overall: holistic quality

Also assess:
- quality_pass: true if the task is satisfactorily completed, false if there are critical failures or omissions
- quality_notes: 1–2 sentences describing the main issues or strengths

Respond in JSON only:
{{
  "correctness": <0-10>,
  "completeness": <0-10>,
  "overall": <0-10>,
  "quality_pass": <true|false>,
  "quality_notes": "<string>"
}}"""


def llm_judge(
    task: str,
    expected_answer: str,
    response: str,
    client: anthropic.Anthropic,
) -> dict:
    prompt = LLM_JUDGE_PROMPT.format(
        task=task,
        expected_answer=expected_answer,
        response=response[:2000],  # cap to save tokens
    )
    try:
        r = client.messages.create(
            model=JUDGE_MODEL,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        text = r.content[0].text.strip()
        start, end = text.find("{"), text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except Exception as e:
        print(f"    [judge error] {e}")
    return {
        "correctness": 0, "completeness": 0, "overall": 0,
        "quality_pass": False, "quality_notes": "Judge call failed."
    }


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------
def evaluate_fixture(
    fixture_name: str,
    fixture_def: dict,
    client: anthropic.Anthropic,
    label: str = "baseline",
    skill_text_override: str | None = None,
    n_samples_override: int | None = None,
) -> dict:
    """
    Run the benchmark task against the fixture's SKILL.md (or skill_text_override)
    for n_samples independent calls, then average all metrics.

    skill_text_override: pass the candidate skill text directly (used by the quality
        guard check in optimize_fixture) without writing it to disk first.
    n_samples_override: override the fixture's n_samples setting (e.g. use 1 for the
        cheap quality-guard check inside optimize_fixture).
    """
    skill_dir  = FIXTURES_DIR / fixture_name
    skill_path = skill_dir / "SKILL.md"
    skill_text = (
        skill_text_override
        if skill_text_override is not None
        else skill_path.read_text(encoding="utf-8")
    )

    benchmark_task  = fixture_def["benchmark_task"]
    expected_answer = fixture_def["expected_answer"]
    requires_tools  = fixture_def.get("requires_tools", True)
    n_samples       = (
        n_samples_override
        if n_samples_override is not None
        else fixture_def.get("n_samples", 1)
    )

    # Static analysis — only count files mentioned near imperative read verbs
    files_read, bytes_read = count_skill_file_references(skill_text, skill_dir)

    # ── n_samples eval loop ──────────────────────────────────────────────────
    samples: list[dict] = []
    for i in range(n_samples):
        tag = f"sample {i+1}/{n_samples}" if n_samples > 1 else "task"
        print(f"  [{label}] Running benchmark {tag}...")
        t0 = time.time()
        try:
            resp = client.messages.create(
                model=EVAL_MODEL,
                max_tokens=1024,
                system=skill_text,
                messages=[{"role": "user", "content": benchmark_task}],
            )
            ws  = time.time() - t0
            ans = resp.content[0].text.strip() if resp.content else ""
            inp = resp.usage.input_tokens
            out = resp.usage.output_tokens
            err = None
        except Exception as e:
            ws  = time.time() - t0
            ans = ""
            inp = out = 0
            err = str(e)
            print(f"    [eval error] {e}")

        cit  = round(compute_citation_score(ans), 3)
        hal  = round(compute_hallucination_risk(ans, tool_called=False, requires_tools=requires_tools), 3)
        als  = round(compute_answer_length_score(ans), 3)
        fuzz = compute_fuzzy_correctness(ans, expected_answer)
        cost = compute_estimated_cost(inp, out, EVAL_MODEL)

        judge_tag = f"judge {i+1}/{n_samples}" if n_samples > 1 else "judge"
        print(f"  [{label}] Running LLM {judge_tag}...")
        jdg = llm_judge(benchmark_task, expected_answer, ans, client)

        samples.append({
            "wall_clock_s": ws, "answer": ans,
            "input_tokens": inp, "output_tokens": out, "total_tokens": inp + out,
            "latency_ms": ws * 1000, "estimated_cost": cost, "error": err,
            "citation_score": cit, "hallucination_risk": hal,
            "answer_length_score": als, "fuzzy_correctness": fuzz,
            "judge": jdg,
        })

    # ── Aggregate ─────────────────────────────────────────────────────────────
    def _avg(key: str) -> float:
        vals = [s[key] for s in samples if s.get(key) is not None]
        return sum(vals) / len(vals) if vals else 0.0

    def _avg_judge(key: str) -> float | None:
        vals = [s["judge"].get(key) for s in samples if s["judge"].get(key) is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    wall_clock_s       = _avg("wall_clock_s")
    input_tokens       = round(_avg("input_tokens"))
    output_tokens      = round(_avg("output_tokens"))
    total_tokens       = round(_avg("total_tokens"))
    latency_ms         = round(_avg("latency_ms"), 1)
    estimated_cost     = _avg("estimated_cost")
    citation_score     = round(_avg("citation_score"), 3)
    hallucination_risk = round(_avg("hallucination_risk"), 3)
    answer_length_score = round(_avg("answer_length_score"), 3)
    fuzzy_correctness  = round(_avg("fuzzy_correctness"), 3)
    judge_correctness  = _avg_judge("correctness")
    judge_completeness = _avg_judge("completeness")
    judge_overall      = _avg_judge("overall")

    # quality_pass: True if the majority of samples pass
    passes       = sum(1 for s in samples if s["judge"].get("quality_pass", False))
    quality_pass = passes > len(samples) / 2

    # Use the best-scoring sample for the displayed answer and quality notes
    best          = max(samples, key=lambda s: s["judge"].get("overall") or 0)
    answer        = best["answer"]
    quality_notes = best["judge"].get("quality_notes", "")
    error         = next((s["error"] for s in reversed(samples) if s["error"]), None)

    approx_tokens_skill = len(skill_text) // 4

    # Harness perf_score (SKILLS_TEST_SUITE.md)
    tool_calls = 0
    perf_score = compute_perf_score(wall_clock_s, tool_calls, files_read, bytes_read)

    # Composite quality_score (QUALITY_METRIC_SPEC.md leaderboard formula)
    quality_score = compute_quality_score(
        tool_use_rate=0.0,
        citation_score=citation_score,
        hallucination_risk=hallucination_risk,
        doc_grounding=0.0,
        fuzzy_correctness=fuzzy_correctness,
        judge_overall=judge_overall,
    )

    result = {
        "label":               label,
        "fixture":             fixture_name,
        "n_samples":           n_samples,
        "skill_char_count":    len(skill_text),
        "approx_tokens_skill": approx_tokens_skill,
        # Harness scorecard
        "wall_clock_s":        round(wall_clock_s, 3),
        "tool_calls":          tool_calls,
        "files_read":          files_read,
        "bytes_read":          bytes_read,
        "quality_pass":        quality_pass,
        "quality_notes":       quality_notes,
        "perf_score":          round(perf_score, 3),
        "quality_score":       quality_score,
        # Quality metrics (QUALITY_METRIC_SPEC.md)
        "citation_score":      citation_score,
        "hallucination_risk":  hallucination_risk,
        "answer_length_score": answer_length_score,
        "fuzzy_correctness":   fuzzy_correctness,
        "judge_correctness":   judge_correctness,
        "judge_completeness":  judge_completeness,
        "judge_overall":       judge_overall,
        # Perf metrics (PERF_METRIC_SPEC.md)
        "input_tokens":        input_tokens,
        "output_tokens":       output_tokens,
        "total_tokens":        total_tokens,
        "latency_ms":          latency_ms,
        "estimated_cost_usd":  round(estimated_cost, 8),
        "model":               EVAL_MODEL,
        "answer":              answer,
        "error":               error,
    }

    # Log eval event
    log_event(
        event="eval",
        skill_name=fixture_name,
        skill_path=str(skill_path.relative_to(ROOT)),
        payload={
            "query":    benchmark_task,
            "model":    EVAL_MODEL,
            "label":    label,
            "n_samples": n_samples,
            "metrics": {
                "input_tokens":       input_tokens,
                "output_tokens":      output_tokens,
                "total_tokens":       total_tokens,
                "turns":              1,
                "latency_ms":         latency_ms,
                "estimated_cost_usd": round(estimated_cost, 8),
            },
            "quality": {
                "citation_score":      citation_score,
                "hallucination_risk":  hallucination_risk,
                "fuzzy_correctness":   fuzzy_correctness,
                "judge_overall":       judge_overall,
                "quality_pass":        quality_pass,
                "quality_score":       quality_score,
            },
            "harness": {
                "files_read":    files_read,
                "bytes_read":    bytes_read,
                "perf_score":    round(perf_score, 3),
                "quality_score": quality_score,
            },
        },
    )

    return result


# ---------------------------------------------------------------------------
# Optimizer
# ---------------------------------------------------------------------------
OPTIMIZER_PROMPT = """\
You are an expert skill optimizer. Your job is to rewrite a SKILL.md file to be
better in measurable ways, following two published specs:

  PERF_OPTIMIZATION_OBJECTIVE_SPEC.md — targets: ≥30% token reduction, ≥15% latency reduction, ≥20% cost reduction
  QUALITY_OBJECTIVE_SPEC.md — priority: tool-use/grounding > correctness > hallucination > citation > completeness > conciseness

---

## Current SKILL.md (variant: {fixture_name})

```
{skill_content}
```

Skill size: {char_count} chars ≈ {approx_tokens} tokens

---

## Evaluation Results

### Harness Scorecard (SKILLS_TEST_SUITE.md)
- wall_clock_s:   {wall_clock_s:.2f}s
- files_read:     {files_read}  (lower is better)
- bytes_read:     {bytes_read} bytes
- quality_pass:   {quality_pass}
- quality_notes:  {quality_notes}
- perf_score:     {perf_score:.2f}  (higher is better)
- quality_score:  {quality_score:.2f} / 100  (higher is better)

### Quality Metrics (QUALITY_METRIC_SPEC.md; thresholds in parens)
- citation_score:      {citation_score:.3f}  (target ≥ 0.50)
- hallucination_risk:  {hallucination_risk:.3f}  (target ≤ 0.25)
- answer_length_score: {answer_length_score:.3f}  (target ≥ 0.80)
- fuzzy_correctness:   {fuzzy_correctness:.3f}  (target ≥ 0.60)
- judge_overall:       {judge_overall}/10  (target ≥ 6)
- judge_correctness:   {judge_correctness}/10
- judge_completeness:  {judge_completeness}/10

### Performance Metrics (PERF_METRIC_SPEC.md)
- input_tokens:        {input_tokens}
- output_tokens:       {output_tokens}
- total_tokens:        {total_tokens}
- latency_ms:          {latency_ms:.1f} ms
- estimated_cost_usd:  ${estimated_cost_usd:.6f}
- approx_tokens(skill): {approx_tokens} (chars/4)

### Identified Seed Defects
{seed_defect_description}

### Agent's Answer to Benchmark Task
Task: {benchmark_task}
Answer (first 600 chars):
{answer_snippet}

---

## Optimization Decision Rules

**Performance (apply "compress" strategy — PERF_OPTIMIZATION_OBJECTIVE_SPEC.md):**
- Skill is {approx_tokens} tokens → always apply compress (threshold: > 400 tokens)
- Compress: rewrite prose paragraphs as tight bullet points; remove repeated/redundant text;
  use abbreviations for common terms; target ≥ 30% token reduction
- Add a YAML `<!-- cache_control: ephemeral -->` comment on the static block if the skill
  is stateless across calls (no per-request placeholders needed)

**Quality (QUALITY_OBJECTIVE_SPEC.md decision rules):**
- If files_read > 1 AND only 1 file is needed: tighten trigger/selection guidance;
  add progressive disclosure (select relevant reference first, load others only if needed)
- If the skill bans useful automation (scripts, batching): remove the ban; add a bundled
  helper script recommendation instead
- If no instrumentation exists: add an "## Instrumentation" section listing required
  perf metrics (input_tokens, output_tokens, latency_ms, estimated_cost_usd per
  PERF_METRIC_SPEC.md) and quality signals (citation language, tool_calls, grounding)
- If quality shortcuts omit edge cases: remove the shortcut; add "preserve all edge cases"
  and explicit quality guardrails
- If no tool use is instructed but external data is needed: add explicit required tool-use
  steps with tool names and ordering
- If output schema is missing: add exact required schema with field names, types, example

**Instrumentation requirement (PERF_METRIC_SPEC.md + QUALITY_METRIC_SPEC.md):**
Every optimized skill must include an "## Instrumentation" section that states:
- Which perf metrics to emit on each run (input_tokens, output_tokens, total_tokens,
  turns, latency_ms, estimated_cost_usd)
- Which quality signals to include in outputs (citations with source names, grounding
  references, tool call count)
- Where logs should go: logs/<YYYY-MM-DD>.jsonl (one record per eval event)

---

## Your Task

Rewrite the SKILL.md to:
1. Apply the "compress" strategy — convert prose to compact bullets, remove redundancy,
   target ≥ 30% character reduction from {char_count} chars
2. Fix every identified seed defect
3. Add quality guardrails that prevent the failure modes shown in the evaluation
4. Add an "## Instrumentation" section with the required metric contract
5. Improve perf_score by reducing files_read and bytes_read where possible

**Quality constraint (non-negotiable):** The optimized skill must maintain or improve
answer quality. Do not compress to the point where the agent can no longer correctly
answer the benchmark task. If the compress strategy conflicts with correctness or
completeness, preserve correctness — token savings are secondary.
The current judge_overall is {judge_overall}/10; the optimized skill must score ≥ {judge_floor}/10.

Output ONLY the improved SKILL.md. No preamble, no explanation. Start directly with
the YAML frontmatter (---) or the first heading (#).
"""


def optimize_fixture(
    fixture_name: str,
    fixture_def: dict,
    baseline: dict,
    client: anthropic.Anthropic,
) -> str:
    """
    Generate an improved SKILL.md, run a 1-sample quality guard check, and only
    write the result to disk if quality has not regressed.  Returns the skill text
    that is now on disk (either improved or original).
    """
    skill_dir  = FIXTURES_DIR / fixture_name
    skill_path = skill_dir / "SKILL.md"
    skill_text = skill_path.read_text(encoding="utf-8")
    char_count = len(skill_text)

    baseline_judge = baseline["judge_overall"] or 0
    # Require optimized skill to score within 1 point of baseline
    judge_floor = max(0.0, baseline_judge - 1.0)

    prompt = OPTIMIZER_PROMPT.format(
        fixture_name=fixture_name,
        skill_content=skill_text,
        char_count=char_count,
        approx_tokens=char_count // 4,
        benchmark_task=fixture_def["benchmark_task"],
        seed_defect_description=fixture_def["seed_defect_description"],
        answer_snippet=baseline["answer"][:600],
        # harness
        wall_clock_s=baseline["wall_clock_s"],
        files_read=baseline["files_read"],
        bytes_read=baseline["bytes_read"],
        quality_pass=baseline["quality_pass"],
        quality_notes=baseline["quality_notes"],
        perf_score=baseline["perf_score"],
        quality_score=baseline["quality_score"],
        # quality
        citation_score=baseline["citation_score"],
        hallucination_risk=baseline["hallucination_risk"],
        answer_length_score=baseline["answer_length_score"],
        fuzzy_correctness=baseline["fuzzy_correctness"],
        judge_overall=baseline_judge,
        judge_floor=judge_floor,
        judge_correctness=baseline["judge_correctness"] or 0,
        judge_completeness=baseline["judge_completeness"] or 0,
        # perf
        input_tokens=baseline["input_tokens"],
        output_tokens=baseline["output_tokens"],
        total_tokens=baseline["total_tokens"],
        latency_ms=baseline["latency_ms"],
        estimated_cost_usd=baseline["estimated_cost_usd"],
    )

    print(f"  [optimize] Calling optimizer ({OPTIMIZER_MODEL})...")
    t0 = time.time()
    resp = client.messages.create(
        model=OPTIMIZER_MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    opt_latency = time.time() - t0
    improved = resp.content[0].text.strip()

    before_chars  = char_count
    after_chars   = len(improved)
    before_approx = before_chars // 4
    after_approx  = after_chars // 4
    reduction_pct = round((before_approx - after_approx) / before_approx * 100, 1) if before_approx else 0

    opt_input  = resp.usage.input_tokens
    opt_output = resp.usage.output_tokens
    opt_cost   = compute_estimated_cost(opt_input, opt_output, OPTIMIZER_MODEL)

    # ── Quality floor guard ───────────────────────────────────────────────────
    # Evaluate the candidate (1 sample, in-memory — no disk write yet) and abort
    # if it would flip quality_pass from True→False or drop judge_overall > 1 point.
    print(f"  [optimize] Quality guard check (1 sample)...")
    candidate_eval = evaluate_fixture(
        fixture_name, fixture_def, client,
        label="candidate",
        skill_text_override=improved,
        n_samples_override=1,
    )
    candidate_judge = candidate_eval["judge_overall"] or 0
    quality_regressed = (
        (baseline["quality_pass"] and not candidate_eval["quality_pass"])
        or (candidate_judge < judge_floor)
    )

    if quality_regressed:
        print(
            f"  [optimize] Quality guard: ABORT  "
            f"(baseline judge={baseline_judge:.1f} pass={baseline['quality_pass']}, "
            f"candidate judge={candidate_judge:.1f} pass={candidate_eval['quality_pass']}, "
            f"floor={judge_floor:.1f}) — keeping baseline skill"
        )
        log_event(
            event="optimize",
            skill_name=fixture_name,
            skill_path=str(skill_path.relative_to(ROOT)),
            payload={
                "strategy":        "compress",
                "optimizer_model": OPTIMIZER_MODEL,
                "aborted":         True,
                "abort_reason":    "quality_regression",
                "baseline_judge":  baseline_judge,
                "candidate_judge": candidate_judge,
                "judge_floor":     judge_floor,
                "before": {"char_count": before_chars, "approx_tokens": before_approx},
                "after":  {"char_count": after_chars,  "approx_tokens": after_approx},
                "optimizer_cost": {
                    "input_tokens":       opt_input,
                    "output_tokens":      opt_output,
                    "estimated_cost_usd": round(opt_cost, 8),
                    "latency_ms":         round(opt_latency * 1000, 1),
                },
            },
        )
        return skill_text  # unchanged

    # ── Write accepted candidate ──────────────────────────────────────────────
    skill_path.write_text(improved, encoding="utf-8")
    print(f"  [optimize] SKILL.md accepted: {before_chars}c → {after_chars}c ({reduction_pct}% token reduction)")

    log_event(
        event="optimize",
        skill_name=fixture_name,
        skill_path=str(skill_path.relative_to(ROOT)),
        payload={
            "strategy":        "compress",
            "optimizer_model": OPTIMIZER_MODEL,
            "aborted":         False,
            "baseline_judge":  baseline_judge,
            "candidate_judge": candidate_judge,
            "judge_floor":     judge_floor,
            "before": {"char_count": before_chars, "approx_tokens": before_approx},
            "after":  {"char_count": after_chars,  "approx_tokens": after_approx},
            "efficiency": {
                "token_reduction":     before_approx - after_approx,
                "token_reduction_pct": reduction_pct,
                "char_reduction_pct":  round((before_chars - after_chars) / before_chars * 100, 1),
            },
            "optimizer_cost": {
                "input_tokens":       opt_input,
                "output_tokens":      opt_output,
                "estimated_cost_usd": round(opt_cost, 8),
                "latency_ms":         round(opt_latency * 1000, 1),
            },
            "explanation_snippet": improved[:200],
        },
    )

    return improved


# ---------------------------------------------------------------------------
# Scorecard printer
# ---------------------------------------------------------------------------
def print_scorecard(all_results: list[dict]) -> None:
    from collections import defaultdict
    by_fixture: dict[str, dict] = defaultdict(dict)
    for r in all_results:
        by_fixture[r["fixture"]][r["label"]] = r

    W = 120
    print("\n" + "=" * W)
    print("FIXTURE SCORECARD — baseline vs optimized")
    print("=" * W)

    header = (
        f"{'Fixture':<35} {'Label':<10} "
        f"{'perf_score':>10} {'qual_score':>10} {'quality_pass':>12} "
        f"{'files_read':>10} {'total_tok':>9} "
        f"{'fuzzy_corr':>10} {'hall_risk':>9} "
        f"{'judge_ovr':>9} {'cost_usd':>10}"
    )
    print(header)
    print("-" * W)

    aggregate: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))

    for fixture_name in FIXTURES:
        runs = by_fixture.get(fixture_name, {})
        for label in ("baseline", "optimized"):
            r = runs.get(label)
            if not r:
                continue
            aggregate[label]["perf"].append(r["perf_score"])
            aggregate[label]["quality"].append(r["quality_score"])
            qp = "PASS" if r["quality_pass"] else "FAIL"
            print(
                f"{fixture_name:<35} {label:<10} "
                f"{r['perf_score']:>10.2f} {r['quality_score']:>10.2f} {qp:>12} "
                f"{r['files_read']:>10} {r['total_tokens']:>9} "
                f"{r['fuzzy_correctness']:>10.3f} {r['hallucination_risk']:>9.3f} "
                f"{(r['judge_overall'] or 0):>9.1f} {r['estimated_cost_usd']:>10.6f}"
            )
        print()

    print("-" * W)
    for label in ("baseline", "optimized"):
        ps = aggregate[label]["perf"]
        qs = aggregate[label]["quality"]
        if ps:
            print(
                f"{'AGGREGATE MEAN':<35} {label:<10} "
                f"{sum(ps)/len(ps):>10.2f} {sum(qs)/len(qs):>10.2f}"
            )
    print("=" * W)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    all_results: list[dict] = []
    run_tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    sample_counts = {k: v.get("n_samples", 1) for k, v in FIXTURES.items()}
    print(f"\n{'='*60}")
    print(f"Fixture Eval + Optimize Pipeline  (session {_session_id[:8]})")
    print(f"  eval_model:      {EVAL_MODEL}")
    print(f"  optimizer_model: {OPTIMIZER_MODEL}")
    print(f"  fixtures:        {len(FIXTURES)}")
    print(f"  n_samples:       {sample_counts}")
    print(f"  quality guard:   enabled (abort if judge drops > 1pt or pass flips)")
    print(f"  tool penalty:    fixture-aware (requires_tools flag)")
    print(f"{'='*60}\n")

    for fixture_name, fixture_def in FIXTURES.items():
        print(f"\n{'─'*60}")
        print(f"FIXTURE: {fixture_name}")
        print(f"{'─'*60}")

        # 1. Baseline eval
        baseline = evaluate_fixture(fixture_name, fixture_def, client, label="baseline")
        all_results.append(baseline)
        print(
            f"  [baseline] perf_score={baseline['perf_score']:.2f}  "
            f"quality_pass={baseline['quality_pass']}  "
            f"tokens={baseline['total_tokens']}  "
            f"files_read={baseline['files_read']}"
        )

        # 2. Optimize (rewrites SKILL.md in place)
        optimize_fixture(fixture_name, fixture_def, baseline, client)

        # 3. Post-optimization eval
        optimized = evaluate_fixture(fixture_name, fixture_def, client, label="optimized")
        all_results.append(optimized)
        print(
            f"  [optimized] perf_score={optimized['perf_score']:.2f}  "
            f"quality_pass={optimized['quality_pass']}  "
            f"tokens={optimized['total_tokens']}  "
            f"files_read={optimized['files_read']}"
        )

        delta_perf    = optimized["perf_score"]    - baseline["perf_score"]
        delta_quality = optimized["quality_score"] - baseline["quality_score"]
        delta_tok     = baseline["total_tokens"]   - optimized["total_tokens"]
        delta_tok_pct = round(delta_tok / baseline["total_tokens"] * 100, 1) if baseline["total_tokens"] else 0
        print(
            f"  [delta] Δperf_score={delta_perf:+.2f}  "
            f"Δquality_score={delta_quality:+.2f}  "
            f"Δtokens={delta_tok:+d} ({delta_tok_pct:+.1f}%)"
        )

    # Save raw results
    output_path = OUTPUTS_DIR / f"fixture_results_{run_tag}.json"
    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nResults saved → {output_path}")

    # Session summary log
    for fixture_name in FIXTURES:
        runs = {r["label"]: r for r in all_results if r["fixture"] == fixture_name}
        base = runs.get("baseline", {})
        opt  = runs.get("optimized", {})
        if base and opt:
            log_event(
                event="session_summary",
                skill_name=fixture_name,
                skill_path=str(FIXTURES_DIR / fixture_name / "SKILL.md"),
                payload={
                    "baseline": {
                        "total_tokens": base["total_tokens"],
                        "latency_ms":   base["latency_ms"],
                        "cost_usd":     base["estimated_cost_usd"],
                        "perf_score":   base["perf_score"],
                    },
                    "best_result": {
                        "strategy":             "compress",
                        "total_tokens":         opt["total_tokens"],
                        "latency_ms":           opt["latency_ms"],
                        "cost_usd":             opt["estimated_cost_usd"],
                        "perf_score":           opt["perf_score"],
                        "token_savings_pct":    round(
                            (base["total_tokens"] - opt["total_tokens"]) /
                            base["total_tokens"] * 100, 1
                        ) if base["total_tokens"] else 0,
                        "perf_score_delta":     round(opt["perf_score"] - base["perf_score"], 2),
                    },
                },
            )

    print_scorecard(all_results)


if __name__ == "__main__":
    main()
