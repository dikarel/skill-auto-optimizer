"""
judge.py
LLM-as-judge scoring (real) and a deterministic mock judge for smoke tests.

Note on circularity (call it out in the paper's limitations): the judge and the
agent are the same model family. The real judge is asked only for a bounded rubric
score; to reduce single-sample noise the caller runs multiple samples and reports
confidence intervals. A stronger design (different judge model, or a rubric with
anchored examples) is future work.
"""
from __future__ import annotations

import json

from metrics import compute_fuzzy_correctness

JUDGE_PROMPT = """\
You are grading an AI assistant's answer to a benchmark task.

Task:
{task}

Reference (ground-truth) answer:
{expected}

Assistant's answer:
{answer}

Grade on a 0-10 integer scale:
1. correctness  — factual accuracy vs the reference
2. completeness — does it address every part of the task, including edge cases
3. overall      — holistic quality

Also decide:
- quality_pass: true only if the answer is correct AND complete (no critical omissions)
- quality_notes: one short sentence; avoid braces, quotes, and newlines

Respond with a SINGLE JSON object and nothing else, inside a ```json code fence:
```json
{{"correctness": 0, "completeness": 0, "overall": 0, "quality_pass": false, "quality_notes": "..."}}
```"""

# A parse/call failure returns None for every score. Per QUALITY_METRIC_SPEC.md,
# a failed judge is EXCLUDED from averages (null), not scored 0 — scoring it 0
# would fabricate a quality regression whenever the judge reply is malformed.
_JUDGE_FAIL = {"correctness": None, "completeness": None, "overall": None,
               "quality_pass": None, "input_tokens": 0, "output_tokens": 0}


def _extract_json(text: str) -> dict | None:
    text = text.strip()
    candidates = []
    if "```" in text:  # prefer a fenced block
        import re
        for m in re.findall(r"```(?:json)?\s*(.*?)```", text, re.DOTALL):
            candidates.append(m.strip())
    if "{" in text and "}" in text:
        candidates.append(text[text.find("{"): text.rfind("}") + 1])
    candidates.append(text)
    for c in candidates:
        try:
            return json.loads(c)
        except Exception:  # noqa: BLE001
            continue
    return None


def llm_judge(client, model: str, task: str, expected: str, answer: str) -> dict:
    prompt = JUDGE_PROMPT.format(task=task, expected=expected, answer=(answer or "")[:3000])
    try:
        r = client.messages.create(
            model=model, max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(getattr(b, "text", "") for b in r.content if getattr(b, "type", None) == "text").strip()
        d = _extract_json(text)
        if d is not None and "overall" in d:
            return {
                "correctness": int(d.get("correctness", 0)),
                "completeness": int(d.get("completeness", 0)),
                "overall": int(d.get("overall", 0)),
                "quality_pass": bool(d.get("quality_pass", False)),
                "quality_notes": str(d.get("quality_notes", "")),
                "input_tokens": r.usage.input_tokens,
                "output_tokens": r.usage.output_tokens,
            }
        return {**_JUDGE_FAIL, "quality_notes": "judge returned no parseable JSON (excluded)",
                "input_tokens": r.usage.input_tokens, "output_tokens": r.usage.output_tokens}
    except Exception as e:  # noqa: BLE001
        return {**_JUDGE_FAIL, "quality_notes": f"judge error: {e} (excluded)"}


def mock_judge(task: str, expected: str, answer: str) -> dict:
    """Deterministic judge: overall scales with token-F1 vs the reference so scores
    move with answer content, without any API call."""
    fuzz = compute_fuzzy_correctness(answer, expected)
    overall = max(0, min(10, round(fuzz * 13)))
    return {
        "correctness": overall,
        "completeness": max(0, min(10, round(fuzz * 12))),
        "overall": overall,
        "quality_pass": overall >= 6,
        "quality_notes": f"[mock] token-F1={fuzz:.2f}",
        "input_tokens": 0,
        "output_tokens": 0,
    }
