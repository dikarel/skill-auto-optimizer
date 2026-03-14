# Test Plan

This document describes how to evaluate `skill-auto-optimizer` with intentionally flawed sample skills and show that approved optimization passes improve measured performance over multiple iterations.

Use [SKILLS_TEST_SUITE.md](./SKILLS_TEST_SUITE.md) as the fixture definition and temporary scoring contract.

## Goal

Demonstrate that:
- the optimizer detects missing instrumentation and optimization opportunities
- human-approved changes improve measured performance over successive iterations
- quality does not regress while performance improves

## Setup

1. Create a disposable fixture root such as `tmp/test-skills/`.
2. For each fixture in `SKILLS_TEST_SUITE.md`, create one local skill directory with:
   - `SKILL.md`
   - optional `references/`, `scripts/`, or `agents/` content needed to express the seeded defect
   - enough synthetic content to make the benchmark measurable
3. Keep the fixture skills isolated from `~/.codex/skills/.system`.
4. Create a results directory such as `tmp/test-results/`.
5. Create an empty CSV at `tmp/test-results/results.csv` with this header:

```csv
iteration,skill,run_id,wall_clock_s,tool_calls,files_read,bytes_read,quality_pass,quality_notes,perf_score
```

## Creating the Sample Skills

Use the fixture definitions in `SKILLS_TEST_SUITE.md` exactly. The suite is intentionally small; the point is not realism, but repeatable failure modes the optimizer should improve.

For each fixture:
- create the anti-patterns called out in the fixture spec
- keep the skill functional enough to complete its benchmark task
- make the defect obvious enough that an optimization proposal can be evaluated
- do not pre-add instrumentation, benchmark scripts, or quality gates unless the fixture explicitly calls for them

## Baseline Pass

1. Run each fixture skill on its benchmark task 5 times before any optimizer changes.
2. Record one row per run in `results.csv`.
3. Compute `perf_score` using the formula in `SKILLS_TEST_SUITE.md`.
4. Mark `quality_pass` manually or with a lightweight eval harness.
5. Treat any run with `quality_pass = false` as a failed baseline, not a valid performance datapoint.

## Optimization Loop

Repeat the following loop for at least 3 iterations.

1. Run the optimizer in read-only proposal mode against the fixture root.
2. Review proposals per skill.
3. Approve or reject changes separately for each skill.
4. Apply only the approved edits for that skill.
5. If verification requires running scripts, benchmarks, or tests, approve execution separately for that same skill.
6. Re-run the benchmark task 5 times per approved skill.
7. Append all new rows to `results.csv`.
8. Recompute per-skill and aggregate mean `perf_score`.
9. Stop if aggregate mean `perf_score` regresses or if quality regresses.

Use a separate notes file if needed to capture:
- which proposals were approved
- which proposals were rejected
- why any iteration was skipped or rerun

## Required Outcome

The suite passes when all of the following are true:
- aggregate mean `perf_score` improves every completed iteration
- no accepted iteration introduces a quality regression
- each fixture skill receives at least one concrete instrumentation proposal
- skills with no logs receive both instrumentation and starter benchmark/eval proposals

## Graph

Render a line chart from `results.csv` with:
- one line per skill
- one thicker aggregate mean line
- x-axis as `iteration`
- y-axis as mean `perf_score`
- markers at each iteration
- a subtitle that notes how many runs were averaged per point

Example plotting script:

```python
import csv
from collections import defaultdict

import matplotlib.pyplot as plt

rows = []
with open("tmp/test-results/results.csv", newline="") as f:
    for row in csv.DictReader(f):
        if row["quality_pass"].lower() != "true":
            continue
        rows.append({
            "iteration": int(row["iteration"]),
            "skill": row["skill"],
            "perf_score": float(row["perf_score"]),
        })

series = defaultdict(list)
aggregate = defaultdict(list)
for row in rows:
    series[row["skill"]].append((row["iteration"], row["perf_score"]))
    aggregate[row["iteration"]].append(row["perf_score"])

plt.figure(figsize=(10, 6))
for skill, points in sorted(series.items()):
    by_iter = defaultdict(list)
    for iteration, score in points:
        by_iter[iteration].append(score)
    xs = sorted(by_iter)
    ys = [sum(by_iter[x]) / len(by_iter[x]) for x in xs]
    plt.plot(xs, ys, marker="o", linewidth=2, alpha=0.8, label=skill)

agg_xs = sorted(aggregate)
agg_ys = [sum(aggregate[x]) / len(aggregate[x]) for x in agg_xs]
plt.plot(agg_xs, agg_ys, marker="o", linewidth=4, color="black", label="aggregate mean")

plt.title("Skill Auto Optimizer Performance by Iteration")
plt.suptitle("Mean perf_score over quality-passing runs", y=0.94, fontsize=10)
plt.xlabel("Iteration")
plt.ylabel("Mean perf_score")
plt.grid(alpha=0.25)
plt.legend()
plt.tight_layout()
plt.savefig("tmp/test-results/perf-iterations.png", dpi=180)
```

## Notes

- Replace the optimizer invocation with the real command or prompt once the skill is wired into your runtime.
- Once the production metric specs are written, update this plan to use those official metrics instead of the temporary suite scorecard.
- Keep the raw CSV even if the graph looks good; the CSV is the actual audit trail.
