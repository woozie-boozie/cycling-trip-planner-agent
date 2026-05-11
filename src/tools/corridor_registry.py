"""Corridor catalog loaded from ``data/corridors/*.yaml``.

Each YAML file defines one corridor (start ↔ end city pair) with one or
more variants. Loaded once at import time, validated via Pydantic, and
exposed as the same ``CorridorVariant`` dataclass shape that
``route_real.py`` previously held inline.

Why this exists (Phase 1 of the catalog refactor):
    Adding the 21st corridor used to mean editing two Python files
    (``route_real.py`` and ``web/lib/corridors.ts``) plus a JSON cache
    file. Per-corridor YAML files in ``data/corridors/`` collapse that
    to a single-file operation — the registry walks the directory at
    import time and the readers (route_real, frontend codegen, POI
    fetcher) all share the same source of truth.

The dataclasses ``Anchor`` and ``CorridorVariant`` previously lived in
``route_real.py``; they're defined here now so a single import target
covers the whole catalog subsystem. ``route_real.py`` re-imports them
from this module to preserve every existing call site.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# Public dataclasses — canonical Anchor + CorridorVariant types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Anchor:
    """A single waypoint along a corridor variant.

    Anchors with ``is_overnight=False`` are "through-towns" — they steer
    BRouter along the signposted route so the polyline doesn't cut corners,
    but they don't surface to the agent as a planning waypoint. Anchors
    with ``is_ferry_arrival=True`` mark the destination side of a ferry
    crossing.
    """

    name: str
    country: str
    lat: float
    lon: float
    is_ferry_arrival: bool = False
    is_overnight: bool = True


@dataclass(frozen=True)
class CorridorVariant:
    """A single variant within a corridor — name + anchors + presentation.

    Multiple variants per corridor (e.g. Avenue Verte has 3) let the agent
    surface a side-by-side comparison when the user hasn't yet committed
    to a specific signposted alternative.
    """

    name: str
    title: str
    description: str
    anchors: list[Anchor]
    distinguishing_features: list[str]
    trade_offs: list[str]
    best_for: str
    is_default: bool = False
    # One-word at-a-glance tag (e.g. "Direct", "Scenic", "Quiet"). Picked
    # from axes that actually differ between variants in this corridor —
    # None when variants are too homogeneous to label honestly.
    headline_tag: str | None = None


# ---------------------------------------------------------------------------
# Pydantic shapes for YAML — validate every field at load time
# ---------------------------------------------------------------------------


class _AnchorYaml(BaseModel):
    """YAML shape for a single corridor anchor. Bridges to the public
    ``Anchor`` dataclass via :meth:`to_anchor`."""

    name: str
    country: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    is_ferry_arrival: bool = False
    is_overnight: bool = True

    def to_anchor(self) -> Anchor:
        return Anchor(
            name=self.name,
            country=self.country,
            lat=self.lat,
            lon=self.lon,
            is_ferry_arrival=self.is_ferry_arrival,
            is_overnight=self.is_overnight,
        )


class _VariantYaml(BaseModel):
    """YAML shape for one corridor variant."""

    name: str
    title: str
    description: str
    headline_tag: str | None = None
    is_default: bool = False
    distinguishing_features: list[str]
    trade_offs: list[str]
    best_for: str
    anchors: list[_AnchorYaml] = Field(min_length=2)

    def to_variant(self) -> CorridorVariant:
        return CorridorVariant(
            name=self.name,
            title=self.title,
            description=self.description,
            anchors=[a.to_anchor() for a in self.anchors],
            distinguishing_features=self.distinguishing_features,
            trade_offs=self.trade_offs,
            best_for=self.best_for,
            is_default=self.is_default,
            headline_tag=self.headline_tag,
        )


class CorridorDef(BaseModel):
    """One corridor entry, parsed from a single YAML file.

    Public — used by the POI fetcher + frontend codegen to enumerate the
    catalog (e.g. to render homepage cards, populate Overpass queries).
    """

    id: str = Field(
        min_length=1,
        description="Stable slug (e.g. 'ldn-par'). Used as the corridor id "
        "in the frontend matcher and as the filename stem in "
        "data/corridors/<id>.yaml.",
    )
    label: str = Field(description="Display name like 'London → Paris'")
    start: str = Field(description="Start city — must match first variant's first anchor name")
    end: str = Field(description="End city — must match first variant's last anchor name")
    aliases: list[str] = Field(
        default_factory=list,
        description="Alternative phrasings the frontend matchCorridor scans for "
        "(e.g. 'avenue verte', 'eurovelo 6'). Lowercase tokens.",
    )
    description: str = Field(
        description="One-paragraph corridor blurb shown above variant comparison",
    )
    variants: list[_VariantYaml] = Field(min_length=1)

    @model_validator(mode="after")
    def _exactly_one_default(self) -> CorridorDef:
        defaults = [v for v in self.variants if v.is_default]
        if len(defaults) != 1:
            raise ValueError(
                f"corridor {self.id!r} must have exactly ONE variant with "
                f"is_default=true (found {len(defaults)}). Pick the "
                f"signposted-or-most-popular variant as the default."
            )
        return self

    @model_validator(mode="after")
    def _endpoints_match_first_variant(self) -> CorridorDef:
        v0 = self.variants[0]
        first_anchor = v0.anchors[0]
        last_anchor = v0.anchors[-1]
        if first_anchor.name.lower() != self.start.lower():
            raise ValueError(
                f"corridor {self.id!r}: start='{self.start}' must match "
                f"first variant's first anchor (got '{first_anchor.name}')"
            )
        if last_anchor.name.lower() != self.end.lower():
            raise ValueError(
                f"corridor {self.id!r}: end='{self.end}' must match "
                f"first variant's last anchor (got '{last_anchor.name}')"
            )
        return self

    def to_variants(self) -> list[CorridorVariant]:
        """Convert to the runtime CorridorVariant dataclass list."""
        return [v.to_variant() for v in self.variants]


# ---------------------------------------------------------------------------
# Registry — single source of truth, loaded once at import time
# ---------------------------------------------------------------------------


_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "corridors"


def _normalize(s: str) -> str:
    return s.strip().lower()


def _reverse_variant(v: CorridorVariant) -> CorridorVariant:
    """Build a reverse-direction CorridorVariant by reversing anchor order.

    Mirrors the inline list-comprehension previously in
    ``route_real._CORRIDORS`` (paris→london, copenhagen→amsterdam,
    brighton→london). The reversed first anchor's ``is_ferry_arrival``
    flag is preserved per-anchor — the ferry crossing still happens at
    the same geographic point regardless of travel direction.
    """
    return CorridorVariant(
        name=v.name,
        title=v.title,
        description=v.description,
        anchors=list(reversed(v.anchors)),
        distinguishing_features=v.distinguishing_features,
        trade_offs=v.trade_offs,
        best_for=v.best_for,
        is_default=v.is_default,
        headline_tag=v.headline_tag,
    )


@lru_cache(maxsize=1)
def load_all_corridors() -> dict[tuple[str, str], list[CorridorVariant]]:
    """Walk ``data/corridors/*.yaml`` and return a bidirectional catalog.

    Keys are ``(normalised_start, normalised_end)`` tuples. For every
    corridor file we register BOTH directions — the reverse is computed
    by reversing each variant's anchor list. Process-cached so the
    filesystem walk + YAML parse + Pydantic validation cost is paid
    exactly once per process.

    Returns an empty dict if ``data/corridors/`` is missing or empty —
    callers fall through to generic mode for every request, same as
    before the catalog existed.
    """
    out: dict[tuple[str, str], list[CorridorVariant]] = {}

    if not _DATA_DIR.exists():
        return out

    for path in sorted(_DATA_DIR.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text())
        if raw is None:
            continue  # tolerate empty file
        try:
            corridor = CorridorDef.model_validate(raw)
        except Exception as e:
            raise ValueError(
                f"failed to parse corridor file {path.name}: {e}"
            ) from e

        variants = corridor.to_variants()
        start_key = _normalize(corridor.start)
        end_key = _normalize(corridor.end)
        out[(start_key, end_key)] = variants
        out[(end_key, start_key)] = [_reverse_variant(v) for v in variants]

    return out


def get_corridor_variants(start: str, end: str) -> list[CorridorVariant] | None:
    """Look up variants for one direction. Returns ``None`` for out-of-
    catalog corridors — caller falls through to generic mode."""
    return load_all_corridors().get((_normalize(start), _normalize(end)))


def all_corridor_defs() -> list[CorridorDef]:
    """Return every ``CorridorDef`` as the YAML parsed it.

    Used by:
      - The POI fetcher (``scripts/fetch_corridor_pois.py``) to enumerate
        corridor ids + endpoints for Overpass queries.
      - The frontend codegen (``scripts/build_corridors_ts.py``) to emit
        ``web/lib/corridors.ts`` from the same YAML registry.
      - Any "list all available corridors" API endpoint we add later.

    NOT cached — each call re-reads the files. Cheap enough at our scale
    (≤30 files); skipping the cache means the codegen sees freshly-edited
    YAML without restarting the python process.
    """
    if not _DATA_DIR.exists():
        return []
    return [
        CorridorDef.model_validate(yaml.safe_load(p.read_text()))
        for p in sorted(_DATA_DIR.glob("*.yaml"))
        if yaml.safe_load(p.read_text()) is not None
    ]


def _clear_cache_for_tests() -> None:
    """Drop the lru_cache so tests can pick up freshly-written YAML files."""
    load_all_corridors.cache_clear()
