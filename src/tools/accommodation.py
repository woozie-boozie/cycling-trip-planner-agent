"""find_accommodation — places to stay near a location.

Catalog lives in the `accommodations` table in Postgres (seeded from
`_CATALOG` below via `src/db/seed.py`). The agent uses this to honor
preferences like "camping but a hostel every 4th night" — by filtering
`types` per segment as it builds the day-by-day plan.
"""

from __future__ import annotations

from sqlmodel import select

from src.db import get_async_session
from src.db.models import Accommodation as AccommodationRow
from src.tools.base import register_tool
from src.tools.schemas import (
    Accommodation,
    AccommodationType,
    FindAccommodationInput,
    FindAccommodationOutput,
)

# Rough per-city accommodation catalog. Designed to *look* like real listings:
# bike-friendly campings on the outskirts, central hostels, mid-range hotels.
_CATALOG: dict[str, list[Accommodation]] = {
    "amsterdam": [
        Accommodation(
            name="Camping Zeeburg",
            type="camping",
            location="Amsterdam",
            distance_from_location_km=4.5,
            estimated_price_eur_per_night=25,
            bike_friendly=True,
            notes="Direct cycle path into the city center.",
        ),
        Accommodation(
            name="ClinkNOORD Hostel",
            type="hostel",
            location="Amsterdam",
            distance_from_location_km=2.0,
            estimated_price_eur_per_night=45,
            bike_friendly=True,
        ),
        Accommodation(
            name="Hotel V Nesplein",
            type="hotel",
            location="Amsterdam",
            distance_from_location_km=0.5,
            estimated_price_eur_per_night=180,
            bike_friendly=True,
        ),
    ],
    "hoorn": [
        Accommodation(
            name="Camping de Kogge",
            type="camping",
            location="Hoorn",
            distance_from_location_km=3.0,
            estimated_price_eur_per_night=22,
            bike_friendly=True,
        ),
        Accommodation(
            name="Stadslogement Oud Hoorn",
            type="guesthouse",
            location="Hoorn",
            distance_from_location_km=0.4,
            estimated_price_eur_per_night=85,
            bike_friendly=True,
        ),
    ],
    "groningen": [
        Accommodation(
            name="Camping Stadspark",
            type="camping",
            location="Groningen",
            distance_from_location_km=2.0,
            estimated_price_eur_per_night=20,
            bike_friendly=True,
        ),
        Accommodation(
            name="Simplon Jongerenhotel",
            type="hostel",
            location="Groningen",
            distance_from_location_km=1.5,
            estimated_price_eur_per_night=40,
            bike_friendly=True,
        ),
    ],
    "bremen": [
        Accommodation(
            name="Stadtcamping Bremen",
            type="camping",
            location="Bremen",
            distance_from_location_km=4.0,
            estimated_price_eur_per_night=24,
            bike_friendly=True,
        ),
        Accommodation(
            name="Bremen Hostel",
            type="hostel",
            location="Bremen",
            distance_from_location_km=1.0,
            estimated_price_eur_per_night=38,
            bike_friendly=True,
        ),
        Accommodation(
            name="Hotel Bremer Haus",
            type="hotel",
            location="Bremen",
            distance_from_location_km=0.3,
            estimated_price_eur_per_night=110,
            bike_friendly=True,
        ),
    ],
    "hamburg": [
        Accommodation(
            name="Camping Buchholz",
            type="camping",
            location="Hamburg",
            distance_from_location_km=8.0,
            estimated_price_eur_per_night=28,
            bike_friendly=True,
        ),
        Accommodation(
            name="Generator Hamburg",
            type="hostel",
            location="Hamburg",
            distance_from_location_km=2.0,
            estimated_price_eur_per_night=42,
            bike_friendly=True,
            notes="Locked bike room and on-site repair stand.",
        ),
        Accommodation(
            name="25hours Hotel HafenCity",
            type="hotel",
            location="Hamburg",
            distance_from_location_km=1.0,
            estimated_price_eur_per_night=160,
            bike_friendly=True,
        ),
    ],
    "lübeck": [
        Accommodation(
            name="Campingplatz Schönböcken",
            type="camping",
            location="Lübeck",
            distance_from_location_km=4.5,
            estimated_price_eur_per_night=22,
            bike_friendly=True,
        ),
        Accommodation(
            name="Rucksackhotel Backpackers",
            type="hostel",
            location="Lübeck",
            distance_from_location_km=0.8,
            estimated_price_eur_per_night=35,
            bike_friendly=True,
        ),
    ],
    "puttgarden": [
        Accommodation(
            name="Camping Wulfener Hals",
            type="camping",
            location="Puttgarden",
            distance_from_location_km=12.0,
            estimated_price_eur_per_night=26,
            bike_friendly=True,
            notes="Short ride to the ferry terminal.",
        ),
    ],
    "rødby": [
        Accommodation(
            name="Lalandia Camping",
            type="camping",
            location="Rødby",
            distance_from_location_km=5.0,
            estimated_price_eur_per_night=24,
            bike_friendly=True,
        ),
        Accommodation(
            name="Hotel Maribo Søpark",
            type="hotel",
            location="Rødby",
            distance_from_location_km=15.0,
            estimated_price_eur_per_night=120,
            bike_friendly=True,
        ),
    ],
    "vordingborg": [
        Accommodation(
            name="Vordingborg Camping",
            type="camping",
            location="Vordingborg",
            distance_from_location_km=2.0,
            estimated_price_eur_per_night=22,
            bike_friendly=True,
        ),
        Accommodation(
            name="Danhostel Vordingborg",
            type="hostel",
            location="Vordingborg",
            distance_from_location_km=1.0,
            estimated_price_eur_per_night=40,
            bike_friendly=True,
        ),
    ],
    "copenhagen": [
        Accommodation(
            name="Camping Charlottenlund Fort",
            type="camping",
            location="Copenhagen",
            distance_from_location_km=7.0,
            estimated_price_eur_per_night=30,
            bike_friendly=True,
            notes="On the seafront, direct cycle path to the city.",
        ),
        Accommodation(
            name="Generator Copenhagen",
            type="hostel",
            location="Copenhagen",
            distance_from_location_km=1.5,
            estimated_price_eur_per_night=50,
            bike_friendly=True,
        ),
        Accommodation(
            name="Hotel Skt. Petri",
            type="hotel",
            location="Copenhagen",
            distance_from_location_km=0.5,
            estimated_price_eur_per_night=200,
            bike_friendly=True,
        ),
    ],
    # ---- Avenue Verte corridor (London → Paris) ---------------------------
    "london": [
        Accommodation(
            name="Lee Valley Camping & Caravan Park",
            type="camping",
            location="London",
            distance_from_location_km=14.0,
            estimated_price_eur_per_night=29,
            bike_friendly=True,
            notes="Bike-friendly site with secure storage and direct Lee Valley cycle path into central London.",
        ),
        Accommodation(
            name="YHA London Central",
            type="hostel",
            location="London",
            distance_from_location_km=0.5,
            estimated_price_eur_per_night=48,
            bike_friendly=True,
        ),
        Accommodation(
            name="Travelodge London Central Waterloo",
            type="hotel",
            location="London",
            distance_from_location_km=0.8,
            estimated_price_eur_per_night=140,
            bike_friendly=True,
        ),
    ],
    "east grinstead": [
        Accommodation(
            name="Tanglewood Caravan Park",
            type="camping",
            location="East Grinstead",
            distance_from_location_km=3.5,
            estimated_price_eur_per_night=22,
            bike_friendly=True,
        ),
        Accommodation(
            name="The Old Mill Guesthouse",
            type="guesthouse",
            location="East Grinstead",
            distance_from_location_km=1.0,
            estimated_price_eur_per_night=85,
            bike_friendly=True,
        ),
    ],
    "lewes": [
        Accommodation(
            name="South Downs YHA",
            type="hostel",
            location="Lewes",
            distance_from_location_km=2.0,
            estimated_price_eur_per_night=42,
            bike_friendly=True,
            notes="Right on the South Downs Way — popular with cyclists.",
        ),
        Accommodation(
            name="The Shelleys Hotel",
            type="hotel",
            location="Lewes",
            distance_from_location_km=0.5,
            estimated_price_eur_per_night=130,
            bike_friendly=True,
        ),
    ],
    "newhaven": [
        Accommodation(
            name="Buckle Holiday Park",
            type="camping",
            location="Newhaven",
            distance_from_location_km=2.5,
            estimated_price_eur_per_night=20,
            bike_friendly=True,
            notes="Walking distance to the DFDS ferry terminal.",
        ),
        Accommodation(
            name="Premier Inn Newhaven",
            type="hotel",
            location="Newhaven",
            distance_from_location_km=1.5,
            estimated_price_eur_per_night=88,
            bike_friendly=True,
        ),
    ],
    "dieppe": [
        Accommodation(
            name="Camping Vitamin",
            type="camping",
            location="Dieppe",
            distance_from_location_km=2.0,
            estimated_price_eur_per_night=22,
            bike_friendly=True,
            notes="Near the seafront, ~10 min ride from the ferry port.",
        ),
        Accommodation(
            name="Auberge de Jeunesse Dieppe",
            type="hostel",
            location="Dieppe",
            distance_from_location_km=0.8,
            estimated_price_eur_per_night=32,
            bike_friendly=True,
        ),
        Accommodation(
            name="Hôtel de l'Univers",
            type="hotel",
            location="Dieppe",
            distance_from_location_km=0.4,
            estimated_price_eur_per_night=98,
            bike_friendly=True,
        ),
    ],
    "forges-les-eaux": [
        Accommodation(
            name="Camping de la Minière",
            type="camping",
            location="Forges-les-Eaux",
            distance_from_location_km=2.0,
            estimated_price_eur_per_night=18,
            bike_friendly=True,
        ),
        Accommodation(
            name="Hôtel Continental Forges",
            type="hotel",
            location="Forges-les-Eaux",
            distance_from_location_km=0.5,
            estimated_price_eur_per_night=72,
            bike_friendly=True,
        ),
    ],
    "beauvais": [
        Accommodation(
            name="Camping Municipal de Beauvais",
            type="camping",
            location="Beauvais",
            distance_from_location_km=3.5,
            estimated_price_eur_per_night=18,
            bike_friendly=True,
        ),
        Accommodation(
            name="Auberge de Jeunesse Beauvais",
            type="hostel",
            location="Beauvais",
            distance_from_location_km=1.5,
            estimated_price_eur_per_night=29,
            bike_friendly=True,
        ),
        Accommodation(
            name="Mercure Beauvais Centre",
            type="hotel",
            location="Beauvais",
            distance_from_location_km=0.4,
            estimated_price_eur_per_night=110,
            bike_friendly=True,
        ),
    ],
    "cergy-pontoise": [
        Accommodation(
            name="Auberge de Jeunesse Cergy",
            type="hostel",
            location="Cergy-Pontoise",
            distance_from_location_km=1.0,
            estimated_price_eur_per_night=34,
            bike_friendly=True,
        ),
        Accommodation(
            name="Best Western Le Cergy",
            type="hotel",
            location="Cergy-Pontoise",
            distance_from_location_km=0.5,
            estimated_price_eur_per_night=98,
            bike_friendly=True,
        ),
    ],
    "paris": [
        Accommodation(
            name="Camping Bois de Boulogne",
            type="camping",
            location="Paris",
            distance_from_location_km=8.0,
            estimated_price_eur_per_night=38,
            bike_friendly=True,
            notes="Pricey but the only campsite inside greater Paris — direct cycle path along the Seine.",
        ),
        Accommodation(
            name="Generator Paris",
            type="hostel",
            location="Paris",
            distance_from_location_km=2.0,
            estimated_price_eur_per_night=52,
            bike_friendly=True,
        ),
        Accommodation(
            name="Hôtel Eiffel Trocadéro",
            type="hotel",
            location="Paris",
            distance_from_location_km=1.0,
            estimated_price_eur_per_night=185,
            bike_friendly=True,
        ),
    ],
    "crystal palace": [
        Accommodation(
            name="The Crystal Palace Hotel",
            type="hotel",
            location="Crystal Palace",
            distance_from_location_km=0.5,
            estimated_price_eur_per_night=95,
            bike_friendly=True,
            notes="Convenient overnight if breaking the London → Brighton ride into two.",
        ),
    ],
    "brighton": [
        Accommodation(
            name="Sheepcote Valley Caravan Park",
            type="camping",
            location="Brighton",
            distance_from_location_km=4.0,
            estimated_price_eur_per_night=28,
            bike_friendly=True,
        ),
        Accommodation(
            name="YHA Brighton",
            type="hostel",
            location="Brighton",
            distance_from_location_km=1.5,
            estimated_price_eur_per_night=42,
            bike_friendly=True,
        ),
        Accommodation(
            name="The Grand Brighton",
            type="hotel",
            location="Brighton",
            distance_from_location_km=0.3,
            estimated_price_eur_per_night=180,
            bike_friendly=True,
        ),
    ],
}


def _normalize(name: str) -> str:
    return name.strip().lower()


def _generic_results(location: str) -> list[Accommodation]:
    """Sensible stub when a location isn't in the catalog. We keep the agent
    moving rather than blowing up."""
    return [
        Accommodation(
            name=f"Generic Campground near {location}",
            type="camping",
            location=location,
            distance_from_location_km=4.0,
            estimated_price_eur_per_night=25,
            bike_friendly=True,
            notes="Mock data — exact listings unavailable for this location.",
        ),
        Accommodation(
            name=f"Generic Hostel in {location}",
            type="hostel",
            location=location,
            distance_from_location_km=1.5,
            estimated_price_eur_per_night=40,
            bike_friendly=True,
            notes="Mock data — exact listings unavailable for this location.",
        ),
    ]


def _row_to_schema(row: AccommodationRow) -> Accommodation:
    return Accommodation(
        name=row.name,
        type=row.type,  # type: ignore[arg-type]
        location=row.location,
        distance_from_location_km=row.distance_from_location_km,
        estimated_price_eur_per_night=row.estimated_price_eur_per_night,
        bike_friendly=row.bike_friendly,
        notes=row.notes,
    )


@register_tool(
    name="find_accommodation",
    description=(
        "Find places to stay near a given location, optionally filtered by type "
        "(camping, hostel, hotel, guesthouse). Use after get_route, once per "
        "overnight stop, to honor the cyclist's accommodation preferences "
        "(e.g. 'camping but a hostel every 4th night')."
    ),
    input_model=FindAccommodationInput,
    output_model=FindAccommodationOutput,
)
async def find_accommodation(input: FindAccommodationInput) -> FindAccommodationOutput:
    location_lower = _normalize(input.location)

    async with get_async_session() as session:
        result = await session.execute(
            select(AccommodationRow).where(AccommodationRow.location_lower == location_lower)
        )
        rows = result.scalars().all()

    catalog: list[Accommodation] = (
        [_row_to_schema(r) for r in rows] if rows else _generic_results(input.location)
    )

    filtered: list[Accommodation]
    if input.types:
        wanted: set[AccommodationType] = set(input.types)
        filtered = [a for a in catalog if a.type in wanted]
        # If the strict filter eliminates everything, fall back to the full
        # catalog with a note in the agent prompt rather than returning empty.
        if not filtered:
            filtered = catalog
    else:
        filtered = catalog

    return FindAccommodationOutput(
        location=input.location,
        results=filtered[: input.max_results],
    )
