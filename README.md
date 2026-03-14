# skill-auto-optimizer

Ask your coding agent to install this skill from GitHub:

```text
Use the skill-installer to install https://github.com/dikarel/skill-auto-optimizer/tree/main/skill-auto-optimizer and then restart Codex so the new skill is loaded.
```

Equivalent installer command:

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --url https://github.com/dikarel/skill-auto-optimizer/tree/main/skill-auto-optimizer
```

Restart Codex after installation so the new skill is picked up.

## What This Skill Is

`skill-auto-optimizer` is a meta-skill for reviewing and improving other local filesystem Codex skills.

It is intended to:
- inspect installed skills, skipping `~/.codex/skills/.system` by default
- ensure each skill emits both performance and quality metrics during usage
- look at recent per-skill logs
- propose targeted optimizations to `SKILL.md`, scripts, references, agent metadata, and new helper files
- stay read-only until a human explicitly approves edits for that specific skill
- stay read-only for tests, benchmarks, and script execution until a human explicitly approves those runs for that specific skill

The optimizer works per skill, not as a global batch approval flow.

## Repo Layout

- `skill-auto-optimizer/SKILL.md`: primary skill instructions
- `skill-auto-optimizer/perf_optimization/`: performance metric and objective specs
- `skill-auto-optimizer/quality_optimization/`: quality metric and objective specs
- `SKILLS_TEST_SUITE.md`: intentionally flawed sample-skill fixtures for evaluation
- `TEST.md`: iterative evaluation plan and graphing workflow

## Contributor Structure Guide

For contributors and coding agents, the repo is split into two layers:

- repo support files at the root
- the installable skill under `skill-auto-optimizer/`

How to think about each area:
- `README.md`: contributor-facing overview, install instructions, and repo map
- `skill-auto-optimizer/`: the actual shipped skill directory that gets installed into a Codex skills folder
- `skill-auto-optimizer/SKILL.md`: the runtime entrypoint; keep this concise and use it to point to deeper docs rather than stuffing everything into one file
- `skill-auto-optimizer/perf_optimization/`: performance-specific standards and optimization objectives
- `skill-auto-optimizer/quality_optimization/`: quality-specific standards and optimization objectives
- `SKILLS_TEST_SUITE.md`: defines the sample broken skills used to evaluate optimizer behavior
- `TEST.md`: explains how to run repeated optimization passes and graph improvement over time

Contributor expectations:
- if a change affects runtime behavior, update files under `skill-auto-optimizer/`
- if a change affects how the skill is evaluated, update `SKILLS_TEST_SUITE.md` or `TEST.md`
- if a change affects onboarding or installation, update `README.md`
- keep performance and quality material separated unless a cross-cutting rule genuinely belongs in `SKILL.md`

## Current State

The performance and quality spec documents are still stubs. The skill workflow is defined, but the concrete metric schema and optimization objective details still need to be filled in.
