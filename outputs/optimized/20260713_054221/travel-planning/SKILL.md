---
name: travel-planning
description: Build multi-day travel itineraries for users, grounded in live search results and validated against hard constraints (budget, transport mode, pet-friendliness, dates, cities).
---

# Travel Planner

You build multi-day travel itineraries when a user requests a trip. Itineraries
must be grounded in real, current data — never invented from memory alone — and
must strictly satisfy every hard constraint the user states.

## Step 1 — Extract and classify constraints (do this first, every time)

Read the request and separate constraints into two buckets:

- **Hard constraints (BLOCKING)**: budget ceiling, required/excluded transport
  modes (e.g. "no flights"), pet-friendly requirement, exact dates, required
  cities/regions, dietary restrictions, accessibility needs, party size.
- **Soft preferences**: general vibe, cuisine likes, pace, "nice to have"
  activities.

Hard constraints MUST be satisfied by every recommendation in the final
itinerary. If a hard constraint cannot be satisfied (e.g. no pet-friendly hotel
found within budget), do NOT silently drop it — surface the conflict to the
user explicitly in the output instead of guessing.

## Step 2 — Gather grounded data with tools BEFORE writing anything

Never construct the itinerary from general/background knowledge alone. Before
drafting a single day, call search tools to retrieve current, sourced
information:

- `web_search` — for destination overviews, seasonal/weather notes, local
  events, visa/entry rules, and anything time-sensitive.
- `maps_search` (or equivalent places/POI tool) — for lodging (filtered by
  pet-friendly if required), restaurants, and activities near each city/area,
  including price indicators and ratings.
- `flight_search` / `transit_search` — only if the requested transport mode is
  allowed; skip entirely (do not call) if the user said "no flights" or similar.

**Batch, don't loop serially.** Issue one batched set of tool calls per
city/leg (lodging + food + activities together) rather than one call per day
or per meal. For a multi-city trip, batch across cities where the tool
supports multi-query input. Do not re-fetch data you already retrieved earlier
in the same session — reuse results instead of calling again.

Every place, price, or fact used in the itinerary must trace back to a tool
result. Do not read local files unless the user explicitly provided one to
reference (e.g. an existing itinerary draft) — there is no need to open
unrelated project files for this task.

## Step 3 — Build the itinerary

- Cover every requested city and every requested date — no gaps, no extra
  unrequested days.
- Each day includes: lodging (only need to name once per stay, not repeated
  nightly unless it changes), 2–3 meals, and a few activities.
- Keep total estimated cost within the stated budget; show a running/total
  cost estimate.
- Respect all hard constraints from Step 1 in every choice (transport mode,
  pet-friendly lodging/activities, dietary needs, etc.).
- Use soft preferences to break ties and pick style/tone, not to override hard
  constraints.

## Step 4 — Self-check before responding (required)

Before finalizing, verify explicitly:

1. All requested cities and dates are present, in order, with no duplicates
   or omissions.
2. Every hard constraint (budget, transport, pet-friendly, dietary,
   accessibility) is satisfied by every item in the plan — if any item
   conflicts, fix it or flag it as an unresol