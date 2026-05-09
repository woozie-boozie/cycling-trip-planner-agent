"""Pydantic schemas for tool inputs and outputs.

These are the *single source of truth* for tool typing:

  - Tool implementations consume the Input model
  - Anthropic's `input_schema` is generated from the Input model's JSON schema
  - Tool outputs are validated against the Output model before returning to the agent
  - The agent's system prompt can reference these field names confidently

Keep field names self-documenting (units in the name where ambiguous: `_km`, `_m`,
`_celsius`, etc.) so the agent doesn't need to guess.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------

Difficulty = Literal["easy", "moderate", "hard", "extreme"]
AccommodationType = Literal["camping", "hostel", "hotel", "guesthouse"]
Month = Literal[
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


# ---------------------------------------------------------------------------
# get_route
# ---------------------------------------------------------------------------


class Waypoint(BaseModel):
    """A point along a cycling route."""

    name: str = Field(description="City or town name")
    country: str = Field(description="ISO country name")
    distance_from_start_km: float = Field(
        ge=0, description="Cumulative distance from the route's start point in km"
    )
    is_ferry_required: bool = Field(
        default=False,
        description="True if reaching this waypoint requires a ferry (e.g. Rødby–Puttgarden)",
    )


class GetRouteInput(BaseModel):
    """Input for get_route."""

    start: str = Field(description="Starting city, e.g. 'Amsterdam'")
    end: str = Field(description="Destination city, e.g. 'Copenhagen'")
    daily_km_target: float = Field(
        default=80.0,
        gt=0,
        le=300,
        description="Cyclist's target distance per day in km. Used to compute estimated_days.",
    )


class GetRouteOutput(BaseModel):
    """Output for get_route — full route summary plus ordered waypoints."""

    start: str
    end: str
    total_distance_km: float = Field(ge=0)
    estimated_days: int = Field(ge=1, description="Total days assuming the daily_km_target")
    waypoints: list[Waypoint] = Field(
        description="Ordered list including start and end. Use to break trip into daily segments."
    )
    notes: str | None = Field(
        default=None,
        description="Free-text notes the agent should surface to the user (e.g. ferry crossings)",
    )


# ---------------------------------------------------------------------------
# find_accommodation
# ---------------------------------------------------------------------------


class Accommodation(BaseModel):
    """A single place to stay near a location."""

    name: str
    type: AccommodationType
    location: str = Field(description="City or town the accommodation is in")
    distance_from_location_km: float = Field(
        ge=0, description="Distance from the queried location's center"
    )
    estimated_price_eur_per_night: float = Field(ge=0)
    bike_friendly: bool = Field(
        default=True, description="True if secure bike storage / repair is available"
    )
    notes: str | None = None


class FindAccommodationInput(BaseModel):
    """Input for find_accommodation."""

    location: str = Field(description="City or town to find lodging near, e.g. 'Bremen'")
    types: list[AccommodationType] | None = Field(
        default=None,
        description=(
            "Optional filter by accommodation type. If None, returns a mix of all types. "
            "Use ['camping'] to honor a 'camping only' preference."
        ),
    )
    max_results: int = Field(default=5, ge=1, le=20)


class FindAccommodationOutput(BaseModel):
    """Output for find_accommodation — list of nearby places."""

    location: str
    results: list[Accommodation]


# ---------------------------------------------------------------------------
# get_weather
# ---------------------------------------------------------------------------


class GetWeatherInput(BaseModel):
    """Input for get_weather."""

    location: str = Field(description="City or town to get weather for")
    month: Month = Field(description="Month of travel — typical/historical weather is returned")


class GetWeatherOutput(BaseModel):
    """Output for get_weather — historical averages for the given location/month."""

    location: str
    month: Month
    avg_temp_celsius: float
    avg_high_celsius: float
    avg_low_celsius: float
    rain_days_per_month: int = Field(ge=0, le=31)
    avg_rain_mm: float = Field(ge=0)
    notes: str | None = Field(
        default=None,
        description=(
            "Free-text guidance the agent should surface to the user (e.g. prevailing wind, "
            "frequent rain warnings)."
        ),
    )


# ---------------------------------------------------------------------------
# get_elevation_profile
# ---------------------------------------------------------------------------


class GetElevationProfileInput(BaseModel):
    """Input for get_elevation_profile."""

    start: str = Field(description="Segment start city/town")
    end: str = Field(description="Segment end city/town")


class GetElevationProfileOutput(BaseModel):
    """Output for get_elevation_profile — terrain difficulty for a single segment."""

    start: str
    end: str
    distance_km: float = Field(ge=0)
    elevation_gain_m: int = Field(ge=0, description="Total ascent across the segment, in meters")
    elevation_loss_m: int = Field(ge=0, description="Total descent across the segment, in meters")
    max_grade_percent: float = Field(
        ge=0, le=100, description="Steepest gradient encountered as a percentage"
    )
    difficulty: Difficulty
    notes: str | None = None


# ---------------------------------------------------------------------------
# critique_trip_plan — self-critique tool the agent calls before finalizing
# ---------------------------------------------------------------------------


class DraftedDay(BaseModel):
    """A single day in the agent's draft plan, structured for critique.

    Required fields: day_number + distance_km. Everything else is optional but
    informative — the more the agent fills in, the more thorough the critique.
    """

    day_number: int = Field(ge=1)
    distance_km: float = Field(ge=0, description="Distance cycled this day in km")
    elevation_gain_m: int = Field(default=0, ge=0)
    difficulty: Difficulty | None = None
    accommodation_type: AccommodationType | None = Field(
        default=None,
        description="Where the cyclist sleeps THIS NIGHT (after riding day_number)",
    )
    accommodation_name: str | None = None
    has_ferry: bool = Field(
        default=False, description="True if this day involves a ferry crossing"
    )
    notes: str | None = None


CritiqueSeverity = Literal["info", "warning", "blocker"]
CritiqueCategory = Literal[
    "pacing",
    "accommodation_mismatch",
    "elevation_pacing",
    "consistency",
    "ferry_missing",
]


class CritiqueIssue(BaseModel):
    """A single issue surfaced by the critique."""

    severity: CritiqueSeverity
    category: CritiqueCategory
    message: str
    affects_days: list[int] = Field(default_factory=list)
    suggestion: str | None = None


CritiqueAssessment = Literal["ship_it", "minor_revisions", "major_revisions"]


class CritiqueTripPlanInput(BaseModel):
    """Input for critique_trip_plan."""

    days: list[DraftedDay] = Field(min_length=1)
    daily_km_target: float = Field(gt=0, description="The user's stated daily distance target")
    accommodation_preference: str = Field(
        default="any",
        description=(
            "Free-text describing the user's accommodation preference, e.g. "
            "'mostly camping', 'hostel every 3rd night', 'hotels every night'. "
            "The critique parses this for known patterns ('every Nth night', 'camping')."
        ),
    )


class CritiqueTripPlanOutput(BaseModel):
    """Output for critique_trip_plan — issues found + overall assessment.

    Agent uses this to decide whether to ship the plan, surface warnings to
    the user, or revise. `overall_assessment` is the headline:
      - ship_it          → present the plan as-is
      - minor_revisions  → surface the warnings to the user (Heads up section)
      - major_revisions  → revise the plan, optionally re-critique
    """

    issues: list[CritiqueIssue]
    overall_assessment: CritiqueAssessment
    summary: str
