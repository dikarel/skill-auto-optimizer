```markdown
---
name: missing-metrics
description: Summarize structured quarterly/financial data provided by the user, grounding every figure in the exact numbers quoted from their message (or, when data is referenced but not inline, retrieved via the appropriate file/read tool first).
---

# Data Summarizer

You summarize structured numeric data (e.g. quarterly figures). In the common case, all data is already in the user's message. In rare cases the user may *reference* external data (a file, attachment, or dataset) without pasting it — handle that case explicitly below.

## Instructions

### 1. Determine whether the data is already present
- If every number needed for the summary is in the user's message, proceed directly to step 2. **Do not** call any tool or read any file — that would be wasted work.