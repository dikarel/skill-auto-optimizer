# Symmetric-Instrumentation Eval Harness

An evaluation harness for the Skillception skill-auto-optimizer study. It measures
skill **quality** and **efficiency** on equal footing by running each skill in a real
tool-execution loop, so that tool use and document grounding are *observed* rather
than assumed.

## What it measures

The quality composite (0–100) ranks tool use and grounding as its highest-priority
dimension (35 of 100 points). To score that dimension honestly, the harness rests on
three requirements:

1. **Tools execute for real.** Each skill runs in a genuine tool-use loop: the agent
   calls the fixture's bound tools, results are returned, and the loop continues until
   a final answer. `tool_use_rate` and `doc_grounding` are computed from what the
   agent actually did, not assumed.
2. **Variance is reported.** Every (fixture, variant) is evaluated over N samples with
   95% confidence intervals, so run-to-run noise is visible rather than mistaken for
   signal.
3. **Baselines are never overwritten.** The optimizer writes the optimized skill to a
   separate path; the flawed baseline is immutable, so any run is reproducible from the
   same starting point.

## What's here

```
eval_harness/
  run.py          # orchestration: baseline vs optimized, N samples, CIs, scorecard
  agent_loop.py   # real Anthropic tool-use loop (+ deterministic mock path)
  tools.py        # sandboxed, deterministic tools + backing-data providers
  metrics.py      # quality/perf metrics, incl. live tool_use_rate & doc_grounding
  judge.py        # LLM judge (+ deterministic mock judge)
  fixtures.py     # fixture registry + ground-truth doc IDs + mock scripts
  optimizer.py    # writes the optimized skill to a SEPARATE path (never the baseline)
  stats.py        # mean / std / 95% CI
../fixtures/      # the four flawed baselines + their backing data
```

## Run it

Smoke test (no API key, no cost, validates the whole pipeline):

```bash
python eval_harness/run.py --mock --samples 3
```

Real run:

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
each file twice ≈ 21 tool calls) needs a high `--max-iters` to finish; if it runs out
of turns the run is flagged (`error="hit_max_iters"`, a `!Ntrunc` mark in the
scorecard, counted in `summary[...]["truncated"]`). If you see truncation on a
baseline, raise `--max-iters` and re-run so you measure the skill's true (slow)
behavior rather than a truncated failure. Default 30 clears the serial baseline; check
the flag if you add heavier fixtures.

**Judge failures.** If the LLM judge returns an unparseable reply, that sample's judge
scores are recorded as `null` and EXCLUDED from the averages (not scored 0). Such
samples are counted in `summary[...]["judge_failures"]` and marked `!Njudgefail` in the
scorecard. A high count means the judge prompt/parse needs attention, not that quality
dropped.

**File-deliverable fixtures.** A fixture may declare an `output_file`; if so, the
written file's contents are folded into what the judge scores, so a correct deliverable
isn't scored as an empty answer when the agent ends on a tool call. (No fixture in the
current four-fixture suite uses this; the capability remains for future file-output
fixtures.)

Outputs land in `outputs/fixture_results_v2/results_<tag>.json` (per-sample raw +
aggregates with CIs) and the optimized skills in `outputs/optimized/<tag>/`.

## Cost

One real run = `4 fixtures × 2 variants × N samples` agent runs (each possibly
multi-turn for tool use) + one judge call per sample + one optimizer call per fixture.
At `--samples 8` that is on the order of ~140 model calls. Start with `--samples 3` on
Haiku to gauge spend, then scale up on Sonnet for the headline run.

## Notes

- **Baselines** in `../fixtures/` are authored to embody the documented seed defects,
  and the optimizer never overwrites them.
- **Mock numbers are illustrative only.** `--mock` runs scripted behavior to validate
  the plumbing without API calls; only real-run numbers are reported.
