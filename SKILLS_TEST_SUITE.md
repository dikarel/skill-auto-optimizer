# Skills Test Suite

This document defines a small fixture suite for evaluating `skill-auto-optimizer`.

Use these fixtures to test two things:
- the optimizer can identify missing instrumentation and propose targeted fixes
- approved optimization passes improve measured performance without breaking quality

Do not treat this suite as the production metric spec. The optimizer's real skill-level metric contract belongs in:
- `skill-auto-optimizer/specs/PERF_METRIC_SPEC.md`
- `skill-auto-optimizer/specs/QUALITY_METRIC_SPEC.md`

Until those specs are filled in, this suite uses a temporary harness-level scorecard so iteration-to-iteration improvement can still be measured.

## Fixture Set

Create one temporary skill per fixture under a disposable directory such as `tmp/test-skills/`.

### `fixture-chatty-reference-loader`

Intent:
- Simulate a skill with poor progressive disclosure and excessive file reading.

Seed defects:
- `SKILL.md` tells the agent to read every reference file before doing any work.
- Add 3 to 5 large reference files, but only 1 is needed for the benchmark task.
- Include repetitive instructions and duplicate examples.
- Emit no performance metrics.

Benchmark task:
- Ask the skill to answer a simple question that only requires one reference file.

Expected optimizer proposals:
- tighten trigger/selection guidance
- reduce eager reference loading
- add instrumentation
- move repeated logic into smaller reusable files if needed

### `fixture-serial-scriptless`

Intent:
- Simulate a skill that performs repetitive shell work manually and slowly.

Seed defects:
- `SKILL.md` describes a multi-step process that repeatedly scans the same files.
- No helper script exists even though the operation is deterministic.
- Instructions prefer sequential loops even when safe batched work is possible.
- Emit no performance metrics.

Benchmark task:
- Ask the skill to summarize a synthetic directory of many small files.

Expected optimizer proposals:
- add a bundled script for deterministic repeated work
- reduce repeated scans
- improve file-selection guidance
- add instrumentation

### `fixture-missing-metrics`

Intent:
- Simulate a skill with acceptable instructions but no logging or eval path.

Seed defects:
- `SKILL.md` has no mention of quality metrics, performance metrics, or logs.
- No `scripts/` or `references/` support evaluation.
- No per-skill recent logs exist.

Benchmark task:
- Ask the skill to perform a short task twice so the optimizer can detect the missing baseline path.

Expected optimizer proposals:
- add instrumentation hooks
- add a starter eval or benchmark path
- define where recent metrics should come from once the real specs exist

### `fixture-quality-regression-trap`

Intent:
- Prevent false wins where performance improves only because the skill becomes too shallow.

Seed defects:
- `SKILL.md` contains an intentionally lossy shortcut such as "prefer brief answers even if some edge cases are omitted."
- Existing output examples are fast but incomplete.
- Emit no performance metrics.

Benchmark task:
- Ask the skill to solve a task with an obvious edge case that must be preserved.

Expected optimizer proposals:
- keep or improve correctness while improving efficiency
- add explicit quality guardrails
- add instrumentation so fast-but-wrong outputs do not score as wins

## Harness-Level Scorecard

Use this temporary scorecard for the test suite until the real spec files are filled in.

Collect per benchmark run:
- `iteration`
- `skill`
- `run_id`
- `wall_clock_s`
- `tool_calls`
- `files_read`
- `bytes_read`
- `quality_pass`
- `quality_notes`

Compute a temporary performance score per run:

`perf_score = 1000 / (1 + wall_clock_s + 0.25 * tool_calls + 0.01 * files_read + 0.0001 * bytes_read)`

Rules:
- A run only counts as improved if `quality_pass = true`.
- Report both per-skill score and aggregate mean score.
- The primary success criterion is monotonic improvement in aggregate mean performance score across approved iterations.
- A single skill may stall, but the aggregate should not regress.

## Minimum Evidence Standard

For each fixture skill:
- record a baseline before any optimizer-approved edits
- run at least 5 benchmark repetitions per iteration
- complete at least 3 approved optimization iterations

For the overall suite:
- show per-skill and aggregate score trends
- keep raw results in a CSV so the graph can be regenerated
- note any proposal that was rejected by the human, since approval gates affect the outcome
