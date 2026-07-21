"""
agent_loop.py
A real tool-use loop over the Anthropic Messages API, plus a deterministic mock
path used for no-cost smoke testing.

The loop binds the fixture's tools, lets the model call them, executes each call
locally against the sandboxed backing data (tools.py), feeds the results back, and
repeats until the model stops or max_iters is hit. It records everything needed to
score tool use and grounding: the sequence of tool calls and the doc_ids each call
surfaced.

Mock mode runs a scripted sequence of tool calls (defined per fixture/variant in
fixtures.py) through the SAME real executors, so the smoke test exercises the tool
sandbox and the full metric/aggregation pipeline without any API spend.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from tools import EXECUTORS, ToolContext, schemas_for


@dataclass
class AgentRun:
    final_text: str
    tool_calls: list[dict] = field(default_factory=list)   # [{"name","input"}]
    retrieved_doc_ids: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    files_read: int = 0        # distinct doc_ids surfaced by file-read tools
    bytes_read: int = 0        # total bytes returned by file-read tools
    turns: int = 0             # number of model calls
    wall_clock_s: float = 0.0
    error: str | None = None

    @property
    def tool_called(self) -> bool:
        return len(self.tool_calls) > 0

    @property
    def num_tool_calls(self) -> int:
        return len(self.tool_calls)


_FILE_READ_TOOLS = {"read_file", "read_files"}


def _account_reads(run: AgentRun, tool_name: str, result_text: str, doc_ids: list[str]) -> None:
    """Track files_read / bytes_read for the perf score from real reads."""
    if tool_name in _FILE_READ_TOOLS:
        run.files_read += len(doc_ids)
        run.bytes_read += len(result_text.encode("utf-8"))


def run_agent_real(
    client,
    model: str,
    system: str,
    user_message: str,
    tool_names: list[str],
    ctx: ToolContext,
    max_iters: int = 30,
    max_tokens: int = 3000,
) -> AgentRun:
    run = AgentRun(final_text="")
    tools = schemas_for(tool_names)
    messages: list[dict] = [{"role": "user", "content": user_message}]
    last_assistant_text = ""
    hit_cap = True
    t0 = time.perf_counter()
    try:
        for _ in range(max_iters):
            kwargs = dict(model=model, max_tokens=max_tokens, system=system, messages=messages)
            if tools:
                kwargs["tools"] = tools
            resp = client.messages.create(**kwargs)
            run.turns += 1
            run.input_tokens += resp.usage.input_tokens
            run.output_tokens += resp.usage.output_tokens
            messages.append({"role": "assistant", "content": resp.content})
            turn_text = "".join(
                getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text"
            ).strip()
            if turn_text:
                last_assistant_text = turn_text

            if resp.stop_reason == "tool_use":
                results = []
                for block in resp.content:
                    if getattr(block, "type", None) == "tool_use":
                        run.tool_calls.append({"name": block.name, "input": block.input})
                        executor = EXECUTORS.get(block.name)
                        if executor is None:
                            text, ids = f"ERROR: unknown tool {block.name}", []
                        else:
                            text, ids = executor(ctx, **block.input)
                        run.retrieved_doc_ids += ids
                        _account_reads(run, block.name, text, ids)
                        results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": text[:8000],
                        })
                messages.append({"role": "user", "content": results})
            else:
                # Final answer: concatenate text blocks
                run.final_text = turn_text
                hit_cap = False
                break
        if hit_cap:
            # Ran out of tool-call turns. Fall back to the last text the model
            # produced (may be a partial answer) and flag the truncation so it can
            # be filtered/reported rather than silently scored as an empty failure.
            run.final_text = last_assistant_text
            run.error = f"hit_max_iters({max_iters})"
    except Exception as e:  # noqa: BLE001 — surface any API/tool error into the record
        run.error = str(e)
    run.wall_clock_s = time.perf_counter() - t0
    return run


def run_agent_mock(script: dict, ctx: ToolContext) -> AgentRun:
    """Execute a scripted run (from fixtures.MOCK_SCRIPTS) through the real
    executors. `script` = {"tool_calls": [{"name","input"}...], "final": str}."""
    run = AgentRun(final_text=script.get("final", ""))
    for call in script.get("tool_calls", []):
        name, inp = call["name"], call.get("input", {})
        run.tool_calls.append({"name": name, "input": inp})
        executor = EXECUTORS.get(name)
        if executor is None:
            text, ids = f"ERROR: unknown tool {name}", []
        else:
            text, ids = executor(ctx, **inp)
        run.retrieved_doc_ids += ids
        _account_reads(run, name, text, ids)
    # Deterministic, non-zero synthetic perf numbers (no wall-clock randomness).
    run.turns = len(run.tool_calls) + 1
    run.input_tokens = 400 + 60 * len(run.tool_calls)
    run.output_tokens = max(20, len(run.final_text) // 4)
    run.wall_clock_s = round(0.4 + 0.15 * len(run.tool_calls), 3)
    return run
