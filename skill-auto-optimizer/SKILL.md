---
name: skill-auto-optimizer
description: Review local filesystem Codex skills for instrumentation, quality, and performance. Use when a user wants to audit installed skills, ensure they emit quality and performance metrics, inspect recent per-skill logs, and propose read-only optimizations to SKILL.md, scripts, references, agents metadata, or new support files without changing any skill until a human approves that specific skill.
---

# Skill Auto Optimizer

Use this skill when the user wants to review and improve installed local skills.

Default scope:
- Scan local filesystem skills under `~/.codex/skills`.
- Skip `~/.codex/skills/.system` unless the user explicitly overrides that default.
- Accept extra explicit skill paths outside `~/.codex/skills`, including repo-local skills.

Primary responsibilities:
1. Instrumentation review: ensure each target skill emits both performance and quality metrics during usage.
2. Optimization review: inspect recent per-skill metrics and propose improvements against the defined objectives.

References:
- Read `specs/PERF_METRIC_SPEC.md` for the required performance metric contract.
- Read `specs/QUALITY_METRIC_SPEC.md` for the required quality metric contract.
- Read `specs/PERF_OPTIMIZATION_OBJECTIVE_SPEC.md` for performance optimization goals.
- Read `specs/QUALITY_OBJECTIVE_SPEC.md` for quality optimization goals.

Do not invent metric schemas, log formats, or optimization targets when the reference specs define them. If a spec is still a stub, call that out and proceed with a limited review instead of pretending the standard exists.

Safety and approval rules:
- Stay read-only by default.
- Do not edit a target skill until a human explicitly approves that specific skill.
- Do not run target-skill tests, benchmarks, or scripts until a human explicitly approves execution for that specific skill.
- Keep approvals per skill, not as a single batch.

Review scope for each skill:
- `SKILL.md`
- bundled `scripts/`
- bundled `references/`
- `agents/openai.yaml` when present
- any other bundled files that materially affect quality or performance
- new files that would help instrumentation, benchmarking, or optimization

Per-skill workflow:
1. Inventory the skill contents and identify the callable surfaces, support files, and any existing logs.
2. Compare the skill's current instrumentation against the performance and quality metric specs.
3. Review recent per-skill logs and summarize the strongest quality and performance signals.
4. Compare observed behavior against the performance and quality objective specs.
5. Produce a proposal for that skill only:
   - current gaps
   - suspected root causes
   - concrete file-level changes
   - any new files to add
   - a verification plan that remains blocked on approval
6. Stop and request human approval before making edits.
7. After edit approval, make only the approved changes for that skill.
8. After execution approval, run only the approved verification steps and report outcomes.

Missing-log behavior:
- If a skill lacks usable recent logs, propose both:
  - instrumentation changes needed to emit the required metrics
  - a starter benchmark or eval path that would generate an initial baseline

Output expectations:
- Keep findings and proposals grouped per skill.
- Distinguish clearly between observed facts, inferences from logs, and speculative recommendations.
- Flag when missing specs or missing logs reduce confidence.
- Prefer the smallest high-leverage change set that improves the skill meaningfully.
