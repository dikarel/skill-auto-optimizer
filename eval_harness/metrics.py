"""
metrics.py
Quality and performance metric functions.

Ported from scripts/run_fixtures.py, with the two critical fixes that motivate the
symmetric-instrumentation re-run:

  1. tool_use_rate and doc_grounding are NO LONGER hardcoded to 0.0. They are
     computed from what the agent actually did during a real tool-execution loop
     (see agent_loop.py). In the original harness these two fields — worth 35 of
     the 100 quality points and ranked the #1 quality objective — were always 0,
     so the composite quality score was structurally blind to grounding/tool use.

  2. perf_score is computed from OBSERVED execution (real tool_calls, real
     files_read / bytes_read from the tool trace) rather than a static regex scan
     of the skill text.

The scoring formulas themselves are unchanged from QUALITY_METRIC_SPEC.md /
PERF_METRIC_SPEC.md so results remain comparable to the original study.
"""
from __future__ import annotations

import re

# ── Keyword tables (verbatim from QUALITY_METRIC_SPEC.md) ─────────────────────
CITATION_KEYWORDS = [
    "according to", "based on", "as described in", "the documentation states",
    "per the", "as noted in", "as mentioned in", "the doc", "source:", "references",
    "documentation says", "docs say", "as outlined", "§",
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


def compute_hallucination_risk(text: str, tool_called: bool, requires_tools: bool) -> float:
    """Higher = worse. +2 phantom hits when the fixture needs external data but no
    tool was called — now driven by REAL tool_called, not a hardcoded False."""
    lower = text.lower()
    matches = sum(1 for p in HALLUCINATION_RISK_PHRASES if p in lower)
    if requires_tools and not tool_called:
        matches += 2
    return min(1.0, matches / 4.0)


def compute_answer_length_score(text: str) -> float:
    if not text:
        return 0.0
    words = len(text.split())
    if words < 20:     return 0.2
    elif words < 50:   return 0.6
    elif words <= 250: return 1.0
    elif words <= 400: return 0.8
    else:              return 0.6


def compute_fuzzy_correctness(answer: str, ground_truth: str) -> float:
    """Token-level F1 between answer and ground truth (lowercased word tokens)."""
    if not answer or not ground_truth:
        return 0.0
    def tok(t: str) -> set[str]:
        return set(re.findall(r"\b\w+\b", t.lower()))
    a, g = tok(answer), tok(ground_truth)
    if not g:
        return 0.0
    overlap = a & g
    prec = len(overlap) / len(a) if a else 0.0
    rec = len(overlap) / len(g)
    if prec + rec == 0:
        return 0.0
    return round(2 * prec * rec / (prec + rec), 3)


# ── LIVE metrics (the un-stubbed ones) ────────────────────────────────────────
def compute_tool_use_rate(tool_called: bool) -> float:
    """Per-sample: 1.0 if the agent called at least one tool, else 0.0.
    Aggregated across samples this becomes the fraction of runs that used tools."""
    return 1.0 if tool_called else 0.0


def compute_doc_grounding(retrieved_doc_ids: list[str], relevant_doc_ids: list[str]) -> float | None:
    """Fraction of relevant docs actually retrieved during the run.
    Returns None when the fixture declares no relevant docs (self-contained tasks)
    so that grounding is EXCLUDED from that fixture's quality score rather than
    dragging it to zero — matching QUALITY_METRIC_SPEC.md's 'no relevant doc IDs'
    handling."""
    relevant = set(relevant_doc_ids)
    if not relevant:
        return None
    retrieved = set(retrieved_doc_ids)
    return round(len(retrieved & relevant) / len(relevant), 3)


# ── Composite scores ──────────────────────────────────────────────────────────
def compute_perf_score(wall_clock_s: float, tool_calls: int, files_read: int, bytes_read: int) -> float:
    """Harness perf_score from SKILLS_TEST_SUITE.md. Inputs are now OBSERVED from
    the execution trace, not static analysis."""
    return 1000 / (1 + wall_clock_s + 0.25 * tool_calls + 0.01 * files_read + 0.0001 * bytes_read)


def compute_quality_score(
    tool_use_rate: float,
    citation_score: float,
    hallucination_risk: float,
    doc_grounding: float | None,
    fuzzy_correctness: float,
    judge_overall: float | None,
) -> float:
    """Composite 0-100 quality score (QUALITY_METRIC_SPEC.md leaderboard formula).

    When doc_grounding is None (fixture has no relevant docs), its 20-point
    component is dropped AND the max is renormalised so self-contained fixtures are
    not penalised for a dimension that does not apply to them. In the original
    harness both tool_use_rate and doc_grounding were passed as a literal 0.0 for
    every fixture — that is the bug this function fixes.
    """
    components = [
        ("tool_use", tool_use_rate * 15, 15),
        ("citation", citation_score * 10, 10),
        ("hallucination", (1.0 - hallucination_risk) * 15, 15),
        ("fuzzy", fuzzy_correctness * 10, 10),
    ]
    if doc_grounding is not None:
        components.append(("grounding", doc_grounding * 20, 20))
    if judge_overall is not None:
        components.append(("judge", judge_overall * 3, 30))

    earned = sum(c[1] for c in components)
    max_pts = sum(c[2] for c in components)
    # Renormalise to 0-100 so fixtures with dropped components stay comparable.
    return round(earned / max_pts * 100, 2) if max_pts else 0.0
