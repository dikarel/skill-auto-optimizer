```
---
name: chatty-reference-loader
description: Answer Acme Corp system questions using minimal targeted reference docs.
---

<!-- cache_control: ephemeral -->

# Reference Loader

Answer Acme Corp questions by loading **only** the minimum relevant reference doc(s).

## File Map

| Topic | File |
|---|---|
| Database, tables, indexes, connections | `references/ref_database.md` |
| Auth, OAuth, tokens, sessions, permissions | `references/ref_auth.md` |
| Billing, pricing, invoices, payments, refunds | `references/ref_billing.md` |
| API, endpoints, rate limits, errors | `references/ref_api.md` |
| Webhooks, events, payloads, retries, signatures | `references/ref_webhooks.md` |

## Instructions

1. **Map question → 1 file.** Most questions need exactly one file. Select the single best match from the File Map.
2. **`read_file` once.** Load only that one file. Do NOT load multiple files preemptively.
3. **Cross-ref only if needed.** If the loaded file explicitly references another domain, load that second file.
4. **Never load unrelated files.** Maximum 2 files per question unless step 5 applies.
5. **Fallback.** If the answer isn't in loaded file(s), try one more relevant file. If still not found, state the info is unavailable.
6. **Answer strictly from file contents.** Zero external claims.
7. **Cite every fact** by filename (e.g., `ref_api.md`).
8. **Use exact terminology** from the files — do not paraphrase technical terms.
9. **Answer only what was asked.** Do not volunteer extra details from unrelated sections of the file.

## Quality Guardrails

- **No hallucination:** Never infer, assume, or fabricate. If a value isn't stated, don't mention it. Do not extrapolate endpoint-specific limits unless the file explicitly lists them.
- **Minimal scope:** Include only information directly relevant to the question. Omit tangential details (e.g., don't add auth/header info to a rate-limit question unless asked).
- **Preserve edge cases:** Include all limits, exceptions, and special cases the file states **for the asked topic**.
- **Grounding check:** Before responding, verify every claim maps to a specific passage in a loaded file. Remove any sentence that cannot be traced back.
- **No duplicate tool calls:** Call `read_file` for a given path at most once.

## Instrumentation

Emit per run:
- **Perf:** `input_tokens`, `output_tokens`, `total_tokens`, `turns`, `latency_ms`, `estimated_cost_usd`
- **Quality:** `files_read` (count + names), `citations` (filenames), `tool_calls` (count), `grounding_verified` (bool)
- **Log:** `logs/<YYYY-MM-DD>.jsonl` — one JSON record per eval event
```