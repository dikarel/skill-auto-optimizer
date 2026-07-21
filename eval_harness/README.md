# Symmetric-Instrumentation Eval Harness

A rebuilt evaluation harness for the Skillception skill-auto-optimizer study. It
exists to test whether the original hackathon result — *efficiency improved while
quality regressed* — is a real efficiency/quality trade-off or an artifact of
**asymmetric instrumentation**.

## Why this rebuild exists

The original `scripts/run_fixtures.py` had three measurement problems that all
biased toward an apparent trade-off:

1. **35 of 100 quality points were hardcoded to zero.** `tool_use_rate` and
   `doc_grounding` were passed as literal `0.0` for every fixture
   (`run_fixtures.py:506-511`), even though `QUALITY_OBJECTIVE_SPEC.md` ranks
   tool-use/grounding as the **#1** quality objective. Quality collapsed to a mostly
   judge-driven score.
2. **No tools were ever executed.** Evaluation was a single `messages.create` with
   no tools bound, and `tool_called` was hardcoded `False`, so every
   tool-requiring fixture took a flat hallucination penalty and could never earn
   grounding credit.
3. **Run-to-run instability.** Across the three committed result files the "trade-off"
   appears in only one; in another, quality *improved*.

This harness fixes all three: a **real tool-execution loop**, **live tool_use /
doc_grounding**, and **multi-sample runs with 95% confidence intervals**.

## What's here

```
eval_harness/
  run.py          # orchestration: baseline vs optimized, N samples, CIs, scorecard
  agent_loop.py   # real Anthropic tool-use loop (+ deterministic mock path)
  tools.py        # sandboxed, deterministic tools + backing-data providers
  metrics.py      # quality/perf metrics — tool_use & grounding now LIVE, not stubbed
  judge.py        # LLM judge (+ deterministic mock judge)
  fixtures.py     # fixture registry + ground-truth doc IDs + mock scripts
  optimizer.py    # rewrites a flawed skill to a SEPARATE path (never overwrites baseline)
  stats.py        # mean / std / 95% CI
../fixtures/      # RECONSTRUCTED flawed baselines + backing data (see caveat below)
```

## Run it

Smoke test (no API key, no cost — validates the whole pipeline):

```bash
python eval_harness/run.py --mock --samples 3
```

Real run (the paid re-run for the paper):

```bash
pip install -r eval_harness/requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...      # or cp eval_harness/.env.example .env
python eval_harness/run.py --samples 8   # bump samples for tighter CIs
```

Useful flags: `--fixtures quality-regression-trap serial-scriptless` (subset),
`--run-tag <tag>` (deterministic output dir), `--max-iters` (max model turns per
agent run; default 30), `--max-tokens` (default 3000). Models via `EVAL_MODEL` /
`JUDGE_MODEL` / `OPTIMIZER_MODEL` (default `claude-sonnet-5`; set all to
`claude-haiku-4-5-20251001` for a cheaper run).

**Truncation.** A wasteful skill (e.g. the serial-scriptless baseline, which reads
each file twice ≈ 21 tool calls) needs a high `--max-iters` to finish; if it runs
out of turns the run is flagged (`error="hit_max_iters"`, a `!Ntrunc` mark in the
scorecard, counted in `summary[...]["truncated"]`). If you see truncation on a
baseline, raise `--max-iters` and re-run so you measure the skill's true (slow)
behavior rather than a truncated failure. Default 30 clears the serial baseline;
check the flag if you add heavier fixtures.

**Judge failures.** If the LLM judge returns an unparseable reply, that sample's
judge scores are recorded as `null` and EXCLUDED from the averages (not scored 0),
matching the quality spec. Such samples are counted in `summary[...]["judge_failures"]`
and marked `!Njudgefail` in the scorecard. A high count means the judge prompt/parse
needs attention, not that quality dropped.

**File-deliverable fixtures.** A fixture may declare an `output_file`; if so, the
written file's contents are folded into what the judge scores, so a correct
deliverable isn't scored as an empty answer when the agent ends on a tool call. (No
fixture in the current four-fixture suite uses this; the capability remains for
future file-output fixtures.)

Outputs land in `outputs/fixture_results_v2/results_<tag>.json` (per-sample raw +
aggregates with CIs) and the optimized skills in `outputs/optimized/<tag>/`.

## Cost

One real run = `5 fixtures × 2 variants × N samples` agent runs (each possibly
multi-turn for tool use) + one judge call per sample + one optimizer call per
fixture. At `--samples 8` that's on the order of ~170 model calls. Start with
`--samples 3` on Haiku to gauge spend, then scale up on Sonnet for the headline run.

## Two caveats to state in the paper

1. **Reconstructed baselines.** The original optimizer rewrote `SKILL.md` in place,
   so the pristine flawed fixtures were never committed to git. The baselines in
   `../fixtures/` are faithfully reconstructed from the documented seed defects in
   the original `run_fixtures.py`. This harness never overwrites them.
2. **Mock numbers are illustrative only.** `--mock` runs scripted behavior to
   validate plumbing; it is not evidence. Only the real run's numbers go in the paper.
