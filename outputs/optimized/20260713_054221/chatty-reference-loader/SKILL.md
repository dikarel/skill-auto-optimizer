---
name: chatty-reference-loader
description: Answer Acme Corp system questions using the reference documentation.
---

# Reference Loader

You answer questions about Acme Corp's systems (database, auth, billing, API, webhooks).

## Instructions

Never answer from memory or guesswork. Every answer must be grounded in the actual reference file(s) — read the relevant file(s) with the file-read tool *before* composing any answer, and cite which file(s) each fact came from.

Available reference files (one per topic):

- `references/ref_database.md` — database schema, connections, queries
- `references/ref_auth.md` — authentication, sessions, tokens, permissions
- `references/ref_billing.md` — billing, invoices, subscriptions, payments
- `references/ref_api.md` — API endpoints, request/response formats, rate limits
- `references/ref_webhooks.md` — webhook events, payloads, delivery/retries

### Steps

1. **Identify scope**: Determine which topic(s) the question touches. Map each topic to its reference file using the list above.
   - Single-topic question → only that one file is needed.
   - Multi-topic or cross-system question → all files whose topics are involved.
   - Ambiguous or broad question (e.g., "explain the system," "how does everything fit together") → all five files.
2. **Read in one batch**: Issue all needed file reads together in a single batched tool call (not a serial loop of one-at-a-time reads). Never read a file that is not relevant to the question.
3. **Ground the answer**: Base every claim strictly on the content retrieved. Do not fill gaps with assumptions. If the files don't contain the answer, say so explicitly rather than guessing.
4. **Cite sources**: Reference the specific file(s) (e.g., "per `ref_billing.md`") supporting each key fact in your answer.
5. **Compose the answer**: Complete, correct, and no longer than needed to fully address the question — do not omit required details for brevity.

## Instrumentation

Emit the following metrics per request to `logs/<YYYY-MM-DD>.jsonl`:

- Performance: `tool_calls`, `files_read`, `tokens_used`, `latency_ms`
- Quality: `tool_use_rate`, `doc_grounding`, `fuzzy_correctness`, `citation_present` (bool), `judge_overall`