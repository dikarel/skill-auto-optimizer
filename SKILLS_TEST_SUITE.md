# Skills Test Suite

This document defines a small fixture suite for evaluating `skill-auto-optimizer`.

Use these fixtures to test two things:
- the optimizer can identify missing instrumentation and propose targeted fixes
- approved optimization passes improve measured performance without breaking quality

Do not treat this suite as the production metric spec. The optimizer's real skill-level metric contract belongs in:
- `skill-auto-optimizer/perf_optimization/PERF_METRIC_SPEC.md`
- `skill-auto-optimizer/quality_optimization/QUALITY_METRIC_SPEC.md`

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

### `fixture-travel-planning`

Intent:
- Simulate a skill that handles a multi-constraint planning task without tool use
  guidance, causing the agent to answer from memory instead of searching real-world
  data, and to silently drop hard constraints like pet-friendly accommodations,
  no-flight travel, and budget limits.

Seed defects:
- `SKILL.md` describes the planning task in prose but does not instruct the agent
  to call any search tools before constructing the itinerary.
- No guidance exists on which search skills to call or in what order
  (e.g., `search_cities`, `search_accommodations`, `search_restaurants`,
  `search_attractions`).
- Instructions do not mention hard constraints explicitly (no flights, pet-friendly,
  budget cap) as blocking requirements — they are buried or softened.
- Output format requirements (exact JSON schema, 7 day objects, required fields)
  are not specified, causing the agent to produce freeform text or incomplete JSON.
- Emit no performance metrics.

Benchmark task:
- Ask the skill to build a 7-day itinerary for two travelers leaving from
  Minneapolis, covering three cities in Ohio, March 17–23 2022, budget $5,100,
  pet-friendly accommodations, no flights, preferred cuisines American /
  Mediterranean / Chinese / Italian. Produce output at `/app/output/itinerary.json`.

The three failure modes and the stage at which each surfaces:

| Stage | Failure mode | Signal |
|---|---|---|
| Data sourcing | Agent answers from memory, no search tools called | `tool_called` array empty or absent |
| Constraint satisfaction | Flight legs present, non-pet-friendly hotels, budget exceeded | Hard constraint fields violated |
| Output schema | Missing required fields, fewer than 7 day objects, malformed JSON | JSON parse error or schema diff |

Expected optimizer proposals:
- add explicit instruction to call search tools before constructing any part of the itinerary
- list the required search skills by name and specify the order: cities → accommodations → restaurants → attractions
- promote no-flights, pet-friendly, and budget constraints to a clearly labeled hard constraints section
- add the exact required JSON schema with field names, types, and an example day object
- add a self-check step: verify all 7 days are present, no flights appear, all accommodations are pet-friendly, and cumulative cost is within budget before writing the file
- add instrumentation so tool call count and constraint satisfaction are measurable

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
