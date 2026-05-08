"""Seed the database with the tool data dicts that previously lived in code.

Idempotent: drops + re-inserts every table on each run. We're not in
production with real users yet, so a clean reload on each `make seed` is
the right semantics.

Reads from the Python data the case study originally shipped with — this
preserves the architecture story ("the dict was a database all along; we
just gave it a real backend").

Run via:
    .venv/bin/python -m src.db.seed
"""

from __future__ import annotations

import asyncio

import structlog
from sqlmodel import delete

from src.db import get_async_session, init_db
from src.db.models import Accommodation, ElevationSegment, Route, Waypoint, WeatherNorm

# Pull existing in-code data — this is the architecture proof:
# the dicts were always going to graduate to a real datastore.
from src.tools.accommodation import _CATALOG as ACCOM_CATALOG
from src.tools.elevation import _SEGMENTS as ELEV_SEGMENTS
from src.tools.route import _KNOWN_ROUTES
from src.tools.weather import _CLIMATE as WEATHER_CLIMATE

log = structlog.get_logger(__name__)


def _norm(s: str) -> str:
    return s.strip().lower()


async def seed_routes() -> int:
    """Populate routes + waypoints from the in-code corridor catalog."""
    inserted = 0
    async with get_async_session() as session:
        await session.execute(delete(Waypoint))
        await session.execute(delete(Route))
        seen: set[tuple[str, str]] = set()
        for (start_lower, end_lower), waypoints in _KNOWN_ROUTES.items():
            if (start_lower, end_lower) in seen:
                continue
            seen.add((start_lower, end_lower))
            start_display = waypoints[0][0]
            end_display = waypoints[-1][0]
            total_km = waypoints[-1][2]
            route = Route(
                start_lower=start_lower,
                end_lower=end_lower,
                start_display=start_display,
                end_display=end_display,
                total_distance_km=total_km,
                notes=None,  # ferry note is computed at query time, not stored
            )
            session.add(route)
            await session.flush()  # populate route.id

            for sequence, (name, country, km, ferry) in enumerate(waypoints):
                session.add(
                    Waypoint(
                        route_id=route.id,  # type: ignore[arg-type]
                        sequence=sequence,
                        name=name,
                        country=country,
                        distance_from_start_km=km,
                        is_ferry_required=ferry,
                    )
                )
            inserted += 1
        await session.commit()
    return inserted


async def seed_accommodations() -> int:
    inserted = 0
    async with get_async_session() as session:
        await session.execute(delete(Accommodation))
        for location_lower, items in ACCOM_CATALOG.items():
            for a in items:
                session.add(
                    Accommodation(
                        location_lower=location_lower,
                        name=a.name,
                        type=a.type,
                        location=a.location,
                        distance_from_location_km=a.distance_from_location_km,
                        estimated_price_eur_per_night=a.estimated_price_eur_per_night,
                        bike_friendly=a.bike_friendly,
                        notes=a.notes,
                    )
                )
                inserted += 1
        await session.commit()
    return inserted


async def seed_weather() -> int:
    inserted = 0
    async with get_async_session() as session:
        await session.execute(delete(WeatherNorm))
        for location_lower, months in WEATHER_CLIMATE.items():
            for month, stats in months.items():
                avg, high, low, rain_days, rain_mm, note = stats
                session.add(
                    WeatherNorm(
                        location_lower=location_lower,
                        month=month,
                        avg_temp_celsius=avg,
                        avg_high_celsius=high,
                        avg_low_celsius=low,
                        rain_days_per_month=rain_days,
                        avg_rain_mm=rain_mm,
                        notes=note,
                    )
                )
                inserted += 1
        await session.commit()
    return inserted


async def seed_elevation() -> int:
    """Insert each segment in BOTH directions (mirroring gain/loss for the
    reverse direction). The original code did this auto-mirroring at
    runtime — we precompute it now."""
    inserted = 0
    async with get_async_session() as session:
        await session.execute(delete(ElevationSegment))
        for row in ELEV_SEGMENTS:
            start, end, dist, gain, loss, grade, diff, note = row
            # Forward
            session.add(
                ElevationSegment(
                    start_lower=_norm(start),
                    end_lower=_norm(end),
                    distance_km=dist,
                    elevation_gain_m=gain,
                    elevation_loss_m=loss,
                    max_grade_percent=grade,
                    difficulty=diff,
                    notes=note,
                )
            )
            inserted += 1
            # Reverse (gain/loss swapped) — only if it's not a zero-distance
            # crossing where direction is meaningless.
            if dist > 0:
                session.add(
                    ElevationSegment(
                        start_lower=_norm(end),
                        end_lower=_norm(start),
                        distance_km=dist,
                        elevation_gain_m=loss,
                        elevation_loss_m=gain,
                        max_grade_percent=grade,
                        difficulty=diff,
                        notes=note,
                    )
                )
                inserted += 1
        await session.commit()
    return inserted


async def main() -> None:
    log.info("seed.start")
    await init_db()

    routes = await seed_routes()
    accom = await seed_accommodations()
    weather = await seed_weather()
    elev = await seed_elevation()

    log.info(
        "seed.done",
        routes=routes,
        accommodations=accom,
        weather_norms=weather,
        elevation_segments=elev,
    )

    print(f"✓ Seeded {routes} routes, {accom} accommodations, {weather} weather norms, {elev} elevation segments")


if __name__ == "__main__":
    asyncio.run(main())
