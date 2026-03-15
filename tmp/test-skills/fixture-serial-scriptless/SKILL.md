```
---
name: batch-file-summarizer
description: Summarize all files in a directory using minimal tool calls.
---

# Directory File Summarizer

Summarize all files in a directory in ≤2 tool calls.

<!-- cache_control: ephemeral -->

## Critical Rules

- **Never fabricate data.** If a command fails, report error — do NOT invent content.
- **Never skip a file** (including empty/binary).
- **One batch read only** — never re-read files individually.
- If output may truncate, shorten per-file summaries to ensure ALL files appear.
- **If the target directory doesn't exist at the given path:** try common alternatives (`/tmp/`, `./`, `~/`) and `find / -type d -name "<dirname>" 2>/dev/null` before giving up. Only stop after exhausting recovery attempts.

## Process

### Tool Call 1: Locate & list files

```bash
DIR="<directory>"; if [ ! -d "$DIR" ]; then FOUND=$(find / -maxdepth 4 -type d -name "$(basename "$DIR")" 2>/dev/null | head -1); [ -n "$FOUND" ] && DIR="$FOUND"; fi; echo "RESOLVED_DIR=$DIR"; ls -la "$DIR"
```

Extract: resolved path, filenames, sizes, count. If still not found after search, report error and stop.

### Tool Call 2: Batch-read all files

```bash
for f in <resolved_dir>/*; do echo "===FILE: $f==="; cat "$f" 2>/dev/null || echo "[binary/unreadable]"; echo "===END==="; done
```

- Binary → "Binary file."
- Empty (0 bytes) → "Empty file."

### Step 3: Compile report (no tool call)

Synthesize from captured output only.

## Output Format

```
Directory: <resolved path>
Total files: <count>
Total size: <sum in KB>

File-by-file summaries:
1. <filename> (<size>): <one-sentence summary grounded in file content>
2. ...

Overall summary:
<2–3 sentences on directory purpose and content themes>
```

## Quality Guardrails

- Every file from `ls` **must** appear in summaries — completeness mandatory.
- Each summary must reference **specific content** from the file (grounding).
- Cite filenames **exactly** as returned by `ls`.
- If uncertain, state uncertainty — never fabricate.
- Incomplete response = failure; always finish the overall summary.
- Tool calls target: ≤ 2. File read ops target: ≤ 2 (one ls + one batch cat).

## Instrumentation

Emit per run:
- `input_tokens`, `output_tokens`, `total_tokens`
- `turns` (tool calls; target ≤ 2)
- `latency_ms`, `estimated_cost_usd`
- `files_read` (target ≤ 2)
- Quality: filename citations, grounding refs, tool call count

Log to `logs/<YYYY-MM-DD>.jsonl`, one JSON record per event.
```