#!/usr/bin/env python3
"""
run.py: Symmetric-instrumentation fixture evaluation.

For each fixture: evaluate the flawed baseline over N samples, optimize it to a
SEPARATE file, evaluate the optimized skill over N samples, and report before/after
with mean ± 95% CI. tool_use_rate and doc_grounding are measured from a real
tool-execution loop, and perf inputs come from the observed trace.

Usage:
  python eval_harness/run.py --mock                 # no API calls, smoke test
  python eval_harness/run.py --samples 8            # real run (needs ANTHROPIC_API_KEY)
  python eval_harness/run.py --fixtures quality-regression-trap serial-scriptless

Env: ANTHROPIC_API_KEY, and optionally EVAL_MODEL / JUDGE_MODEL / OPTIMIZER_MODEL.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import metrics
import stats
from agent_loop import run_agent_mock, run_agent_real
from fixtures import FIXTURES, MOCK_SCRIPTS
from judge import llm_judge, mock_judge
from optimizer import optimize_mock, optimize_real
from tools import ToolContext

LOG = logging.getLogger("eval_harness")

ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = ROOT / "fixtures"


def configure_logging(level: str = "INFO", log_file: str | None = None) -> None:
    """Configure the harness logger with a console handler and an optional file
    handler. Idempotent: repeated calls replace existing handlers so re-invoking
    run() in-process does not duplicate log lines."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    LOG.setLevel(numeric_level)
    LOG.handlers.clear()
    LOG.propagate = False

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    console = logging.StreamHandler(stream=sys.stderr)
    console.setLevel(numeric_level)
    console.setFormatter(fmt)
    LOG.addHandler(console)

    if log_file:
        path = Path(log_file).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path, encoding="utf-8")
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(fmt)
        LOG.addHandler(file_handler)
        LOG.info("logging to file: %s", path)

# Cheapest capable default keeps run cost low; bump to claude-sonnet-5 for the
# headline paper run. Prices below are approximate ($/M tokens) and overridable.
DEFAULT_MODEL = os.getenv("EVAL_MODEL", "claude-sonnet-5")
JUDGE_MODEL = os.getenv("JUDGE_MODEL", DEFAULT_MODEL)
OPTIMIZER_MODEL = os.getenv("OPTIMIZER_MODEL", DEFAULT_MODEL)

PRICING = {
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "claude-sonnet-5": {"input": 3.00, "output": 15.00},
    "claude-opus-4-8": {"input": 15.00, "output": 75.00},
}


def est_cost(model: str, in_tok: int, out_tok: int) -> float:
    r = PRICING.get(model, {"input": 3.00, "output": 15.00})
    return (in_tok * r["input"] + out_tok * r["output"]) / 1_000_000


def make_ctx(fixture_name: str, fixture_def: dict, run_tag: str, variant: str, sample: int) -> ToolContext:
    allowed = FIXTURES_DIR / fixture_def["backing_subdir"]
    sandbox = ROOT / "outputs" / "sandbox" / run_tag / fixture_name / variant / f"s{sample}"
    return ToolContext(allowed_root=allowed, output_sandbox=sandbox)


def eval_one_sample(fixture_name, fixture_def, skill_text, variant, sample, client, mock, run_tag,
                    max_iters=30, max_tokens=3000) -> dict:
    ctx = make_ctx(fixture_name, fixture_def, run_tag, variant, sample)
    task = fixture_def["benchmark_task"]
    expected = fixture_def["expected_answer"]
    requires_tools = fixture_def["requires_tools"]

    if mock:
        run = run_agent_mock(MOCK_SCRIPTS[fixture_name][variant], ctx)
    else:
        run = run_agent_real(client, DEFAULT_MODEL, skill_text, task,
                             fixture_def["tool_names"], ctx,
                             max_iters=max_iters, max_tokens=max_tokens)

    ans = run.final_text
    # File-output fixtures: fold the written deliverable into the scored answer so a
    # correct file is not scored as an empty answer just because the agent ended on a
    # tool call rather than a closing text message.
    out_file = fixture_def.get("output_file")
    if out_file:
        fp = ctx.output_sandbox / Path(out_file).name
        if fp.exists():
            content = fp.read_text(encoding="utf-8", errors="replace")[:4000]
            ans = (ans + f"\n\n[Deliverable file {out_file}]:\n{content}").strip() if ans else content

    citation = metrics.compute_citation_score(ans)
    hallucination = metrics.compute_hallucination_risk(ans, run.tool_called, requires_tools)
    length = metrics.compute_answer_length_score(ans)
    fuzzy = metrics.compute_fuzzy_correctness(ans, expected)
    tool_use_rate = metrics.compute_tool_use_rate(run.tool_called)
    grounding = metrics.compute_doc_grounding(run.retrieved_doc_ids, fixture_def["relevant_doc_ids"])

    if mock:
        jd = mock_judge(task, expected, ans)
    else:
        jd = llm_judge(client, JUDGE_MODEL, task, expected, ans)

    quality_score = metrics.compute_quality_score(
        tool_use_rate=tool_use_rate,
        citation_score=citation,
        hallucination_risk=hallucination,
        doc_grounding=grounding,
        fuzzy_correctness=fuzzy,
        judge_overall=jd["overall"],
    )
    perf_score = metrics.compute_perf_score(run.wall_clock_s, run.num_tool_calls,
                                            run.files_read, run.bytes_read)
    total_in = run.input_tokens + jd.get("input_tokens", 0)
    total_out = run.output_tokens + jd.get("output_tokens", 0)

    return {
        "fixture": fixture_name, "variant": variant, "sample": sample,
        "perf_score": round(perf_score, 3), "quality_score": quality_score,
        "quality_pass": jd["quality_pass"],
        "tool_use_rate": tool_use_rate, "doc_grounding": grounding,
        "citation_score": citation, "hallucination_risk": hallucination,
        "answer_length_score": length, "fuzzy_correctness": fuzzy,
        "judge_correctness": jd["correctness"], "judge_completeness": jd["completeness"],
        "judge_overall": jd["overall"], "quality_notes": jd["quality_notes"],
        "num_tool_calls": run.num_tool_calls, "files_read": run.files_read,
        "bytes_read": run.bytes_read, "wall_clock_s": round(run.wall_clock_s, 3),
        "retrieved_doc_ids": run.retrieved_doc_ids,
        "input_tokens": run.input_tokens, "output_tokens": run.output_tokens,
        "estimated_cost_usd": round(est_cost(DEFAULT_MODEL, total_in, total_out), 8),
        "error": run.error, "answer": ans,
    }


_AGG_KEYS = ["perf_score", "quality_score", "tool_use_rate", "doc_grounding",
             "fuzzy_correctness", "hallucination_risk", "judge_overall",
             "num_tool_calls", "files_read"]


def summarize(samples: list[dict]) -> dict:
    out = {}
    for k in _AGG_KEYS:
        vals = [s[k] for s in samples if s.get(k) is not None]
        out[f"{k}_mean"] = stats.aggregate(vals).mean if vals else None
        out[f"{k}_agg"] = stats.aggregate(vals).as_dict() if vals else None
    valid_pass = [s for s in samples if s["quality_pass"] is not None]
    passes = sum(1 for s in valid_pass if s["quality_pass"])
    out["quality_pass_rate"] = round(passes / len(valid_pass), 3) if valid_pass else None
    out["judge_failures"] = sum(1 for s in samples if s["judge_overall"] is None)
    out["truncated"] = sum(1 for s in samples if (s.get("error") or "").startswith("hit_max_iters"))
    return out


def run(args) -> None:
    LOG.info("=== eval_harness startup ===")
    LOG.debug("parsed args: %s", vars(args))
    LOG.info("repo root: %s", ROOT)
    LOG.info("fixtures dir: %s", FIXTURES_DIR)
    if not FIXTURES_DIR.is_dir():
        LOG.warning("fixtures directory does not exist: %s", FIXTURES_DIR)

    mock = args.mock
    LOG.info("mode: %s", "MOCK (no API calls)" if mock else "REAL (Anthropic API)")
    client = None
    if not mock:
        try:
            import anthropic
        except ImportError:
            LOG.error("anthropic SDK not installed; cannot run in REAL mode")
            sys.exit("anthropic not installed. `pip install -r eval_harness/requirements.txt`")
        LOG.debug("anthropic SDK version: %s", getattr(anthropic, "__version__", "unknown"))
        key = os.getenv("ANTHROPIC_API_KEY")
        LOG.info("ANTHROPIC_API_KEY present: %s", bool(key))  # never log the key value itself
        if not key:
            LOG.error("ANTHROPIC_API_KEY not set; aborting REAL run")
            sys.exit("ANTHROPIC_API_KEY not set. Export it or use --mock.")
        client = anthropic.Anthropic(api_key=key)
        LOG.info("Anthropic client initialized")

    run_tag = args.run_tag or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    names = args.fixtures or list(FIXTURES.keys())
    unknown = [n for n in names if n not in FIXTURES]
    if unknown:
        LOG.warning("ignoring unknown fixtures not in registry: %s", unknown)
        names = [n for n in names if n in FIXTURES]
    all_samples: list[dict] = []
    summary_rows: list[dict] = []

    LOG.info("run_tag: %s", run_tag)
    LOG.info("models: eval=%s judge=%s optimizer=%s", DEFAULT_MODEL, JUDGE_MODEL, OPTIMIZER_MODEL)
    LOG.info("fixtures (%d): %s", len(names), names)
    LOG.info("config: samples=%d max_iters=%d max_tokens=%d",
             args.samples, args.max_iters, args.max_tokens)
    out_dir = ROOT / "outputs" / "fixture_results_v2"
    LOG.info("results will be written under: %s", out_dir)
    LOG.info("=== startup complete; beginning evaluation ===")

    print(f"\n{'='*72}\nSymmetric-instrumentation eval  (run {run_tag}, {'MOCK' if mock else 'REAL'})")
    print(f"  model={DEFAULT_MODEL}  judge={JUDGE_MODEL}  optimizer={OPTIMIZER_MODEL}")
    print(f"  fixtures={names}  samples={args.samples}\n{'='*72}")

    for name in names:
        fd = FIXTURES[name]
        baseline_skill = (FIXTURES_DIR / fd["backing_subdir"] / "SKILL.md").read_text(encoding="utf-8")
        print(f"\n── {name} ──")

        # Baseline
        base_samples = [eval_one_sample(name, fd, baseline_skill, "baseline", i, client, mock, run_tag,
                                       args.max_iters, args.max_tokens)
                        for i in range(args.samples)]
        all_samples += base_samples
        base_sum = summarize(base_samples)
        print(f"  baseline : perf={base_sum['perf_score_mean']:.1f}  "
              f"quality={base_sum['quality_score_mean']:.1f}  "
              f"tool_use={base_sum['tool_use_rate_mean']:.2f}  "
              f"grounding={base_sum['doc_grounding_mean']}  "
              f"pass_rate={base_sum['quality_pass_rate']}")

        # Optimize (writes to a separate path; baseline untouched)
        if mock:
            opt_skill, opt_path, _ = optimize_mock(ROOT, run_tag, name, fd, baseline_skill)
        else:
            opt_skill, opt_path, _ = optimize_real(client, OPTIMIZER_MODEL, ROOT, run_tag, name, fd,
                                                   baseline_skill, base_sum)

        # Optimized
        opt_samples = [eval_one_sample(name, fd, opt_skill, "optimized", i, client, mock, run_tag,
                                       args.max_iters, args.max_tokens)
                       for i in range(args.samples)]
        all_samples += opt_samples
        opt_sum = summarize(opt_samples)
        print(f"  optimized: perf={opt_sum['perf_score_mean']:.1f}  "
              f"quality={opt_sum['quality_score_mean']:.1f}  "
              f"tool_use={opt_sum['tool_use_rate_mean']:.2f}  "
              f"grounding={opt_sum['doc_grounding_mean']}  "
              f"pass_rate={opt_sum['quality_pass_rate']}")

        summary_rows.append({"fixture": name, "baseline": base_sum, "optimized": opt_sum,
                             "optimized_skill_path": str(opt_path.relative_to(ROOT))})

    _print_scorecard(summary_rows)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"results_{run_tag}{'_mock' if mock else ''}.json"
    out_path.write_text(json.dumps(
        {"run_tag": run_tag, "mock": mock, "model": DEFAULT_MODEL, "samples": args.samples,
         "summary": summary_rows, "samples_raw": all_samples}, indent=2), encoding="utf-8")
    LOG.info("evaluation complete: %d fixtures, %d total samples", len(summary_rows), len(all_samples))
    LOG.info("results saved: %s", out_path)
    print(f"\nResults saved → {out_path.relative_to(ROOT)}")


def _fmt_ci(agg: dict | None) -> str:
    if not agg:
        return "   n/a   "
    return f"{agg['mean']:6.1f}±{agg['ci95_high']-agg['mean']:4.1f}"


def _print_scorecard(rows: list[dict]) -> None:
    W = 104
    print("\n" + "=" * W)
    print("SCORECARD  (mean ± 95% CI; perf & quality include live tool_use / grounding)")
    print("=" * W)
    print(f"{'Fixture':<26}{'variant':<10}{'perf':>13}{'quality':>13}{'tool_use':>10}{'grounding':>11}{'pass':>7}")
    print("-" * W)
    agg_perf = {"baseline": [], "optimized": []}
    agg_qual = {"baseline": [], "optimized": []}
    for r in rows:
        for v in ("baseline", "optimized"):
            s = r[v]
            flags = ""
            if s.get("truncated"):
                flags += f" !{s['truncated']}trunc"
            if s.get("judge_failures"):
                flags += f" !{s['judge_failures']}judgefail"
            pr = s["quality_pass_rate"]
            pr_s = f"{pr:>7.2f}" if pr is not None else f"{'n/a':>7}"
            print(f"{r['fixture']:<26}{v:<10}"
                  f"{_fmt_ci(s['perf_score_agg']):>13}{_fmt_ci(s['quality_score_agg']):>13}"
                  f"{(s['tool_use_rate_mean'] or 0):>10.2f}"
                  f"{(s['doc_grounding_mean'] if s['doc_grounding_mean'] is not None else -1):>11.2f}"
                  f"{pr_s}{flags}")
            if s["perf_score_mean"] is not None:
                agg_perf[v].append(s["perf_score_mean"])
                agg_qual[v].append(s["quality_score_mean"])
        print()
    print("-" * W)
    for v in ("baseline", "optimized"):
        p, q = agg_perf[v], agg_qual[v]
        if p:
            print(f"{'AGGREGATE MEAN':<26}{v:<10}{sum(p)/len(p):>13.1f}{sum(q)/len(q):>13.1f}")
    print("=" * W)
    print("grounding = -1.00 means N/A (self-contained fixture, no relevant docs).")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true", help="no API calls; scripted behavior")
    ap.add_argument("--samples", type=int, default=5, help="samples per variant per fixture")
    ap.add_argument("--fixtures", nargs="*", help="subset of fixture names")
    ap.add_argument("--run-tag", help="override run tag (for deterministic output paths)")
    ap.add_argument("--max-iters", type=int, default=30,
                    help="max model turns per agent run (raise for wasteful skills like serial baseline)")
    ap.add_argument("--max-tokens", type=int, default=3000, help="max_tokens per model call")
    ap.add_argument("--log-level", default=os.getenv("EVAL_LOG_LEVEL", "INFO"),
                    choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                    help="console/file log verbosity (default INFO; env EVAL_LOG_LEVEL)")
    ap.add_argument("--log-file", default=os.getenv("EVAL_LOG_FILE"),
                    help="optional path to also write logs to (env EVAL_LOG_FILE)")
    args = ap.parse_args()
    configure_logging(args.log_level, args.log_file)
    run(args)


if __name__ == "__main__":
    main()
