# Test Plan

This document describes how to evaluate `skill-auto-optimizer` against the
intentionally flawed sample skills and show that approved optimization passes improve
measured quality and efficiency.

The fixtures are defined in [SKILLS_TEST_SUITE.md](./SKILLS_TEST_SUITE.md) and live
under [`fixtures/`](./fixtures/). The evaluation is implemented by the harness in
[`eval_harness/`](./eval_harness/).

## Goal

Demonstrate that:
- the optimizer detects missing instrumentation and optimization opportunities
- human-approved changes improve measured quality without regressing it
- efficiency is measured on equal footing with quality, so a fast-but-shallow rewrite
  cannot score as a win

## How the harness runs

For each fixture the harness:
1. evaluates the flawed baseline (`fixtures/<name>/SKILL.md`) over N samples
2. runs the optimizer, which writes the optimized skill to a separate path under
   `outputs/optimized/<run-tag>/` and never overwrites the baseline
3. evaluates the optimized skill over N samples
4. reports baseline vs optimized quality and perf as mean plus 95% confidence interval

Each sample runs the skill in a real tool-execution loop, so `tool_use_rate` and
`doc_grounding` are computed from what the agent actually did. See
[`eval_harness/README.md`](./eval_harness/README.md) for metric details.

## Running it

Smoke test (no API key, no cost):

```bash
python eval_harness/run.py --mock --samples 3
```

Real run:

```bash
pip install -r eval_harness/requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python eval_harness/run.py --samples 8
```

Useful flags: `--fixtures <names>` (subset), `--run-tag <tag>` (deterministic output
dir), `--max-iters` and `--max-tokens` (agent-loop limits). Models are set via
`EVAL_MODEL` / `JUDGE_MODEL` / `OPTIMIZER_MODEL`.

## Reading the results

The scorecard prints per-fixture and aggregate quality and perf with confidence
intervals, plus the live tool-use and grounding rates and the judge pass-rate. Watch
for `!Ntrunc` (a run exhausted the tool-call turn cap; raise `--max-iters` and re-run)
and `!Njudgefail` (an unparseable judge reply, excluded from averages rather than
scored zero).

Raw per-sample records and aggregates are written to
`outputs/fixture_results_v2/results_<tag>.json`, and the optimized skills to
`outputs/optimized/<tag>/`. Keep these as the audit trail.

## The approval gate

`skill-auto-optimizer` stays read-only until a human approves edits for a specific
skill, and stays read-only for tests, benchmarks, and script execution until those are
approved for that same skill. In the harness, the optimizer produces its rewrite on a
separate path so a reviewer can inspect the proposed diff before anything is applied.
Note any proposal a human rejected, since the per-skill approval gate affects outcomes.
