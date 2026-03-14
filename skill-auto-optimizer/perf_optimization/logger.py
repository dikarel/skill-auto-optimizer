"""
logger.py
Writes structured JSONL logs to logs/<YYYY-MM-DD>.jsonl.
All public functions accept the dataclasses from evaluator.py and optimizer.py.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from evaluator import MetricsResult, RoutedResult, _estimate_cost
from optimizer import SuggestionReport

LOGS_DIR = Path("logs")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _log_path() -> Path:
    LOGS_DIR.mkdir(exist_ok=True)
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return LOGS_DIR / f"{date}.jsonl"


def _write(record: dict) -> None:
    with _log_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def new_session() -> str:
    """Generate and return a fresh session UUID."""
    return str(uuid.uuid4())


# ── Event writers ─────────────────────────────────────────────────────────────

def log_eval(
    session_id: str,
    skill_name: str,
    skill_path: str,
    query: str,
    model: str,
    result: MetricsResult,
) -> None:
    cost = _estimate_cost(model, result.input_tokens, result.output_tokens)
    _write({
        "ts": _now(),
        "session_id": session_id,
        "event": "eval",
        "skill_name": skill_name,
        "skill_path": skill_path,
        "query": query,
        "model": model,
        "metrics": {
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "total_tokens": result.total_tokens,
            "turns": result.turns,
            "latency_ms": round(result.latency_ms, 2),
            "estimated_cost_usd": round(cost, 8),
        },
    })


def log_eval_multiturn(
    session_id: str,
    skill_name: str,
    skill_path: str,
    queries: list[str],
    model: str,
    result: MetricsResult,
) -> None:
    cost = _estimate_cost(model, result.input_tokens, result.output_tokens)
    _write({
        "ts": _now(),
        "session_id": session_id,
        "event": "eval_multiturn",
        "skill_name": skill_name,
        "skill_path": skill_path,
        "query": queries,
        "model": model,
        "metrics": {
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "total_tokens": result.total_tokens,
            "turns": result.turns,
            "latency_ms": round(result.latency_ms, 2),
            "estimated_cost_usd": round(cost, 8),
        },
    })


def log_optimize(
    session_id: str,
    skill_name: str,
    skill_path: str,
    original_text: str,
    report: SuggestionReport,
    optimizer_input_tokens: int,
    optimizer_output_tokens: int,
    optimizer_model: str,
) -> None:
    before_chars = len(original_text)
    before_approx = before_chars // 4
    after_text = report.optimized_skill
    after_chars = len(after_text)
    after_approx = after_chars // 4
    token_reduction = before_approx - after_approx
    token_reduction_pct = round(token_reduction / before_approx * 100, 1) if before_approx else 0.0
    optimizer_cost = _estimate_cost(optimizer_model, optimizer_input_tokens, optimizer_output_tokens)

    record: dict = {
        "ts": _now(),
        "session_id": session_id,
        "event": "optimize",
        "skill_name": skill_name,
        "skill_path": skill_path,
        "strategy": report.strategy,
        "optimizer_model": optimizer_model,
        "before": {
            "char_count": before_chars,
            "approx_tokens": before_approx,
        },
        "optimizer_cost": {
            "input_tokens": optimizer_input_tokens,
            "output_tokens": optimizer_output_tokens,
            "estimated_cost_usd": round(optimizer_cost, 8),
        },
        "explanation_snippet": report.explanation[:200].replace("\n", " "),
    }

    if report.strategy == "compress":
        record["after"] = {
            "char_count": after_chars,
            "approx_tokens": after_approx,
        }
        record["efficiency"] = {
            "token_reduction": token_reduction,
            "token_reduction_pct": token_reduction_pct,
            "char_reduction_pct": round((before_chars - after_chars) / before_chars * 100, 1),
        }

    elif report.strategy == "cache" and report.cache_template:
        static_text = report.cache_template.get("system", [{}])[0].get("text", "")
        dynamic_text = ""
        msgs = report.cache_template.get("messages", [])
        if msgs:
            content = msgs[0].get("content", [])
            if content:
                dynamic_text = content[0].get("text", "")
        static_chars = len(static_text)
        dynamic_chars = len(dynamic_text)
        cacheable_pct = round(static_chars / (static_chars + dynamic_chars) * 100, 1) if (static_chars + dynamic_chars) else 0
        record["after"] = {
            "static_char_count": static_chars,
            "dynamic_char_count": dynamic_chars,
            "cacheable_token_pct": cacheable_pct,
        }
        record["efficiency"] = {
            "cache_hit_savings_pct": 90.0,
            "note": "Savings apply from 2nd call onward at ~10% cost on static block",
        }

    elif report.strategy == "summarize":
        record["after"] = {
            "char_count": after_chars,
            "approx_tokens": after_approx,
        }
        record["efficiency"] = {
            "token_reduction": token_reduction,
            "token_reduction_pct": token_reduction_pct,
            "char_reduction_pct": round((before_chars - after_chars) / before_chars * 100, 1),
        }

    _write(record)


def log_routed(
    session_id: str,
    skill_name: str,
    skill_path: str,
    query: str,
    result: RoutedResult,
    sonnet_baseline: Optional[MetricsResult] = None,
) -> None:
    rd = result.exec_result
    routing_decision = {
        "classifier_model": "claude-haiku-4-5-20251001",
        "routed_model": result.routed_model,
        "complexity": "unknown",
        "confidence": "unknown",
        "rationale": "",
        "routing_tokens": result.routing_tokens,
        "routing_latency_ms": round(result.routing_latency_ms, 2),
    }

    record: dict = {
        "ts": _now(),
        "session_id": session_id,
        "event": "routed",
        "skill_name": skill_name,
        "skill_path": skill_path,
        "query": query,
        "routing": routing_decision,
        "execution": {
            "model": result.routed_model,
            "input_tokens": rd.input_tokens,
            "output_tokens": rd.output_tokens,
            "total_tokens": rd.total_tokens,
            "latency_ms": round(rd.latency_ms, 2),
            "estimated_cost_usd": round(result.estimated_cost_usd, 8),
        },
        "totals": {
            "tokens": result.total_tokens,
            "latency_ms": round(result.total_latency_ms, 2),
            "estimated_cost_usd": round(result.estimated_cost_usd, 8),
        },
    }

    if sonnet_baseline is not None:
        sonnet_cost = _estimate_cost(
            "claude-sonnet-4-6",
            sonnet_baseline.input_tokens,
            sonnet_baseline.output_tokens,
        )
        cost_delta = result.estimated_cost_usd - sonnet_cost
        savings_pct = round(-cost_delta / sonnet_cost * 100, 1) if sonnet_cost else 0
        record["vs_always_sonnet"] = {
            "token_delta": result.total_tokens - sonnet_baseline.total_tokens,
            "cost_delta_usd": round(cost_delta, 8),
            "cost_savings_pct": savings_pct,
        }

    _write(record)


def log_session_summary(
    session_id: str,
    skill_name: str,
    baseline: MetricsResult,
    baseline_model: str,
    best_strategy: str,
    best_result: MetricsResult,
    best_model: str,
) -> None:
    baseline_cost = _estimate_cost(baseline_model, baseline.input_tokens, baseline.output_tokens)
    best_cost = _estimate_cost(best_model, best_result.input_tokens, best_result.output_tokens)
    _write({
        "ts": _now(),
        "session_id": session_id,
        "event": "session_summary",
        "skill_name": skill_name,
        "baseline": {
            "total_tokens": baseline.total_tokens,
            "latency_ms": round(baseline.latency_ms, 2),
            "cost_usd": round(baseline_cost, 8),
        },
        "best_result": {
            "strategy": best_strategy,
            "total_tokens": best_result.total_tokens,
            "latency_ms": round(best_result.latency_ms, 2),
            "cost_usd": round(best_cost, 8),
            "token_savings_pct": round(
                (baseline.total_tokens - best_result.total_tokens) / baseline.total_tokens * 100, 1
            ) if baseline.total_tokens else 0,
            "latency_savings_pct": round(
                (baseline.latency_ms - best_result.latency_ms) / baseline.latency_ms * 100, 1
            ) if baseline.latency_ms else 0,
        },
    })
