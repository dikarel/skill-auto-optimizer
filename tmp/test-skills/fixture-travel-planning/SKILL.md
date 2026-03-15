```markdown
---
name: travel-planning
description: Multi-day travel itineraries with tool-grounded data, constraint enforcement, JSON output.
---

<!-- cache_control: ephemeral -->

# Travel Planner

Trigger: user requests a trip itinerary.

**MANDATORY: Execute ALL steps below in ONE response. Do NOT stop after searching. You MUST produce the final JSON file before ending your turn.**

## Steps (all required, sequential, single turn)

1. **Search accommodations** — `web_search` per city (pet-friendly if required, budget-appropriate). Record: name, neighborhood, nightly rate, source URL.
2. **Search restaurants** — `web_search` per city for cuisine-matching restaurants. Record: name, cuisine, avg meal cost, source URL.
3. **Search attractions** — `web_search` per city for top activities. Record: name, type, admission cost, source URL.
4. **Compile itinerary** — day-by-day plan using ONLY search results. Zero invented places.
5. **Write JSON** — `create_file` at user path (default `/app/output/itinerary.json`). Must match schema below exactly. Must be complete valid JSON.
6. **Self-check** — `read_file` the written file. Verify: valid JSON, all days present, `estimated_total_cost` = Σ `daily_est_cost`, total ≤ budget, all hard constraints met. Fix & rewrite if invalid.

**STOP CONDITION: Only stop AFTER step 6 is complete and verified. If you run out of search results, use what you have — but you MUST still produce the JSON file.**

## Hard Constraints (blocking — task fails if ANY violated)

- **Budget**: `estimated_total_cost` ≤ stated budget
- **No-fly**: if specified → ground transport only; include driving distance/time between cities
- **Pet-friendly**: if required → every accommodation must be pet-friendly (with source)
- **Full duration**: cover every calendar day — never truncate
- **All cities**: visit every requested destination
- **Output file**: JSON must be written to specified path via `create_file`

## JSON Schema

```json
{
  "trip": {
    "title": "string",
    "travelers": 0,
    "origin": "string",
    "dates": {"start":"YYYY-MM-DD","end":"YYYY-MM-DD"},
    "total_budget": 0,
    "estimated_total_cost": 0,
    "transportation": "string",
    "pet_friendly": false,
    "preferred_cuisines": ["string"],
    "cities_visited": ["string"],
    "days": [
      {
        "day": 1,
        "date": "YYYY-MM-DD",
        "city": "string",
        "accommodation": {
          "name":"string","neighborhood":"string",
          "nightly_rate":0,"pet_friendly":false,"source_url":"string"
        },
        "meals": {
          "breakfast":{"name":"string","cuisine":"string","est_cost":0,"source_url":"string"},
          "lunch":{"name":"string","cuisine":"string","est_cost":0,"source_url":"string"},
          "dinner":{"name":"string","cuisine":"string","est_cost":0,"source_url":"string"}
        },
        "activities": [
          {"name":"string","type":"string","est_cost":0,"source_url":"string"}
        ],
        "daily_est_cost": 0,
        "transport_notes": "string"
      }
    ]
  }
}
```

- Every `source_url` from search results (citation).
- 2–3 activities/day.
- `daily_est_cost` = accommodation + meals + activities + transport for that day.
- `estimated_total_cost` = Σ `daily_est_cost`.

## Quality Guardrails

- Cite every place via `source_url` — citation target ≥ 0.50.
- Never invent names without search grounding — hallucination target ≤ 0.25.
- Tight budget → prefer cheaper options, note trade-offs.
- Preserve all user edge cases (dietary, accessibility, pet, transport).
- If search yields limited results, still use what was found — never skip file creation.

## Instrumentation

Emit per run to `logs/<YYYY-MM-DD>.jsonl`:

```json
{"perf":{"input_tokens":0,"output_tokens":0,"total_tokens":0,"turns":1,"latency_ms":0,"estimated_cost_usd":0.0},"quality":{"citations_count":0,"tool_calls_count":0,"grounding_sources":[],"days_covered":0,"budget_remaining":0.0,"hard_constraints_met":true}}
```
```