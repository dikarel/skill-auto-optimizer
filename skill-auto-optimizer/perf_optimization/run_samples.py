"""
run_samples.py
Runs the evaluator and optimizer against all skills in skills/,
logging every result to logs/<date>.jsonl per the logs_spec.md format.

Usage:
    python run_samples.py                  # all skills, all strategies
    python run_samples.py --skill example_skill
    python run_samples.py --strategy compress
    python run_samples.py --no-optimize    # eval only, skip optimizer calls
"""

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

import logger
from evaluator import SkillEvaluator, _estimate_cost
from optimizer import SkillOptimizer

load_dotenv()

# ── Sample queries per skill ──────────────────────────────────────────────────

QUERIES: dict[str, dict] = {
    "example_skill": {
        "single": "I bought the Pro plan two weeks ago and I want a refund.",
        "multiturn": [
            "I want to cancel my subscription.",
            "The reason is the reporting feature keeps crashing.",
            "My email is jane@example.com, account ID 98231.",
        ],
        "routing_samples": [
            "What are your pricing plans?",
            "I want a refund for a purchase I made 20 days ago.",
            "We are an enterprise customer. Our security team flagged a potential "
            "data leak via your API. I need full audit logs and details on your "
            "data retention and breach notification policy immediately.",
        ],
    },
    "code_review_skill": {
        "single": "Please review this Python function:\n\ndef get_user(id):\n    query = f\"SELECT * FROM users WHERE id = {id}\"\n    return db.execute(query)",
        "multiturn": [
            "Here is a PR with 3 files changed. First file: auth.py adds JWT validation.",
            "Second file: api.py adds a new /users endpoint with no rate limiting.",
            "Third file: tests/test_auth.py adds 2 unit tests. Is the coverage sufficient?",
        ],
        "routing_samples": [
            "Is using f-strings in SQL queries a security issue?",
            "Review this 50-line Python module for correctness and style.",
            "This PR refactors our entire authentication system from sessions to JWT. "
            "Review for security vulnerabilities, breaking changes, and migration risks.",
        ],
    },
    "data_analyst_skill": {
        "single": "Write a SQL query to find the top 5 customers by total revenue in the last 30 days.",
        "multiturn": [
            "I have a table: orders(id, customer_id, amount, created_at). How do I get monthly revenue?",
            "The query is slow. It takes 10 seconds on 2M rows. How do I optimize it?",
            "Now I also want to include only orders where status = 'completed'.",
        ],
        "routing_samples": [
            "What does GROUP BY do in SQL?",
            "Write a query to calculate 7-day rolling average revenue by customer segment.",
            "Our p-value is 0.03 but our sample sizes are very unequal (n=50 vs n=4000). "
            "Is our A/B test result statistically valid? Walk me through all the assumptions "
            "we need to check and whether we need a different test.",
        ],
    },
}

SKILLS_DIR = Path("skills")
EVAL_MODEL = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-6"


def run_skill(
    skill_name: str,
    skill_markdown: str,
    skill_path: str,
    session_id: str,
    evaluator: SkillEvaluator,
    optimizer: SkillOptimizer,
    strategies: list[str],
    run_optimize: bool,
) -> None:
    queries = QUERIES.get(skill_name, {})
    if not queries:
        print(f"  [skip] no sample queries defined for {skill_name!r}")
        return

    print(f"\n{'─'*60}\nSkill: {skill_name}\n{'─'*60}")

    # ── Baseline single-turn ─────────────────────────────────────
    single_q = queries.get("single", "Hello, what can you help me with?")
    print(f"  eval (single): {single_q[:60]}...")
    baseline = evaluator.run(skill_markdown, single_q, model=EVAL_MODEL)
    logger.log_eval(session_id, skill_name, skill_path, single_q, EVAL_MODEL, baseline)
    print(f"    → {baseline.total_tokens} tokens / {baseline.latency_ms:.0f} ms")

    # ── Baseline multi-turn ──────────────────────────────────────
    mt_queries = queries.get("multiturn", [])
    if mt_queries:
        print(f"  eval (multi-turn, {len(mt_queries)} turns)...")
        baseline_mt = evaluator.run_multiturn(skill_markdown, mt_queries, model=EVAL_MODEL)
        logger.log_eval_multiturn(
            session_id, skill_name, skill_path, mt_queries, EVAL_MODEL, baseline_mt
        )
        print(f"    → {baseline_mt.total_tokens} tokens / {baseline_mt.latency_ms:.0f} ms")

    # ── Optimizer strategies ─────────────────────────────────────
    if run_optimize:
        for strategy in strategies:
            if strategy in ("compress", "cache"):
                print(f"  optimize ({strategy})...")
                report = (
                    optimizer.compress(skill_markdown)
                    if strategy == "compress"
                    else optimizer.prepare_for_caching(skill_markdown)
                )
                # We need raw token counts from the optimizer call — approximate via
                # report.original_tokens (which is the optimizer's input token count)
                logger.log_optimize(
                    session_id, skill_name, skill_path,
                    original_text=skill_markdown,
                    report=report,
                    optimizer_input_tokens=report.original_tokens,
                    optimizer_output_tokens=len(report.optimized_skill) // 4,
                    optimizer_model=optimizer.OPTIMIZER_MODEL,
                )
                before_approx = len(skill_markdown) // 4
                after_approx = len(report.optimized_skill) // 4
                reduction = round((before_approx - after_approx) / before_approx * 100, 1)
                print(f"    → ~{reduction}% token reduction")

                # Re-evaluate compressed skill
                if strategy == "compress":
                    print(f"    re-eval compressed skill...")
                    compressed_result = evaluator.run(
                        report.optimized_skill, single_q, model=EVAL_MODEL
                    )
                    logger.log_eval(
                        session_id, skill_name + "_compressed", skill_path,
                        single_q, EVAL_MODEL, compressed_result,
                    )
                    delta = compressed_result.total_tokens - baseline.total_tokens
                    print(f"    → {compressed_result.total_tokens} tokens ({delta:+d} vs baseline)")

    # ── Routed dispatch ──────────────────────────────────────────
    routing_samples = queries.get("routing_samples", [])
    if routing_samples:
        print(f"  routing ({len(routing_samples)} queries)...")
        # Sonnet baseline for cost comparison
        sonnet_baselines = {
            q: evaluator.run(skill_markdown, q, model=SONNET_MODEL)
            for q in routing_samples
        }
        for query in routing_samples:
            route_report = optimizer.route_query(query, skill_markdown)
            rd = route_report.routing_decision
            routed = evaluator.run_routed(skill_markdown, query, rd)
            logger.log_routed(
                session_id, skill_name, skill_path, query,
                routed, sonnet_baseline=sonnet_baselines[query],
            )
            model_short = rd.get("model", "?")
            complexity = rd.get("complexity", "?")
            print(f"    [{complexity}] → {model_short} / "
                  f"{routed.total_tokens} tokens / ${routed.estimated_cost_usd:.6f}")

    # ── Session summary ──────────────────────────────────────────
    logger.log_session_summary(
        session_id=session_id,
        skill_name=skill_name,
        baseline=baseline,
        baseline_model=EVAL_MODEL,
        best_strategy="routed" if routing_samples else "baseline",
        best_result=baseline,   # placeholder — real best selected below
        best_model=EVAL_MODEL,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill", help="Run only this skill (stem name, no .md)")
    parser.add_argument("--strategy", help="Only run this optimizer strategy")
    parser.add_argument("--no-optimize", action="store_true", help="Skip optimizer calls")
    args = parser.parse_args()

    api_key = os.getenv("ANTHROPIC_API_KEY")
    evaluator = SkillEvaluator(api_key=api_key)
    optimizer = SkillOptimizer(api_key=api_key)
    session_id = logger.new_session()

    strategies = [args.strategy] if args.strategy else ["compress", "cache"]
    run_optimize = not args.no_optimize

    skill_files = sorted(SKILLS_DIR.glob("*.md"))
    if args.skill:
        skill_files = [f for f in skill_files if f.stem == args.skill]
        if not skill_files:
            print(f"No skill file found for {args.skill!r}")
            return

    print(f"Session: {session_id}")
    print(f"Skills : {[f.stem for f in skill_files]}")
    print(f"Logging to: {logger._log_path()}")

    for skill_file in skill_files:
        skill_markdown = skill_file.read_text(encoding="utf-8")
        run_skill(
            skill_name=skill_file.stem,
            skill_markdown=skill_markdown,
            skill_path=str(skill_file),
            session_id=session_id,
            evaluator=evaluator,
            optimizer=optimizer,
            strategies=strategies,
            run_optimize=run_optimize,
        )

    print(f"\nDone. Logs written to {logger._log_path()}")


if __name__ == "__main__":
    main()
