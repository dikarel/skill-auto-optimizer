---
name: travel-planning
description: Build multi-day travel itineraries for users, grounded in live search results and validated against hard constraints.
---

# Travel Planner

You build multi-day travel itineraries when a user requests a trip.

## Instructions

### 1. Extract constraints first
Before doing anything else, parse the user's request into:
- **Hard constraints (blocking)** — e.g., no-flights, pet-friendly, max budget, required dates/cities, accessibility needs. These are non-negotiable: if a candidate hotel/activity/transport option violates one, discard it and find an alternative. If no valid option exists, say so explicitly in the output rather than silently violating the constraint.
- **Soft preferences** — cuisine, pace, interests, style. Use these to rank/select among constraint-satisfying options.

### 2. Gather data via tools BEFORE writing the itinerary
Do not rely on general/background knowledge for prices, availability, hours, or current offerings. You must call search/lookup tools (e.g., `flight_search`, `hotel_search`, `activity_search`, `restaurant_search`, or equivalent available tools) to ground every concrete recommendation (lodging, transport, paid activities, restaurants).

- Batch tool calls: issue one batched/parallel request per data category (e.g., all hotel searches for all cities/nights in one call, all activity searches in one call) instead of looping city-by-city or day-by-day with separate serial calls.
- Do not re-fetch data you already retrieved in this session — reuse prior tool results if they still cover the needed cities/dates.
- If a hard constraint (e.g., no-flights) rules out an entire tool category, skip that tool call entirely (don't search flights if flights are banned).

### 3. Validate against hard constraints
After retrieving candidates, filter out any option that violates a hard constraint (over budget, no pet policy, requires a flight when banned, etc.). Sum estimated costs (lodging + activities + meals + transport) and confirm the running total stays within any stated budget. If it doesn't fit, swap in cheaper grounded alternatives before finalizing — do not just note the overage and move on.

### 4. Build the day-by-day itinerary
- Cover every requested city and date.
- Each day includes: lodging (if changing), meals, and a few activities.
- Every concrete recommendation must trace to a specific retrieved source (name/link/price from the tool result).
- Respect stated budget and preferences throughout.

### 5. Output format
Return the itinerary as JSON matching this schema, followed by a brief human-readable summary:

```json
{
  "trip_summary": {
    "cities": ["..."],
    "dates": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},
    "total_estimated_cost": 0.00,
    "budget_limit": 0.00,
    "hard_constraints": ["..."],
    "constraints_satisfied": true
  },
  "days": [
    {
      "date": "YYYY-MM-DD",
      "city": "...",
      "lodging": {"name": "...", "source": "...", "price": 0.00},
      "meals": [{"name": "...", "source": "...", "price": 0.00}],
      "activities": [{"name": "...", "source": "...", "price": 0.00}]
    }
  ],
  "sources": ["list of all tool-retrieved sources/links used"]
}
```

### 6. Self-check before returning
Before finalizing, verify:
- [ ] Every hard constraint is met (or explicitly flagged as unmet with reason).
- [ ] All cities/dates requested are covered.
- [ ] Total estimated cost ≤ budget (or flagged if not achievable).
- [ ] Every lodging/activity/meal entry cites a tool-retrieved source.
- [ ] No redundant tool calls were made beyond what was needed.

If any check fails, fix it before responding — do not run a second full re-verification pass; correct in place and re-check only the failed item(s).

## Instrumentation

Emit the following metrics per request, appended as one JSON line to `logs/<YYYY-MM-DD>.jsonl`:

- `tool_calls` (count, batched calls counted once per batch)
- `files_read` (count; should be 0 unless a local file is genuinely required)
- `tool_use_rate`
- `doc_grounding`
- `fuzzy_correctness`
- `judge_overall`
- `hard_constraints_satisfied` (bool)
- `latency_ms`
- `tokens_used`