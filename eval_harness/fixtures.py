"""
fixtures.py
Registry of the five evaluation fixtures.

Each entry declares everything the harness needs to score a fixture symmetrically:
  * benchmark_task / expected_answer — the task and its ground truth
  * relevant_doc_ids                 — ground truth for doc_grounding ([] = N/A)
  * requires_tools                   — whether the no-tool hallucination penalty applies
  * tool_names                       — which sandboxed tools are bound for this fixture
  * backing_subdir / corpus_file     — where the fixture's real backing data lives
  * seed_defect                      — the intentional flaw (for the optimizer prompt)

MOCK_SCRIPTS gives a deterministic baseline-vs-optimized behavior used ONLY by
--mock smoke tests. The scripts run through the real tool executors, so grounding
and perf are computed from real backing data even without API calls. They are
illustrative of the expected direction of results; the real (paid) run is what the
paper reports.
"""
from __future__ import annotations

FIXTURES: dict[str, dict] = {
    "chatty-reference-loader": {
        "backing_subdir": "chatty-reference-loader",
        "benchmark_task": "What is the rate limit for the public API endpoint for fetching user data? Use the reference documentation.",
        "expected_answer": (
            "The public API rate limit is 1000 requests per hour per API key. "
            "The burst limit is 100 requests per minute."
        ),
        "relevant_doc_ids": ["ref_api.md"],
        "requires_tools": True,
        "tool_names": ["list_files", "read_file"],
        "seed_defect": (
            "SKILL.md instructs the agent to read all 5 reference files before answering every "
            "question — even simple single-reference questions. The 'always read all references' "
            "instruction is repeated. No performance or quality metrics are emitted."
        ),
    },
    "serial-scriptless": {
        "backing_subdir": "serial-scriptless",
        "benchmark_task": "Summarize the contents of the 'logs_dir' directory. List the files with list_files first.",
        "expected_answer": (
            "The logs_dir directory contains 10 small log files covering authentication (auth.log), "
            "API calls (api.log), billing (billing.log), cache (cache.log), errors (error.log), "
            "workers (worker.log), webhooks (webhook.log), database (db.log), cron (cron.log) and "
            "security (security.log) events. Together they record system operational activity."
        ),
        "relevant_doc_ids": [
            "auth.log", "api.log", "billing.log", "cache.log", "error.log",
            "worker.log", "webhook.log", "db.log", "cron.log", "security.log",
        ],
        "requires_tools": True,
        "tool_names": ["list_files", "read_file", "read_files"],
        "seed_defect": (
            "SKILL.md mandates sequential per-file reads plus a mandatory full second verification "
            "pass, and explicitly bans batching and helper scripts. For 10 files this means ~21 "
            "individual tool calls. No metrics emitted."
        ),
    },
    "missing-metrics": {
        "backing_subdir": "missing-metrics",
        "benchmark_task": (
            "Summarize the following quarterly sales data: Q1: $1.2M, Q2: $1.8M, Q3: $2.1M, "
            "Q4: $2.4M. Total budget was $6.5M."
        ),
        "expected_answer": (
            "Total annual revenue: $7.5M, exceeding the $6.5M budget by $1M (15.4% over). "
            "Q4 was the strongest quarter at $2.4M. Consistent quarter-over-quarter growth "
            "averaging approximately 26%."
        ),
        "relevant_doc_ids": [],           # self-contained; grounding N/A
        "requires_tools": False,
        "tool_names": [],
        "seed_defect": (
            "SKILL.md has reasonable instructions but emits no logs, no performance metrics, and "
            "no quality signals. There is no defined eval or benchmark path."
        ),
    },
    "quality-regression-trap": {
        "backing_subdir": "quality-regression-trap",
        "benchmark_task": (
            "What happens when a user account has zero transactions but still has an active "
            "subscription? What billing actions occur at the next cycle?"
        ),
        "expected_answer": (
            "An account with zero transactions and an active subscription still incurs the full "
            "subscription charge at the next billing cycle. The subscription remains active, the "
            "user retains all subscription benefits, and the billing date is unaffected by the "
            "absence of transactions. The standard payment retry policy applies if the charge fails."
        ),
        "relevant_doc_ids": ["billing_policy", "subscription_lifecycle"],
        "requires_tools": True,
        "tool_names": ["search_knowledge_base", "lookup_policy"],
        "seed_defect": (
            "SKILL.md instructs the agent to 'prefer brief answers and skip edge cases.' The exact "
            "benchmark question (active subscription + zero transactions) is explicitly used as an "
            "example of an edge case to omit. No metrics emitted."
        ),
    },
}


# ── Mock behavior (smoke test only) ───────────────────────────────────────────
_ALL_LOGS = [
    "auth.log", "api.log", "billing.log", "cache.log", "error.log",
    "worker.log", "webhook.log", "db.log", "cron.log", "security.log",
]

MOCK_SCRIPTS: dict[str, dict[str, dict]] = {
    "chatty-reference-loader": {
        # Baseline: reads ALL five references (correct but wasteful).
        "baseline": {
            "tool_calls": [
                {"name": "read_file", "input": {"path": f"references/{f}"}}
                for f in ["ref_database.md", "ref_auth.md", "ref_billing.md", "ref_api.md", "ref_webhooks.md"]
            ],
            "final": "According to ref_api.md the public API rate limit is 1000 requests per hour per API key, and the burst limit is 100 requests per minute.",
        },
        # Optimized: lists, then reads only ref_api.md.
        "optimized": {
            "tool_calls": [
                {"name": "list_files", "input": {"directory": "references"}},
                {"name": "read_file", "input": {"path": "references/ref_api.md"}},
            ],
            "final": "Based on ref_api.md, the public API rate limit is 1000 requests per hour per API key. The burst limit is 100 requests per minute.",
        },
    },
    "serial-scriptless": {
        # Baseline: list + 10 single reads + 10 verification reads = 21 calls.
        "baseline": {
            "tool_calls": (
                [{"name": "list_files", "input": {"directory": "logs_dir"}}]
                + [{"name": "read_file", "input": {"path": f"logs_dir/{f}"}} for f in _ALL_LOGS]
                + [{"name": "read_file", "input": {"path": f"logs_dir/{f}"}} for f in _ALL_LOGS]
            ),
            "final": "The logs_dir directory contains 10 small log files covering authentication (auth.log), API calls (api.log), billing (billing.log), cache (cache.log), errors (error.log), workers (worker.log), webhooks (webhook.log), database (db.log), cron (cron.log) and security (security.log) events. Together they record system operational activity.",
        },
        # Optimized: list + one batched read = 2 calls.
        "optimized": {
            "tool_calls": [
                {"name": "list_files", "input": {"directory": "logs_dir"}},
                {"name": "read_files", "input": {"paths": [f"logs_dir/{f}" for f in _ALL_LOGS]}},
            ],
            "final": "The logs_dir directory contains 10 small log files covering authentication (auth.log), API calls (api.log), billing (billing.log), cache (cache.log), errors (error.log), workers (worker.log), webhooks (webhook.log), database (db.log), cron (cron.log) and security (security.log) events. Together they record system operational activity.",
        },
    },
    "missing-metrics": {
        # No tools either way; answers are similar. Fixture tests instrumentation, not the answer.
        "baseline": {
            "tool_calls": [],
            "final": "Total revenue is $7.5M against a $6.5M budget, so $1M over (about 15.4%). Q4 was strongest at $2.4M, with steady quarter-over-quarter growth of roughly 26% on average.",
        },
        "optimized": {
            "tool_calls": [],
            "final": "Total annual revenue: $7.5M, exceeding the $6.5M budget by $1M (15.4% over). Q4 was the strongest quarter at $2.4M. Consistent quarter-over-quarter growth averaging approximately 26%.",
        },
    },
    "quality-regression-trap": {
        # Baseline: skips the edge case, no tools -> short, ungrounded.
        "baseline": {
            "tool_calls": [],
            "final": "The subscription just renews as normal.",
        },
        # Optimized: retrieves policy, answers the edge case fully.
        "optimized": {
            "tool_calls": [
                {"name": "search_knowledge_base", "input": {"query": "active subscription zero transactions billing cycle charge"}},
                {"name": "lookup_policy", "input": {"topic": "billing"}},
            ],
            "final": "Per the billing policy (§2), an account with zero transactions and an active subscription still incurs the full subscription charge at the next billing cycle. The subscription remains active, all subscription benefits are retained, and the billing date is unaffected by the absence of transactions. The standard payment retry policy applies if the charge fails.",
        },
    },
}
