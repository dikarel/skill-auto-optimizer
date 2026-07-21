"""
optimizer.py
Produces an optimized SKILL.md from a flawed baseline, following the published
objective specs. Critically, it NEVER overwrites the baseline: the optimized skill
is written to outputs/optimized/<run_tag>/<fixture>/SKILL.md, so the baseline stays
immutable and every run is reproducible from the same starting point.
"""
from __future__ import annotations

from pathlib import Path

OPTIMIZER_PROMPT = """\
You are an expert skill optimizer. Rewrite the SKILL.md below to be better on
BOTH published objective specs, with quality taking precedence over efficiency
when they conflict:

  PERF_OPTIMIZATION_OBJECTIVE_SPEC.md — reduce tokens/latency/cost; avoid redundant
    or unnecessary file reads; prefer batched tool use over serial loops.
  QUALITY_OBJECTIVE_SPEC.md — priority order: tool-use/grounding > correctness >
    hallucination-avoidance > citation > completeness > conciseness. NEVER trade
    away tool-use, grounding, or correctness for token savings.

## Current SKILL.md ({fixture_name})
```
{skill_content}
```

## Known seed defects to fix
{seed_defect}

## Baseline evaluation (what to improve)
- quality_score: {quality_score:.1f}/100   perf_score: {perf_score:.1f}
- tool_use_rate: {tool_use_rate:.2f}   doc_grounding: {doc_grounding}
- fuzzy_correctness: {fuzzy_correctness:.2f}   judge_overall: {judge_overall}/10
- tool_calls: {num_tool_calls}   files_read: {files_read}

## Rewrite requirements
1. Fix every seed defect.
2. If the skill needs external data, mandate tool use BEFORE answering, name the
   tools, and require grounding/citation of retrieved sources.
3. Remove wasteful behavior (reading unneeded files, banned batching, redundant
   verification passes) WITHOUT dropping any required information.
4. Preserve all edge cases and correctness — do not shorten at the cost of the
   benchmark answer.
5. Add a concise "## Instrumentation" section listing the perf + quality metrics to
   emit and the log destination (logs/<YYYY-MM-DD>.jsonl).

Output ONLY the improved SKILL.md, starting with the YAML frontmatter (---).
"""


def _out_path(root: Path, run_tag: str, fixture_name: str) -> Path:
    p = root / "outputs" / "optimized" / run_tag / fixture_name / "SKILL.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def optimize_real(client, model: str, root: Path, run_tag: str, fixture_name: str,
                  fixture_def: dict, baseline_skill: str, baseline_summary: dict) -> tuple[str, Path, dict]:
    prompt = OPTIMIZER_PROMPT.format(
        fixture_name=fixture_name,
        skill_content=baseline_skill,
        seed_defect=fixture_def["seed_defect"],
        quality_score=baseline_summary.get("quality_score_mean", 0.0),
        perf_score=baseline_summary.get("perf_score_mean", 0.0),
        tool_use_rate=baseline_summary.get("tool_use_rate_mean", 0.0),
        doc_grounding=baseline_summary.get("doc_grounding_mean"),
        fuzzy_correctness=baseline_summary.get("fuzzy_correctness_mean", 0.0),
        judge_overall=baseline_summary.get("judge_overall_mean"),
        num_tool_calls=baseline_summary.get("num_tool_calls_mean", 0),
        files_read=baseline_summary.get("files_read_mean", 0),
    )
    resp = client.messages.create(model=model, max_tokens=2048,
                                  messages=[{"role": "user", "content": prompt}])
    text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text").strip()
    path = _out_path(root, run_tag, fixture_name)
    path.write_text(text, encoding="utf-8")
    cost = {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens}
    return text, path, cost


def optimize_mock(root: Path, run_tag: str, fixture_name: str,
                  fixture_def: dict, baseline_skill: str) -> tuple[str, Path, dict]:
    """Cosmetic optimized artifact for smoke tests; mock eval behavior comes from
    MOCK_SCRIPTS['optimized'], not from this text."""
    text = baseline_skill.rstrip() + (
        "\n\n## Instrumentation\n"
        "- Perf: input_tokens, output_tokens, total_tokens, turns, latency_ms, estimated_cost_usd\n"
        "- Quality: tool_calls, retrieved doc ids, citations, grounding_verified\n"
        "- Log to logs/<YYYY-MM-DD>.jsonl (one record per eval)\n"
        "\n<!-- [mock optimizer] behavior scripted in fixtures.MOCK_SCRIPTS -->\n"
    )
    path = _out_path(root, run_tag, fixture_name)
    path.write_text(text, encoding="utf-8")
    return text, path, {"input_tokens": 0, "output_tokens": 0}
