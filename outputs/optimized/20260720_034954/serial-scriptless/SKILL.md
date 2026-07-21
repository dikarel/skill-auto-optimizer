---
name: serial-scriptless
description: Summarize the contents of a directory of files.
---

# Directory Summarizer

You summarize every file in a target directory.

## Instructions

1. Call `list_files` on the target directory to get the complete list of filenames. This is your authoritative manifest — every file it returns must be read and accounted for in the summary; do not skip any, and do not summarize files not in the manifest.
2. Read the file contents using the **batch tool** (e.g. `read_files`) in as few calls as possible — pass the full list (or safe-sized chunks if the tool enforces a size limit) instead of issuing one `read_file` call per file. Batching is preferred here because it reduces tool calls without reducing what is actually read; every file's real content is still retrieved and grounded, nothing is skipped or guessed.
3. Verify the batch results against the manifest from step 1: confirm a result was returned for every filename. If any file is missing, errored, or empty, re-read just that file individually with `read_file` — do not re-read files that already succeeded. A second full pass over every file is unnecessary and wasteful.
4. Write the summary strictly from the actual retrieved contents (never inferred from filenames alone). For each file, ground your description in what was read. If a file could not be read after retry, explicitly note it as unavailable rather than guessing its contents.

Output: a short summary of what the directory contains, covering every file in the manifest (either described or flagged as unreadable).

## Instrumentation

Emit these metrics per run, appended as JSON to `logs/<YYYY-MM-DD>.jsonl`:

- `tool_calls` — total number of tool invocations
- `files_read` — count of distinct files successfully read
- `files_total` — count from `list_files` manifest
- `retries` — number of individual re-reads triggered by step 3
- `doc_grounding` — 1.0 if every summarized file traces to actual read content, else 0.0
- `fuzzy_correctness` — heuristic/judge-scored match between summary and file contents
- `latency_ms` and `tokens_used` for the run