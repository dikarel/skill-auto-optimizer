"""
tools.py
Deterministic, sandboxed tool implementations for the eval harness.

Design goals:
  * Real execution: the agent actually calls these tools in a loop, so tool_use and
    doc-grounding are measurable.
  * Deterministic: no real shell, no live web. Backing data is fixed on disk
    (reference docs, a synthetic log dir, a KB corpus) so runs are reproducible and
    cost nothing beyond the model calls themselves.
  * Sandboxed: read_file/read_files cannot escape the fixture's allowed root, and
    create_file can only write inside a per-run output sandbox.

Every executor returns (result_text, doc_ids) where doc_ids are the identifiers
surfaced by the call (basenames of files read, or KB doc ids). The agent loop
accumulates doc_ids so metrics.compute_doc_grounding can score them.
"""
from __future__ import annotations

from pathlib import Path


class ToolError(Exception):
    pass


class ToolContext:
    """Holds the sandbox roots and backing data for one fixture evaluation."""

    def __init__(self, allowed_root: Path, output_sandbox: Path):
        self.allowed_root = allowed_root.resolve()
        self.output_sandbox = output_sandbox.resolve()
        self.output_sandbox.mkdir(parents=True, exist_ok=True)

    # ── path safety ──────────────────────────────────────────────────────────
    def _resolve_readable(self, path: str) -> Path:
        """Resolve a read path, allowing the fixture root or the output sandbox."""
        raw = (self.allowed_root / path) if not Path(path).is_absolute() else Path(path)
        p = raw.resolve()
        for root in (self.allowed_root, self.output_sandbox):
            try:
                p.relative_to(root)
                return p
            except ValueError:
                continue
        raise ToolError(f"path '{path}' is outside the sandbox")

    def _resolve_writable(self, path: str) -> Path:
        name = Path(path).name  # collapse any directory components into the sandbox
        return (self.output_sandbox / name).resolve()


# ── Executors ─────────────────────────────────────────────────────────────────
def _doc_id(p: Path) -> str:
    return p.name


def exec_list_files(ctx: ToolContext, directory: str = ".") -> tuple[str, list[str]]:
    try:
        d = ctx._resolve_readable(directory)
    except ToolError as e:
        return f"ERROR: {e}", []
    if not d.exists() or not d.is_dir():
        return f"ERROR: directory '{directory}' not found", []
    names = sorted(p.name for p in d.iterdir() if p.is_file())
    listing = "\n".join(f"{n} ({(d / n).stat().st_size} bytes)" for n in names)
    return f"Files in {directory}:\n{listing}", []


def exec_read_file(ctx: ToolContext, path: str) -> tuple[str, list[str]]:
    try:
        p = ctx._resolve_readable(path)
    except ToolError as e:
        return f"ERROR: {e}", []
    if not p.exists() or not p.is_file():
        return f"ERROR: file '{path}' not found", []
    text = p.read_text(encoding="utf-8", errors="replace")
    return text, [_doc_id(p)]


def exec_read_files(ctx: ToolContext, paths: list[str]) -> tuple[str, list[str]]:
    chunks, ids = [], []
    for path in paths:
        try:
            p = ctx._resolve_readable(path)
            if not p.exists():
                chunks.append(f"===FILE {path}===\nERROR: not found")
                continue
            chunks.append(f"===FILE {p.name}===\n{p.read_text(encoding='utf-8', errors='replace')}")
            ids.append(_doc_id(p))
        except ToolError as e:
            chunks.append(f"===FILE {path}===\nERROR: {e}")
    return "\n\n".join(chunks), ids


def exec_search_knowledge_base(ctx: ToolContext, query: str) -> tuple[str, list[str]]:
    """Naive term-overlap search over the fixture's kb/ directory."""
    kb = ctx.allowed_root / "kb"
    if not kb.is_dir():
        return "ERROR: no knowledge base available", []
    q = set(query.lower().split())
    scored = []
    for doc in sorted(kb.glob("*.md")):
        text = doc.read_text(encoding="utf-8", errors="replace")
        overlap = len(q & set(text.lower().split()))
        if overlap:
            scored.append((overlap, doc, text))
    scored.sort(key=lambda x: -x[0])
    if not scored:
        return f"No results for '{query}'.", []
    out, ids = [], []
    for _, doc, text in scored[:2]:
        doc_id = doc.stem
        ids.append(doc_id)
        out.append(f"[doc_id: {doc_id}]\n{text.strip()}")
    return "\n\n---\n\n".join(out), ids


def exec_lookup_policy(ctx: ToolContext, topic: str) -> tuple[str, list[str]]:
    kb = ctx.allowed_root / "kb"
    if not kb.is_dir():
        return "ERROR: no policy store available", []
    t = topic.lower()
    for doc in sorted(kb.glob("*.md")):
        if t in doc.stem.lower() or t in doc.read_text(encoding="utf-8", errors="replace").lower():
            return f"[doc_id: {doc.stem}]\n{doc.read_text(encoding='utf-8').strip()}", [doc.stem]
    return f"No policy found for topic '{topic}'.", []


def exec_create_file(ctx: ToolContext, path: str, content: str) -> tuple[str, list[str]]:
    p = ctx._resolve_writable(path)
    p.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} bytes to {p.name}", []


EXECUTORS = {
    "list_files": exec_list_files,
    "read_file": exec_read_file,
    "read_files": exec_read_files,
    "search_knowledge_base": exec_search_knowledge_base,
    "lookup_policy": exec_lookup_policy,
    "create_file": exec_create_file,
}


# ── Anthropic tool schemas ────────────────────────────────────────────────────
_SCHEMAS = {
    "list_files": {
        "name": "list_files",
        "description": "List the files in a directory (relative to the skill's working directory).",
        "input_schema": {
            "type": "object",
            "properties": {"directory": {"type": "string", "description": "Directory to list, e.g. 'references' or 'logs_dir'."}},
            "required": ["directory"],
        },
    },
    "read_file": {
        "name": "read_file",
        "description": "Read the full contents of a single file.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Path to one file."}},
            "required": ["path"],
        },
    },
    "read_files": {
        "name": "read_files",
        "description": "Read multiple files in one call. Returns each file's contents.",
        "input_schema": {
            "type": "object",
            "properties": {"paths": {"type": "array", "items": {"type": "string"}, "description": "List of file paths to read together."}},
            "required": ["paths"],
        },
    },
    "search_knowledge_base": {
        "name": "search_knowledge_base",
        "description": "Search the Acme knowledge base for relevant policy/reference documents.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Search query."}},
            "required": ["query"],
        },
    },
    "lookup_policy": {
        "name": "lookup_policy",
        "description": "Look up a specific policy document by topic (e.g. 'billing', 'subscription').",
        "input_schema": {
            "type": "object",
            "properties": {"topic": {"type": "string", "description": "Policy topic."}},
            "required": ["topic"],
        },
    },
    "create_file": {
        "name": "create_file",
        "description": "Write content to a file at the given path.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Output file path."},
                "content": {"type": "string", "description": "File content to write."},
            },
            "required": ["path", "content"],
        },
    },
}


def schemas_for(tool_names: list[str]) -> list[dict]:
    return [_SCHEMAS[n] for n in tool_names]
