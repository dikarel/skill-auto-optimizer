---
name: serial-scriptless
description: Summarize the contents of a directory of files.
---

# Directory Summarizer

You summarize every file in a target directory.

## Instructions

Work strictly one file at a time. **Do not batch reads and do not use any helper script or shell loop** — batching hides errors, so it is not allowed.

Procedure:

1. Call `list_files` on the directory to get the list of filenames.
2. For **each** file, individually call `read_file` on that one file. Never read more than one file per call.
3. After you have read every file once, do a **mandatory second verification pass**: call `read_file` again on **each** file, one at a time, to confirm the contents did not change.
4. Only after both full passes are complete, write the summary.

Read the files sequentially in the order returned by `list_files`. Never skip a file, and never combine reads. The `read_files` batch tool is prohibited — always use single `read_file` calls.

Produce a short summary of what the directory contains.
