"""Quick smoke test for the Google Places real-data path.

Run via: .venv/bin/python -m scripts.smoke_places

Loads .env, sets USE_REAL_PLACES=true for the process, and runs one
accommodation query + one POI query against the live API. Prints shape
and a redacted summary — never the API key.

Safe to delete after the integration is verified.
"""

from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv


async def main() -> int:
    load_dotenv()
    if not os.getenv("GOOGLE_PLACES_API_KEY"):
        print("FAIL · GOOGLE_PLACES_API_KEY not set in .env")
        return 1
    os.environ["USE_REAL_PLACES"] = "true"

    # Import AFTER env is set so use_real_places() resolves correctly.
    from src.tools.places_real import (
        fetch_real_accommodations,
        fetch_real_pois,
        use_real_places,
    )

    print(f"use_real_places() = {use_real_places()}")
    if not use_real_places():
        print("FAIL · flag check returned False")
        return 1

    # Test 1 · Accommodation in Beauvais (along Avenue Verte)
    print("\n--- Accommodation · Beauvais ---")
    accoms = await fetch_real_accommodations("Beauvais", types=None, max_results=5)
    if accoms is None:
        print("FAIL · accommodation fetch returned None (network or auth issue)")
        return 1
    print(f"got {len(accoms)} results")
    for a in accoms[:3]:
        photo_flag = "📸" if a.photo_url else "  "
        rating_str = f"{a.rating}★ ({a.review_count})" if a.rating else "no rating"
        print(
            f"  {photo_flag} {a.type:9} · {a.name[:40]:40} · "
            f"{a.distance_from_location_km:>4} km · "
            f"{rating_str:>16} · €{a.estimated_price_eur_per_night:.0f}"
        )

    # Test 2 · POI · bike shops in London
    print("\n--- POI · London bike shops ---")
    pois = await fetch_real_pois("London", categories=["bike_shop"], max_results=5)
    if pois is None:
        print("FAIL · POI fetch returned None")
        return 1
    print(f"got {len(pois)} results")
    for p in pois[:3]:
        photo_flag = "📸" if p.photo_url else "  "
        rating_str = f"{p.rating}★ ({p.review_count})" if p.rating else "no rating"
        print(f"  {photo_flag} {p.name[:50]:50} · {rating_str}")

    # Test 3 · POI · seed-only category should return None
    print("\n--- POI · water fountains (seed-only) ---")
    seed_only = await fetch_real_pois(
        "London", categories=["water_fountain"], max_results=3
    )
    if seed_only is not None:
        print(f"FAIL · expected None for seed-only category, got {len(seed_only)}")
        return 1
    print("OK · None returned (seed fallback path will engage)")

    print("\n✓ smoke test PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
