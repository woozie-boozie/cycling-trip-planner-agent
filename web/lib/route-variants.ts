/**
 * Static route-variant metadata for the visual comparison card.
 *
 * Mirrors the backend's `src/tools/route_real.py:CorridorVariant` mental
 * model — title, total_distance_km, estimated_days, distinguishing features,
 * trade-offs, "best for" hint. The agent fetches the *real* numbers via
 * BRouter at runtime; this file is what the FRONTEND visual layer
 * displays in the side-by-side comparison card.
 *
 * If the agent's prose names variants we don't have here, the visual card
 * falls back to the markdown renderer — visual mode never blocks a
 * response from rendering.
 *
 * Phase 3 path: extract this from a `GET /routes/{corridor}/variants`
 * backend endpoint so the frontend stays in sync with route_real.py
 * automatically.
 */

import type { CorridorId } from "@/lib/corridors";

export interface RouteVariantSummary {
  /** Short identifier matching backend `route_real.py:CorridorVariant.name` */
  name: string;
  /** Human-readable title shown on the card header */
  title: string;
  tagline: string;
  total_distance_km: number;
  estimated_days: number;
  /** Two/three short bullets — matches backend `distinguishing_features` */
  distinguishing_features: string[];
  /** Two/three short bullets — matches backend `trade_offs` */
  trade_offs: string[];
  /** Single line — matches backend `best_for` */
  best_for: string;
  /** Used as the colour swatch on the card */
  color: string;
  /** True for the route the agent picks as default when no variant is named */
  is_default?: boolean;
  /**
   * Optional one-line "vibes" — feels like marketing copy and isn't
   * authoritative; OK to reword without backend coordination.
   */
  vibes?: string[];
}

export const ROUTE_VARIANTS: Record<CorridorId, RouteVariantSummary[]> = {
  "ldn-par": [
    {
      name: "v16a_beauvais",
      title: "V16a Beauvais",
      tagline: "fastest signposted",
      total_distance_km: 364,
      estimated_days: 4,
      distinguishing_features: [
        "LF / EuroVelo 7 signage — flat, well-signposted",
        "Beauvais Cathedral (tallest Gothic vault in the world)",
        "Pays de Bray cheese country en route",
      ],
      trade_offs: [
        "Misses the Chantilly châteaux loop",
        "More A-road sections approaching East Grinstead",
      ],
      best_for: "Fastest signposted crossing with one cathedral stop",
      vibes: ["fast roads", "one cathedral", "gentle gradients"],
      color: "#5C9AC4",
      is_default: true,
    },
    {
      name: "oise_chantilly",
      title: "Oise / Chantilly",
      tagline: "scenic châteaux loop",
      total_distance_km: 414,
      estimated_days: 5,
      distinguishing_features: [
        "Chantilly Château + Grand Stables (one of France's finest)",
        "Senlis medieval old town with Gallo-Roman walls",
        "Forest of Chantilly cycle paths",
      ],
      trade_offs: [
        "20–30 km longer — won't fit 4 days at 100km/day",
        "More expensive food / accommodation around Chantilly",
      ],
      best_for: "Heritage + photography over distance; special-occasion trips",
      vibes: ["heritage stops", "longer days", "stunning"],
      color: "#D4942A",
    },
    {
      name: "gisors",
      title: "Gisors",
      tagline: "western Epte valley",
      total_distance_km: 374,
      estimated_days: 4,
      distinguishing_features: [
        "Gisors medieval keep (Knights Templar history)",
        "Epte valley — historic Norman/French frontier",
        "Vexin Français Regional Natural Park (very few tourists)",
      ],
      trade_offs: [
        "No Beauvais Cathedral",
        "More rural — lower density of food / accommodation",
        "Rougher signposting in places",
      ],
      best_for: "Solitude + rural Normandy/Vexin over headline stops",
      vibes: ["solitude", "wildlife", "rural Normandy"],
      color: "#FF4A1C",
    },
  ],
  "ams-cph": [
    {
      name: "ev7_inland",
      title: "Inland EV7/12 hybrid",
      tagline: "default — fastest, flattest",
      total_distance_km: 836,
      estimated_days: 11,
      distinguishing_features: [
        "Mostly LF / EuroVelo 7 (Sun Route) signage — flat, well-signposted",
        "Passes through Bremen + Hamburg (great hostel density, vegetarian food)",
        "Rødby–Puttgarden ferry (~45 min, bikes free)",
      ],
      trade_offs: [
        "Misses the North Sea coast and Wadden Sea UNESCO area",
        "Fewer dramatic seaside stretches",
      ],
      best_for:
        "Riders prioritising distance/day balance and flat, well-signposted infrastructure",
      vibes: ["flat", "well-signposted", "city-rich"],
      color: "#5C9AC4",
      is_default: true,
    },
    {
      name: "ev12_coastal",
      title: "Coastal EV12 North Sea",
      tagline: "scenic but long",
      total_distance_km: 1058,
      estimated_days: 14,
      distinguishing_features: [
        "Wadden Sea UNESCO World Heritage coast — wildlife (seals, seabirds)",
        "Frisian islands gateway, Bremerhaven maritime museum",
        "True EuroVelo 12 'North Sea Route' experience",
      ],
      trade_offs: [
        "~250 km longer — adds ~3 days at the same daily distance",
        "Stronger headwind risk (North Sea westerlies)",
        "Some coastal gravel sections; pace slower than tarmac inland",
      ],
      best_for:
        "Riders who want the EuroVelo 12 'proper' experience with time to enjoy the coast",
      vibes: ["coastal", "wildlife-rich", "headwind country"],
      color: "#FF4A1C",
    },
  ],
  "ldn-bri": [
    {
      name: "ncn20_avenue_verte_uk",
      title: "South Downs classic",
      tagline: "the canonical day-ride",
      total_distance_km: 95,
      estimated_days: 1,
      distinguishing_features: [
        "Mostly NCN 20 + Avenue Verte UK signage",
        "Ditchling Beacon (steepest in southern England) before the descent",
        "Finish on the seafront with a fish & chips reward",
      ],
      trade_offs: [
        "Single-day route — only one variant signposted",
      ],
      best_for: "One iconic day, no faff",
      vibes: ["classic", "one big climb", "seafront finish"],
      color: "#FF4A1C",
      is_default: true,
    },
  ],
};

/** Returns the variants for a corridor, or null if we have only one (no comparison needed). */
export function getVariants(
  corridorId: CorridorId,
): RouteVariantSummary[] | null {
  const list = ROUTE_VARIANTS[corridorId];
  if (!list || list.length <= 1) return null;
  return list;
}
