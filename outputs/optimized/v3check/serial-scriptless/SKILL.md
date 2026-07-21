---
name: serial-scriptless
description: Summarize the contents of a directory of files.
---

# Directory Summarizer

You summarize every file in a target directory.

## Instructions

1. Call `list_files` on the target directory to get the complete list of filenames. This is mandatory — never guess or assume directory contents.
2. Read the contents of every file **once**, grounding the summary strictly in retrieved content:
   - If a batch tool (e.g. `read_files`) is available, call it **once** with the full list of filenames (or in as few batched calls as the tool's size limits allow). Prefer batching over per-file calls to minimize tool calls and latency.
   - If only a single-file `read_file` tool is available, call it once per file — never skip a file, and never fabricate contents for a file you have not read.
3. Do **not** re-read files after the first pass. A second "verification" pass is unnecessary: it doubles tool calls and latency without improving correctness, since file contents are not expected to change mid-task. If you have reason to believe a file changed (e.g. an explicit tool error or staleness warning), re-read only that specific file, not the whole directory.
4. Every file returned by `list_files` must be accounted for in the summary — do not omit or skip any file, and do not read files outside the target directory.
5. After all files are read, write a summary that:
   - Describes what the directory contains overall (file types, apparent purpose).
   - Briefly characterizes each file's content, grounded only in what was actually read (cite the filename for each claim).
   - Notes any file that could not be read (e.g. empty, binary, permission error) rather than guessing its contents.

Never use shell loops or hand-written scripts to read files — only the provided tools (`list_files`, `read_file`/`read_files`).

## Instrumentation

Emit the following metrics as a JSON line to `logs/<YYYY-MM-DD>.jsonl` after completing the task:

- `tool_calls`: total number of tool invocations
- `files_read`: number of distinct files read
- `files_total`: number of files returned by `list_files`
- `batched_reads_used`: true/false
- `latency_ms`: wall-clock time for the task
- `tokens_used`: total tokens consumed (prompt + completion), if available
- `grounding_ok`: true if every summarized claim traces to a file actually read
- `all_files_covered`: true if `files_read == files_total`