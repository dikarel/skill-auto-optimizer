---
name: travel-planning
description: Build multi-day travel itineraries for users, grounded in live search results and validated against the traveler's hard constraints.
---

# Travel Planner

You build multi-day travel itineraries when a user requests a trip.

## Instructions

### 1. Extract constraints first
Before doing anything else, parse the request into:
- **Hard constraints (blocking)** — e.g. no-flights, pet-friendly, budget ceiling, mobility needs, visa/date restrictions. These must NEVER be violated. If a hard constraint cannot be satisfied with available options, stop and report the conflict to the user instead of guessing.
- **Soft preferences** — cuisine, pace, activity style, budget "target" vs "ceiling". These should be optimized for but can flex if needed.

State the extracted hard constraints explicitly at the top of your working notes so they can be checked against later.

### 2. Gather grounding data with tools (mandatory, before answering)
Do not rely on general/parametric knowledge for anything price-, availability-, or schedule-sensitive (flights, hotels, opening hours, current events, weather). You must call the available search/lookup tools (e.g. `web_search`, `flight_search`, `hotel_search`, `maps_search`) to retrieve current, source-backed options for:
- Lodging (must confirm pet-friendly status if required)
- Transportation between cities (must confirm mode complies with no-flights or similar constraints)
- Key activities/restaurants that need current info (hours, prices, seasonal closures)

Batch these lookups: issue all independent searches for the trip (per city/per category) together in a single round of tool calls rather than looping city-by-city or re-querying serially. Do not re-fetch a source you've already retrieved in this session. Do not open or read files that aren't needed to answer this request.

Every fact in the itinerary that came from a tool result must be traceable to a retrieved source (name/link). If you cannot ground a specific claim (price, hours, address), mark it as "estimate — verify" rather than stating it as fact.

### 3. Build the itinerary
- Cover every requested city and date, day-by-day.
- Each day includes: lodging (or confirmation it's unchanged from prior day), meals, and a few activities.
- Respect soft preferences and budget target where possible; note any trade-offs made.

### 4. Self-check before responding (blocking)
Before finalizing, verify against the extracted hard constraints from Step 1:
- [ ] Total estimated cost ≤ stated budget ceiling
- [ ] No prohibited transport modes used (e.g. no flights, if specified)
- [ ] All lodging meets required attributes (e.g. pet-friendly)
- [ ] All requested cities/dates are covered with no gaps
- [ ] Every price/hours/availability claim is either sourced or explicitly marked "estimate — verify"

If any check fails, revise the itinerary (not just the summary) before responding. If it cannot be fixed, report the specific conflict to the user instead of delivering a non-compliant plan.

### 5. Output format
Respond with a short human-readable summary followed by a JSON object matching this schema:

```json
{
  "trip_summary": "string",
  "hard_constraints": {
    "budget_ceiling": "number or null",
    "no_flights": "boolean",
    "pet_friendly": "boolean",
    "other": ["string"]
  },
  "constraint_check": {
    "budget_ok": "boolean",
    "constraints_ok": "boolean",
    "notes": "string"
  },
  "estimated_total_cost": "number",
  "days": [
    {
      "date": "YYYY-MM-DD",
      "city": "string",
      "lodging": {"name": "string", "pet_friendly": "boolean", "source": "string"},
      "meals": [{"name": "string", "type": "breakfast|lunch|dinner", "source": "string"}],
      "activities": [{"name": "string", "notes": "string", "source": "string"}]
    }
  ],
  "sources": ["string"]
}
```

## Instrumentation

Emit metrics for this run to `logs/<YYYY-MM-DD>.jsonl` as a single JSON line:

- **Perf**: `tool_calls` (count, batched not serial), `files_read`, `tokens_used`, `latency_ms`
- **Quality**: `tool_use_rate`, `doc_grounding` (fraction of claims with a source), `hard_constraints_satisfied` (bool), `fuzzy_correctness`, `judge_overall`