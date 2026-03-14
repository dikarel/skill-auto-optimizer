"""
evaluator.py
Benchmarks a skill (markdown string) against a test conversation.
Measures: input tokens, output tokens, turns, and wall-clock latency.
"""

import time
from dataclasses import dataclass
from typing import Optional

import anthropic

# ── Approximate costs per million tokens (as of early 2026) ──────────────────
_COST_PER_M = {
    "claude-haiku-4-5-20251001": {"input": 0.80,  "output": 4.00},
    "claude-sonnet-4-6":         {"input": 3.00,  "output": 15.00},
    "claude-opus-4-6":           {"input": 15.00, "output": 75.00},
}

def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = _COST_PER_M.get(model, {"input": 3.00, "output": 15.00})
    return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000


@dataclass
class MetricsResult:
    input_tokens: int
    output_tokens: int
    total_tokens: int
    turns: int
    latency_ms: float

    def summary(self) -> str:
        return (
            f"Tokens  : {self.input_tokens} in / {self.output_tokens} out "
            f"/ {self.total_tokens} total\n"
            f"Turns   : {self.turns}\n"
            f"Latency : {self.latency_ms:.1f} ms"
        )


@dataclass
class RoutedResult:
    """Metrics for a routed call: includes routing overhead + actual execution."""
    # Routing phase
    routed_model: str           # model chosen by the router
    routing_tokens: int         # tokens spent on the routing call itself
    routing_latency_ms: float   # time spent routing

    # Execution phase
    exec_result: MetricsResult  # full metrics of the actual skill call

    # Totals
    total_tokens: int           # routing + execution tokens combined
    total_latency_ms: float     # routing + execution latency combined
    estimated_cost_usd: float   # estimated $ cost of execution call

    def summary(self) -> str:
        return (
            f"Routed to : {self.routed_model}\n"
            f"Routing   : {self.routing_tokens} tokens / {self.routing_latency_ms:.1f} ms overhead\n"
            f"Execution : {self.exec_result.summary()}\n"
            f"TOTAL     : {self.total_tokens} tokens / {self.total_latency_ms:.1f} ms\n"
            f"Est. cost : ${self.estimated_cost_usd:.6f}"
        )


class SkillEvaluator:
    """
    Wraps Anthropic API calls and logs core performance metrics.

    Usage (single turn):
        evaluator = SkillEvaluator()
        result = evaluator.run(skill_markdown, user_message="Help me get a refund")

    Usage (multi-turn):
        result = evaluator.run_multiturn(skill_markdown, messages=[
            "I want a refund",
            "My email is user@example.com",
        ])
    """

    DEFAULT_MODEL = "claude-haiku-4-5-20251001"

    def __init__(self, api_key: Optional[str] = None):
        self.client = anthropic.Anthropic(api_key=api_key)

    # ------------------------------------------------------------------
    # Single-turn
    # ------------------------------------------------------------------

    def run(
        self,
        skill_markdown: str,
        user_message: str,
        model: str = DEFAULT_MODEL,
    ) -> MetricsResult:
        """Execute one user message against the skill and return metrics."""
        start = time.perf_counter()

        response = self.client.messages.create(
            model=model,
            max_tokens=1024,
            system=skill_markdown,
            messages=[{"role": "user", "content": user_message}],
        )

        latency_ms = (time.perf_counter() - start) * 1000

        usage = response.usage
        return MetricsResult(
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.input_tokens + usage.output_tokens,
            turns=1,
            latency_ms=latency_ms,
        )

    # ------------------------------------------------------------------
    # Routed single-turn
    # ------------------------------------------------------------------

    def run_routed(
        self,
        skill_markdown: str,
        user_message: str,
        routing_decision: dict,
    ) -> RoutedResult:
        """
        Execute a query on the model recommended by the router.

        `routing_decision` is the dict returned by SkillOptimizer.route_query()
        inside SuggestionReport.routing_decision. It must contain:
          - "model_id": the Anthropic model ID to dispatch to
          - (optional) any other fields for logging

        The routing overhead (tokens + latency from the classification call)
        should be passed in separately via routing_tokens / routing_latency_ms
        if you want accurate totals — use run_routed_with_overhead() for that.
        """
        model_id = routing_decision.get("model_id", self.DEFAULT_MODEL)
        exec_result = self.run(skill_markdown, user_message, model=model_id)
        cost = _estimate_cost(model_id, exec_result.input_tokens, exec_result.output_tokens)

        return RoutedResult(
            routed_model=model_id,
            routing_tokens=routing_decision.get("_routing_tokens", 0),
            routing_latency_ms=routing_decision.get("_routing_latency_ms", 0.0),
            exec_result=exec_result,
            total_tokens=routing_decision.get("_routing_tokens", 0) + exec_result.total_tokens,
            total_latency_ms=routing_decision.get("_routing_latency_ms", 0.0) + exec_result.latency_ms,
            estimated_cost_usd=cost,
        )

    # ------------------------------------------------------------------
    # Multi-turn
    # ------------------------------------------------------------------

    def run_multiturn(
        self,
        skill_markdown: str,
        messages: list[str],
        model: str = DEFAULT_MODEL,
    ) -> MetricsResult:
        """
        Simulate a multi-turn conversation.
        `messages` is a list of user utterances; the agent replies to each.
        Aggregates token usage and latency across all turns.
        """
        history: list[dict] = []
        total_input = 0
        total_output = 0
        total_latency = 0.0

        for user_text in messages:
            history.append({"role": "user", "content": user_text})

            start = time.perf_counter()
            response = self.client.messages.create(
                model=model,
                max_tokens=1024,
                system=skill_markdown,
                messages=history,
            )
            total_latency += (time.perf_counter() - start) * 1000

            total_input += response.usage.input_tokens
            total_output += response.usage.output_tokens

            # Append assistant reply so context grows naturally
            history.append(
                {"role": "assistant", "content": response.content[0].text}
            )

        return MetricsResult(
            input_tokens=total_input,
            output_tokens=total_output,
            total_tokens=total_input + total_output,
            turns=len(messages),
            latency_ms=total_latency,
        )
