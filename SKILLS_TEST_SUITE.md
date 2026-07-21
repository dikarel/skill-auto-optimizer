# Skills Test Suite

This document defines the fixture suite for evaluating `skill-auto-optimizer`.

The fixtures test two things:
- the optimizer can identify missing instrumentation and propose targeted fixes
- approved optimization passes improve measured performance without breaking quality

The suite is implemented and run by the harness in [`eval_harness/`](./eval_harness/),
which scores each fixture against the metrics defined in
`skill-auto-optimizer/perf_optimization/PERF_METRIC_SPEC.md` and
`skill-auto-optimizer/quality_optimization/QUALITY_METRIC_SPEC.md`. The flawed
baselines and their backing data live under [`fixtures/`](./fixtures/).

## Fixture Set

Each fixture is a flawed baseline skill (`fixtures/<name>/SKILL.md`) plus any backing
data its benchmark needs.

### `chatty-reference-loader`

Intent:
- Simulate a skill with poor progressive disclosure and excessive file reading.

Seed defects:
- `SKILL.md` tells the agent to read every reference file before doing any work.
- Five reference files exist (`fixtures/chatty-reference-loader/references/`), but the
  benchmark question needs only one.
- Instructions are repeated.
- Emits no performance metrics.

Benchmark task:
- Answer a question (the public API rate limit) that requires only `ref_api.md`.

Expected optimizer proposals:
- tighten trigger/selection guidance and load only the relevant reference
- add instrumentation

### `serial-scriptless`

Intent:
- Simulate a skill that performs repetitive work manually and slowly.

Seed defects:
- `SKILL.md` mandates sequential per-file reads plus a full second verification pass,
  and bans batching. For a 10-file directory this is roughly 21 tool calls.
- Emits no performance metrics.

Benchmark task:
- Summarize the 10 small files in `fixtures/serial-scriptless/logs_dir/`.

Expected optimizer proposals:
- replace the serial-plus-verification loop with a single batched read
- reduce redundant scans
- add instrumentation

### `missing-metrics`

Intent:
- Simulate a skill with acceptable instructions but no logging or eval path.

Seed defects:
- `SKILL.md` has no mention of quality metrics, performance metrics, or logs.
- No evaluation support and no recent logs.

Benchmark task:
- Summarize self-contained quarterly sales figures provided in the prompt (no tools
  needed).

Expected optimizer proposals:
- add instrumentation hooks
- add a starter eval or benchmark path

### `quality-regression-trap`

Intent:
- Prevent false wins where performance improves only because the skill becomes too
  shallow.

Seed defects:
- `SKILL.md` instructs "prefer brief answers, skip edge cases," and names the exact
  benchmark case as an edge case to omit.
- Emits no performance metrics.

Benchmark task:
- Answer a billing question whose correct answer lives in the knowledge base
  (`fixtures/quality-regression-trap/kb/`): what happens to an active subscription
  with zero transactions at the next billing cycle.

Expected optimizer proposals:
- mandate retrieval before answering and cite the source policy
- preserve every edge case rather than omitting them for brevity
- add instrumentation so fast-but-incomplete answers do not score as wins

## Scoring

The harness scores each benchmark run on two axes.

**Quality** is a 0-100 composite (`QUALITY_METRIC_SPEC.md`) over live signals from a
real tool-execution loop: `tool_use_rate`, `doc_grounding` (fraction of a fixture's
ground-truth relevant documents actually retrieved), citation, hallucination risk,
token-overlap correctness, and an LLM-judge score. Tool use and grounding are the
highest-priority dimension (35 of 100 points).

**Performance** is the harness perf score:

`perf_score = 1000 / (1 + wall_clock_s + 0.25 * tool_calls + 0.01 * files_read + 0.0001 * bytes_read)`

whose inputs come from the observed execution trace.

Report both per-fixture and aggregate means. Optimization should raise quality without
a regression; efficiency is assessed alongside it, noting that grounding-related tool
calls carry a perf cost by construction.

## Evidence Standard

For each fixture:
- record a baseline before any optimizer-approved edits
- run N samples per variant (default 8) and report mean plus 95% confidence interval
- keep the optimized skill on a separate path so the baseline stays reproducible

For the overall suite:
- report per-fixture and aggregate quality and perf
- keep raw per-sample results (`outputs/fixture_results_v2/`) as the audit trail
- note any proposal a human rejected, since the per-skill approval gate affects outcomes
