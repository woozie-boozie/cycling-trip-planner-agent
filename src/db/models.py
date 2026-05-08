"""SQLModel ORM tables for tool data.

Five tables, one per kind of reference data:

  - routes / waypoints   — get_route corridors
  - accommodations       — find_accommodation per-city catalog
  - weather_norms        — get_weather (per location, per month)
  - elevation_segments   — get_elevation_profile (per start→end pair)

Design notes:
  - All string lookups (city names, segment endpoints) are normalized to
    lowercase and indexed. The normalization happens in tool functions so
    the column convention is "lowercase already."
  - Literal/enum types from `src.tools.schemas` are stored as plain strings.
    The Pydantic schemas at the boundary re-validate them, so invalid values
    can't survive a round-trip.
  - We don't use Alembic for migrations yet — this is a case study, and
    `SQLModel.metadata.create_all()` (called by db.init_db) is sufficient.
"""

from __future__ import annotations

from sqlmodel import Field, SQLModel


class Route(SQLModel, table=True):
    """A canonical corridor between two cities.

    Waypoints are queried separately by route_id rather than via
    ORM Relationship — keeps SQLModel's typing simple and avoids the
    `Mapped[]` annotation requirement that SQLAlchemy 2.x adds for
    bidirectional relationships.
    """

    __tablename__ = "routes"

    id: int | None = Field(default=None, primary_key=True)
    start_lower: str = Field(index=True, description="Lowercased start city, used for lookups")
    end_lower: str = Field(index=True, description="Lowercased end city")
    start_display: str
    end_display: str
    total_distance_km: float
    notes: str | None = None


class Waypoint(SQLModel, table=True):
    """A single ordered point along a Route.

    Linked to its parent Route via `route_id` (foreign key). Tools query
    waypoints by `route_id` and `sequence` rather than via a relationship,
    which keeps the data access pattern explicit.
    """

    __tablename__ = "waypoints"

    id: int | None = Field(default=None, primary_key=True)
    route_id: int = Field(foreign_key="routes.id", index=True)
    sequence: int = Field(description="Order within the route, 0-indexed")
    name: str
    country: str
    distance_from_start_km: float
    is_ferry_required: bool = False


class Accommodation(SQLModel, table=True):
    """A single place to stay near a city."""

    __tablename__ = "accommodations"

    id: int | None = Field(default=None, primary_key=True)
    location_lower: str = Field(index=True)
    name: str
    type: str = Field(description="camping | hostel | hotel | guesthouse")
    location: str
    distance_from_location_km: float
    estimated_price_eur_per_night: float
    bike_friendly: bool = True
    notes: str | None = None


class WeatherNorm(SQLModel, table=True):
    """Climate norm for a single (location, month) pair."""

    __tablename__ = "weather_norms"

    id: int | None = Field(default=None, primary_key=True)
    location_lower: str = Field(index=True)
    month: str = Field(index=True, description="Full month name e.g. 'June'")
    avg_temp_celsius: float
    avg_high_celsius: float
    avg_low_celsius: float
    rain_days_per_month: int
    avg_rain_mm: float
    notes: str | None = None


class ElevationSegment(SQLModel, table=True):
    """Terrain profile between two adjacent points."""

    __tablename__ = "elevation_segments"

    id: int | None = Field(default=None, primary_key=True)
    start_lower: str = Field(index=True)
    end_lower: str = Field(index=True)
    distance_km: float
    elevation_gain_m: int
    elevation_loss_m: int
    max_grade_percent: float
    difficulty: str = Field(description="easy | moderate | hard | extreme")
    notes: str | None = None
