"""get_elevation_profile — terrain difficulty for a single segment.

The Amsterdam → Copenhagen corridor is famously *flat* — the entire Dutch and
Danish portions sit near sea level, and the German segments cross gentle
moraine. Mock data reflects this so the agent gives an honest "this is an
easy corridor" rather than fabricating mountains.

Real elevation data lives in DEMs (digital elevation models like SRTM); the
abstraction here is the same shape a real provider would use.
"""

from __future__ import annotations

from src.tools.base import register_tool
from src.tools.schemas import (
    Difficulty,
    GetElevationProfileInput,
    GetElevationProfileOutput,
)

# Per-segment terrain. Ordered as they appear on the Ams→Cph corridor;
# reverse direction (Cph→Ams) is symmetrical.
# (start, end, distance_km, gain_m, loss_m, max_grade_pct, difficulty, note)
_SegmentRow = tuple[str, str, float, int, int, float, Difficulty, str | None]

_SEGMENTS: list[_SegmentRow] = [
    # Amsterdam → Copenhagen corridor
    ("amsterdam", "hoorn", 45.0, 30, 25, 1.0, "easy", "Flat polders. Possible headwinds."),
    ("hoorn", "groningen", 185.0, 80, 70, 1.5, "easy", "Mostly flat, dyke-side cycling."),
    ("groningen", "bremen", 180.0, 120, 100, 2.0, "easy", "Crosses German lowlands — flat with gentle rolls."),
    ("bremen", "hamburg", 120.0, 90, 80, 2.0, "easy", "Following the Elbe valley — flat."),
    ("hamburg", "lübeck", 75.0, 110, 90, 3.0, "moderate", "Some gentle rolling moraine outside Hamburg."),
    ("lübeck", "puttgarden", 85.0, 100, 95, 2.5, "easy", "Coastal flatland through Schleswig-Holstein."),
    ("puttgarden", "rødby", 20.0, 5, 5, 0.5, "easy", "Ferry crossing — minimal cycling distance."),
    ("rødby", "vordingborg", 60.0, 60, 55, 2.0, "easy", "Flat Lolland and Falster islands. Wind exposure."),
    ("vordingborg", "copenhagen", 80.0, 90, 80, 2.5, "easy", "Crosses Storstrøm bridge then gentle Zealand terrain."),
    # Avenue Verte (London → Paris)
    ("london", "east grinstead", 60.0, 280, 180, 4.0, "moderate", "South London hills, then Greenwich Park climb. Forest of Ashdown approach."),
    ("east grinstead", "lewes", 50.0, 320, 380, 5.0, "moderate", "Crosses the South Downs ridge — proper climbs and a steep descent into Lewes."),
    ("lewes", "newhaven", 12.0, 40, 80, 2.0, "easy", "Short, flat ride along the Ouse valley to the ferry port."),
    ("newhaven", "dieppe", 0.0, 0, 0, 0.0, "easy", "Channel ferry crossing — no cycling. ~4 hour journey."),
    ("dieppe", "forges-les-eaux", 58.0, 250, 150, 4.0, "moderate", "Climb out of Dieppe, then rolling Pays de Bray farmland."),
    ("forges-les-eaux", "beauvais", 60.0, 180, 200, 3.0, "easy", "Gentle agricultural rolls through Picardy."),
    ("beauvais", "cergy-pontoise", 80.0, 150, 130, 3.0, "easy", "Approach to the Paris basin — mostly flat."),
    ("cergy-pontoise", "paris", 60.0, 100, 120, 2.0, "easy", "Riverside paths along the Seine into central Paris. Watch for traffic in the last 10km."),
    # London → Brighton (south coast classic)
    ("london", "crystal palace", 12.0, 80, 30, 5.0, "easy", "Urban climb out of central London to Crystal Palace ridge."),
    ("crystal palace", "brighton", 83.0, 400, 420, 6.0, "hard", "South Downs the whole way — Ditchling Beacon's the steepest climb in the south of England (16% near top)."),
]

_LOOKUP: dict[tuple[str, str], _SegmentRow] = {(s, e): row for row in _SEGMENTS for s, e in [(row[0], row[1])]}
# Add reverse direction with mirrored gain/loss
for row in _SEGMENTS:
    s, e, dist, gain, loss, grade, diff, note = row
    _LOOKUP[(e, s)] = (e, s, dist, loss, gain, grade, diff, note)


def _normalize(s: str) -> str:
    return s.strip().lower()


@register_tool(
    name="get_elevation_profile",
    description=(
        "Get terrain difficulty for a single segment between two adjacent "
        "waypoints — total elevation gain in meters, elevation loss, max "
        "gradient, and a difficulty rating (easy/moderate/hard/extreme). "
        "Use once per daily segment after building the route, to advise on "
        "pacing and rest-day placement."
    ),
    input_model=GetElevationProfileInput,
    output_model=GetElevationProfileOutput,
)
def get_elevation_profile(input: GetElevationProfileInput) -> GetElevationProfileOutput:
    key = (_normalize(input.start), _normalize(input.end))
    row = _LOOKUP.get(key)
    if row is None:
        # Fall back to a flat-ish default with a note rather than 500-error
        # the agent. Keeps the loop moving on unknown segments.
        return GetElevationProfileOutput(
            start=input.start,
            end=input.end,
            distance_km=80.0,
            elevation_gain_m=150,
            elevation_loss_m=150,
            max_grade_percent=3.0,
            difficulty="moderate",
            notes=(
                "Mock data — segment not in the catalog. Treated as a 'moderate "
                "rolling terrain' default."
            ),
        )

    _, _, dist, gain, loss, grade, diff, note = row
    return GetElevationProfileOutput(
        start=input.start,
        end=input.end,
        distance_km=dist,
        elevation_gain_m=gain,
        elevation_loss_m=loss,
        max_grade_percent=grade,
        difficulty=diff,
        notes=note,
    )
