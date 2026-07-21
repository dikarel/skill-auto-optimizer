---
name: serial-scriptless
description: Summarize the contents of a directory of files.
---

# Directory Summarizer

You summarize every file in a target directory, grounding every claim in
actual file contents retrieved via tool calls.

## Instructions

1. Call `list_files` on the target directory to get the full list of filenames.
2. Read every file's contents using tools before writing anything. Prefer a
   single batched call (e.g. `read_files` with the full filename list) over
   serial `read_file` calls — batching is required when available, since it
   cuts tool calls/latency without losing information. If only a
   single-file `read_file` tool exists, call it once per file (no repeats).
3. Do **not** re-read any file a second time "to verify" — each file must be
   read exactly once. Do not skip any file returned by `list_files`.
4. Do not use shell loops or helper scripts to read files; use the provided
   tools directly (batched call or one call per file).
5. After all files are read, write the summary. For each file, include:
   - the filename (as a citation/reference),
   - a one- to two-sentence description of its actual content, grounded in
     what was read (no speculation about unread content).
6. Close with a short overall summary of what the directory contains as a
   whole.

If `list_files` returns zero files, state that the directory is empty and
skip the read step entirely (do not call read tools with no files).

## Instrumentation

Emit the following metrics per run to `logs/<YYYY-MM-DD>.jsonl`:

- perf: `tool_calls`, `files_read`, `tokens_used`, `latency_ms`
- quality: `tool_use_rate`, `doc_grounding`, `fuzzy_correctness`,
  `citation_count` (one per summarized file), `judge_overall`