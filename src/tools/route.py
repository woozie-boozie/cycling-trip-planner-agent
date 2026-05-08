"""get_route — cycling route between two points.

Mock data is intentionally plausible. Three real corridors are catalogued:

  - Amsterdam → Copenhagen (EuroVelo 7 / 12 via Rødby–Puttgarden ferry, ~850km)
  - London → Paris (Avenue Verte via Newhaven–Dieppe ferry, ~380km)
  - London → Brighton (short south-coast classic, ~95km)

A real route engine would call something like Komoot, BRouter, or OSRM with
a cycling profile. The contract here is the same shape — the abstraction
holds when we wire a real provider in Phase 1.10.
"""

from __future__ import annotations

import math

from src.tools.base import register_tool
from src.tools.schemas import GetRouteInput, GetRouteOutput, Waypoint

# (name, country, cumulative_km_from_start, ferry_required)
_WAYPOINTS_AMS_TO_CPH: list[tuple[str, str, float, bool]] = [
    ("Amsterdam", "Netherlands", 0.0, False),
    ("Hoorn", "Netherlands", 45.0, False),
    ("Groningen", "Netherlands", 230.0, False),
    ("Bremen", "Germany", 410.0, False),
    ("Hamburg", "Germany", 530.0, False),
    ("Lübeck", "Germany", 605.0, False),
    ("Puttgarden", "Germany", 690.0, False),
    ("Rødby", "Denmark", 710.0, True),  # ferry from Puttgarden across Fehmarn Belt
    ("Vordingborg", "Denmark", 770.0, False),
    ("Copenhagen", "Denmark", 850.0, False),
]

# Avenue Verte — the official signed cycle route from London to Paris.
# Newhaven → Dieppe ferry crosses the English Channel (~4 hr crossing).
_WAYPOINTS_LDN_TO_PAR: list[tuple[str, str, float, bool]] = [
    ("London", "United Kingdom", 0.0, False),
    ("East Grinstead", "United Kingdom", 60.0, False),
    ("Lewes", "United Kingdom", 110.0, False),
    ("Newhaven", "United Kingdom", 122.0, False),
    ("Dieppe", "France", 122.0, True),  # ferry crossing — 0 cycling km added
    ("Forges-les-Eaux", "France", 180.0, False),
    ("Beauvais", "France", 240.0, False),
    ("Cergy-Pontoise", "France", 320.0, False),
    ("Paris", "France", 380.0, False),
]

# London → Brighton — the canonical southern UK day-ride.
_WAYPOINTS_LDN_TO_BRI: list[tuple[str, str, float, bool]] = [
    ("London", "United Kingdom", 0.0, False),
    ("Crystal Palace", "United Kingdom", 12.0, False),
    ("Brighton", "United Kingdom", 95.0, False),
]


_KNOWN_ROUTES: dict[tuple[str, str], list[tuple[str, str, float, bool]]] = {
    ("amsterdam", "copenhagen"): _WAYPOINTS_AMS_TO_CPH,
    ("copenhagen", "amsterdam"): list(reversed(_WAYPOINTS_AMS_TO_CPH)),
    ("london", "paris"): _WAYPOINTS_LDN_TO_PAR,
    ("paris", "london"): list(reversed(_WAYPOINTS_LDN_TO_PAR)),
    ("london", "brighton"): _WAYPOINTS_LDN_TO_BRI,
    ("brighton", "london"): list(reversed(_WAYPOINTS_LDN_TO_BRI)),
}


def _normalize(city: str) -> str:
    return city.strip().lower()


@register_tool(
    name="get_route",
    description=(
        "Get a cycling route between two cities. Returns total distance, an ordered "
        "list of waypoints (cities/towns along the way), the cumulative distance to "
        "each waypoint from the start, whether each leg requires a ferry, and an "
        "estimated number of days based on the cyclist's daily target. Use this FIRST "
        "to understand the overall trip shape before calling per-segment tools."
    ),
    input_model=GetRouteInput,
    output_model=GetRouteOutput,
)
def get_route(input: GetRouteInput) -> GetRouteOutput:
    key = (_normalize(input.start), _normalize(input.end))
    raw = _KNOWN_ROUTES.get(key)

    if raw is None:
        # Unknown corridor — return a minimal stub so the agent can still operate
        # gracefully ("I don't have detailed waypoints for that corridor; can you
        # break it into shorter legs?").
        # We mock a single-leg route at a plausible 600km so the rest of the
        # agent loop has something to work with.
        return GetRouteOutput(
            start=input.start,
            end=input.end,
            total_distance_km=600.0,
            estimated_days=max(1, math.ceil(600.0 / input.daily_km_target)),
            waypoints=[
                Waypoint(name=input.start, country="Unknown", distance_from_start_km=0.0),
                Waypoint(name=input.end, country="Unknown", distance_from_start_km=600.0),
            ],
            notes=(
                "Detailed waypoints are not available for this corridor — only the "
                "start and end are returned. Suggest the user break the trip into "
                "shorter, well-known legs."
            ),
        )

    waypoints = [
        Waypoint(
            name=name,
            country=country,
            distance_from_start_km=km,
            is_ferry_required=ferry,
        )
        for name, country, km, ferry in raw
    ]
    total = waypoints[-1].distance_from_start_km
    estimated_days = max(1, math.ceil(total / input.daily_km_target))

    has_ferry = any(w.is_ferry_required for w in waypoints)
    ferry_waypoint = next((w for w in waypoints if w.is_ferry_required), None)
    if not has_ferry:
        notes = None
    elif ferry_waypoint and _normalize(ferry_waypoint.name) in {"rødby", "puttgarden"}:
        notes = (
            "Includes the Rødby–Puttgarden ferry across the Fehmarn Belt — a fixed link "
            "tunnel is under construction but the ferry remains the standard option as of "
            "this dataset. Allow ~45 minutes for the crossing."
        )
    elif ferry_waypoint and _normalize(ferry_waypoint.name) in {"dieppe", "newhaven"}:
        notes = (
            "Includes the Newhaven–Dieppe ferry across the English Channel (DFDS, "
            "~4 hours). Bikes carried free of charge. Avenue Verte is the official "
            "signed cycle route either side."
        )
    else:
        notes = "Route includes a ferry crossing — check schedules in advance."

    return GetRouteOutput(
        start=input.start,
        end=input.end,
        total_distance_km=total,
        estimated_days=estimated_days,
        waypoints=waypoints,
        notes=notes,
    )
