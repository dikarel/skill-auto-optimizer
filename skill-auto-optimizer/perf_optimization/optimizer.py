"""
optimizer.py
Analyzes a markdown skill file and suggests optimized versions.

Strategies implemented:
  1. compress   — Tool Schema Compression: rewrites verbose prose into a
                  compact, token-efficient format without losing meaning.
  2. cache      — Prompt Caching Preparation: splits the skill into a
                  static block (cacheable) and a dynamic block template,
                  with cache_control breakpoints ready for the Anthropic API.
  3. summarize  — Context Summarization Pipeline: compresses a long
                  conversation history into a minimal summary before passing
                  it to the main model, reducing input tokens per turn.
  4. route      — Hierarchical Routing: classifies an incoming query by
                  complexity and recommends the cheapest model that can
                  handle it (Haiku → Sonnet → Opus).
"""

import time
from dataclasses import dataclass
from typing import Optional

import anthropic


@dataclass
class SuggestionReport:
    strategy: str           # "compress" | "cache" | "summarize" | "route"
    original_tokens: int    # token count of original input to optimizer
    optimized_skill: str    # the rewritten skill text (or summary/routing note)
    explanation: str        # what was changed and why
    cache_template: Optional[dict] = None   # set only for "cache" strategy
    routing_decision: Optional[dict] = None  # set only for "route" strategy


# ── Meta-prompts ──────────────────────────────────────────────────────────────

_COMPRESS_SYSTEM = """\
You are an expert prompt engineer specializing in token efficiency.
Your job: rewrite a verbose agent skill (markdown) into the most compact
version that preserves 100% of the operational information.

Rules:
- Replace long prose instructions with concise bullet points or short sentences.
- Remove redundant phrasing, filler words, and repeated context.
- Use abbreviations where unambiguous (e.g., "30d" for "30 days").
- Preserve all constraints, allowed/disallowed actions, and step sequences.
- Output ONLY two labeled sections:
  ### OPTIMIZED SKILL
  <rewritten markdown>
  ### EXPLANATION
  <bullet list of what was changed and why>
"""

_SUMMARIZE_SYSTEM = """\
You are a context compression engine for AI agents.
Given a conversation history between a user and an agent, produce a minimal
summary that preserves every fact, decision, and open question needed to
continue the conversation correctly — nothing more.

Rules:
- Write in third-person present tense ("User wants...", "Agent confirmed...").
- Use bullet points; one bullet per distinct fact.
- Drop pleasantries, filler, and anything already resolved with no future relevance.
- Never invent facts or infer beyond what is stated.
- Output ONLY two labeled sections:
  ### SUMMARY
  <compressed bullet-point history>
  ### EXPLANATION
  <how many tokens saved and what was safely removed>
"""

_ROUTE_SYSTEM = """\
You are a query complexity classifier for an AI routing layer.
Given an agent skill description and a user query, decide which model tier
should handle the query to minimize cost without sacrificing quality.

Model tiers (cheapest → most capable):
  - haiku   : factual lookups, simple yes/no, form filling, rule-based tasks
  - sonnet  : multi-step reasoning, nuanced judgement, moderate complexity
  - opus    : complex analysis, ambiguous edge cases, high-stakes decisions

Output ONLY two labeled sections:
  ### ROUTING DECISION
  model: <haiku|sonnet|opus>
  confidence: <high|medium|low>
  complexity: <simple|moderate|complex>
  rationale: <one sentence>
  ### EXPLANATION
  <bullet list of signals in the query that drove this decision>
"""

_CACHE_SYSTEM = """\
You are an expert in Anthropic's prompt caching API.
Your job: restructure an agent skill (markdown) to maximize cache hit rate.

Anthropic caches the longest static prefix of a prompt. To benefit:
- Separate content that NEVER changes (policies, tool descriptions, constraints)
  from content that changes per request (user context, session data, task input).
- The static block should come first and be as large as possible.
- The dynamic block should be a minimal template with clear {{PLACEHOLDERS}}.

Output ONLY three labeled sections:
  ### STATIC BLOCK
  <the cacheable, never-changing part of the skill>
  ### DYNAMIC TEMPLATE
  <the per-request template with {{PLACEHOLDERS}} for variable data>
  ### EXPLANATION
  <bullet list of decisions made and expected cache savings>
"""


class SkillOptimizer:
    """
    Suggests optimized rewrites of a markdown skill file.

    Usage:
        optimizer = SkillOptimizer()
        reports = optimizer.optimize(skill_markdown)
        for r in reports:
            print(r.strategy, r.explanation)
            print(r.optimized_skill)
    """

    OPTIMIZER_MODEL = "claude-sonnet-4-6"  # stronger model for meta-reasoning

    def __init__(self, api_key: Optional[str] = None):
        self.client = anthropic.Anthropic(api_key=api_key)

    # ------------------------------------------------------------------
    # Strategy 1: Tool Schema Compression
    # ------------------------------------------------------------------

    def compress(self, skill_markdown: str) -> SuggestionReport:
        """Rewrite the skill in a compact, token-efficient format."""
        response = self.client.messages.create(
            model=self.OPTIMIZER_MODEL,
            max_tokens=2048,
            system=_COMPRESS_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": f"Optimize this skill:\n\n{skill_markdown}",
                }
            ],
        )

        raw = response.content[0].text
        optimized, explanation = _parse_two_sections(
            raw, "OPTIMIZED SKILL", "EXPLANATION"
        )

        return SuggestionReport(
            strategy="compress",
            original_tokens=response.usage.input_tokens,
            optimized_skill=optimized,
            explanation=explanation,
        )

    # ------------------------------------------------------------------
    # Strategy 2: Prompt Caching Preparation
    # ------------------------------------------------------------------

    def prepare_for_caching(self, skill_markdown: str) -> SuggestionReport:
        """
        Split the skill into a static (cacheable) block and a dynamic
        template, and return a ready-to-use cache_control message structure.
        """
        response = self.client.messages.create(
            model=self.OPTIMIZER_MODEL,
            max_tokens=2048,
            system=_CACHE_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": f"Restructure this skill for prompt caching:\n\n{skill_markdown}",
                }
            ],
        )

        raw = response.content[0].text
        static_block, rest = _parse_two_sections(raw, "STATIC BLOCK", "DYNAMIC TEMPLATE")
        dynamic_template, explanation = _parse_two_sections(
            rest + "\n### EXPLANATION" + raw.split("### EXPLANATION", 1)[-1],
            "DYNAMIC TEMPLATE",
            "EXPLANATION",
        )

        # Build the Anthropic API message structure with cache_control
        cache_template = {
            "description": (
                "Pass `system` as a list of content blocks. "
                "The static block will be cached after the first call."
            ),
            "system": [
                {
                    "type": "text",
                    "text": static_block,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": dynamic_template,
                        }
                    ],
                }
            ],
            "note": (
                "Replace {{PLACEHOLDERS}} in the dynamic template with "
                "actual runtime values before each API call."
            ),
        }

        return SuggestionReport(
            strategy="cache",
            original_tokens=response.usage.input_tokens,
            optimized_skill=static_block,
            explanation=explanation,
            cache_template=cache_template,
        )

    # ------------------------------------------------------------------
    # Strategy 3: Context Summarization Pipeline
    # ------------------------------------------------------------------

    def summarize_context(
        self,
        history: list[dict],
        skill_markdown: str = "",
    ) -> SuggestionReport:
        """
        Compress a conversation history into a minimal summary.

        `history` is a list of {"role": "user"|"assistant", "content": "..."}
        dicts — the same format used in Anthropic API calls.

        Returns a SuggestionReport where `optimized_skill` is the compressed
        summary text, ready to be injected as a single "assistant" context
        block at the start of the next API call.
        """
        # Format history for the meta-prompt
        formatted = "\n".join(
            f"[{msg['role'].upper()}]: {msg['content']}"
            for msg in history
        )

        response = self.client.messages.create(
            model=self.OPTIMIZER_MODEL,
            max_tokens=1024,
            system=_SUMMARIZE_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": f"Compress this conversation history:\n\n{formatted}",
                }
            ],
        )

        raw = response.content[0].text
        summary, explanation = _parse_two_sections(raw, "SUMMARY", "EXPLANATION")

        # Approximate original token cost: ~1 token per 4 chars
        original_char_count = sum(len(m["content"]) for m in history)
        original_approx_tokens = original_char_count // 4

        return SuggestionReport(
            strategy="summarize",
            original_tokens=original_approx_tokens,
            optimized_skill=summary,
            explanation=explanation,
        )

    # ------------------------------------------------------------------
    # Strategy 4: Hierarchical Routing
    # ------------------------------------------------------------------

    def route_query(
        self,
        query: str,
        skill_markdown: str,
    ) -> SuggestionReport:
        """
        Classify query complexity and recommend the cheapest model tier
        (haiku / sonnet / opus) that can handle it correctly.

        Returns a SuggestionReport where `routing_decision` contains:
          - recommended_model: str
          - confidence: str
          - complexity: str
          - rationale: str
        """
        _route_start = time.perf_counter()
        response = self.client.messages.create(
            model="claude-haiku-4-5-20251001",  # intentionally cheap: routing is simple
            max_tokens=512,
            system=_ROUTE_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Skill description:\n{skill_markdown}\n\n"
                        f"Incoming query:\n{query}"
                    ),
                }
            ],
        )

        raw = response.content[0].text
        decision_block, explanation = _parse_two_sections(
            raw, "ROUTING DECISION", "EXPLANATION"
        )

        routing_decision = _parse_routing_block(decision_block)

        # Map recommended model name → actual Anthropic model ID
        model_map = {
            "haiku": "claude-haiku-4-5-20251001",
            "sonnet": "claude-sonnet-4-6",
            "opus": "claude-opus-4-6",
        }
        recommended = routing_decision.get("model", "sonnet").lower()
        routing_decision["model_id"] = model_map.get(recommended, "claude-sonnet-4-6")

        # Stamp routing overhead so SkillEvaluator.run_routed() can include it in totals
        routing_decision["_routing_tokens"] = response.usage.input_tokens + response.usage.output_tokens
        routing_decision["_routing_latency_ms"] = (time.perf_counter() - _route_start) * 1000

        return SuggestionReport(
            strategy="route",
            original_tokens=response.usage.input_tokens,
            optimized_skill=f"Route to: {recommended}",
            explanation=explanation,
            routing_decision=routing_decision,
        )

    # ------------------------------------------------------------------
    # Run all strategies
    # ------------------------------------------------------------------

    def optimize(
        self,
        skill_markdown: str,
        strategies: list[str] = ("compress", "cache"),
        # For summarize: pass history=[...]
        history: Optional[list[dict]] = None,
        # For route: pass query="..."
        query: Optional[str] = None,
    ) -> list[SuggestionReport]:
        """Run selected strategies and return a report for each."""
        results = []
        for strategy in strategies:
            if strategy == "compress":
                results.append(self.compress(skill_markdown))
            elif strategy == "cache":
                results.append(self.prepare_for_caching(skill_markdown))
            elif strategy == "summarize":
                if not history:
                    raise ValueError("summarize strategy requires history=[...]")
                results.append(self.summarize_context(history, skill_markdown))
            elif strategy == "route":
                if not query:
                    raise ValueError("route strategy requires query='...'")
                results.append(self.route_query(query, skill_markdown))
            else:
                raise ValueError(f"Unknown strategy: {strategy!r}")
        return results


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_routing_block(block: str) -> dict:
    """Parse 'key: value' lines from the ROUTING DECISION block into a dict."""
    result = {}
    for line in block.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip().lower().replace(" ", "_")] = value.strip()
    return result


def _parse_two_sections(text: str, first: str, second: str) -> tuple[str, str]:
    """
    Extract content between ### FIRST and ### SECOND headers.
    Returns (first_content, second_content). Strips surrounding whitespace.
    """
    tag1 = f"### {first}"
    tag2 = f"### {second}"

    if tag1 not in text or tag2 not in text:
        # Graceful fallback: return full text as first section
        return text.strip(), "(could not parse explanation)"

    after_first = text.split(tag1, 1)[1]
    first_content = after_first.split(tag2, 1)[0].strip()
    second_content = after_first.split(tag2, 1)[1].strip()
    return first_content, second_content
