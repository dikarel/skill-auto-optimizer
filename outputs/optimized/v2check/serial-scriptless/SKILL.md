---
name: serial-scriptless
description: Summarize the contents of a directory of files.
---

# Directory Summarizer

You summarize every file in a target directory.

## Instructions

All contents must be grounded in actual tool output — never guess or hallucinate file names or contents. Always read every file's real content before writing the summary.

Procedure:

1. Call `list_files` on the target directory to get the full list of filenames.
2. Read the files using the batch tool: call `read_files` **once** with the entire list of filenames from step 1 (or the minimum number of batched calls if the tool has a size limit). Do not issue separate `read_file` calls per file, and do not use shell loops — batching is required here for efficiency, but every file must still actually be read (no skipping, no sampling, no summarizing based on filename alone).
3. Do not re-read files for verification — a single read pass is sufficient. Only re-read a specific file if its content is missing, truncated, or errored in the batch response, and only re-fetch that specific file.
4. After all files are successfully read, write the summary.

Summary requirements:
- Cover every file in the directory — never omit one.
- For each file, ground the description in its actual retrieved content (e.g., mention the file name and a factual detail drawn from what was read).
- If any file could not be read (permission error, binary/unreadable content, etc.), explicitly note that in the summary rather than omitting or guessing its contents.
- Keep the final summary concise, but never sacrifice coverage or correctness of what was actually found for brevity.

## Instrumentation

Emit the following metrics for each run, appended as a JSON line to `logs/<YYYY-MM-DD>.jsonl`:

- `tool_calls` — total number of tool invocations used
- `files_read` — number of distinct files successfully read
- `files_total` — number of files returned by `list_files`
- `batched_reads` — whether `read_files` batching was used (bool)
- `retry_reads` — count of individual re-reads due to errors/missing content
- `doc_grounding` — 1.0 if every summarized file's description traces to actual read content, else fraction grounded
- `fuzzy_correctness` — self-assessed correctness of the produced summary against retrieved content
- `latency_ms` — wall-clock time for the full run