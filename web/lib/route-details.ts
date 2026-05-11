/**
 * Per-corridor stat extras + elevation profile for the gallery cards.
 *
 * Source of truth: the seeded segment data in `src/tools/elevation.py`
 * (`_SEGMENTS`) and the ferry-cost lookup in `src/tools/budget.py`
 * (`_FERRY_PRICE_EUR`). Numbers here mirror those exactly so the gallery
 * shows the same totals the agent's tools would report on a real plan.
 *
 * Curve shape is reconstructed from the segment-level gain/loss data:
 * for each segment we walk start_elev → start+gain (peak at midpoint) →
 * end_elev = start + gain - loss. Real BRouter elevation samples (the
 * within-segment terrain) only land when the user actually plans a
 * route via `get_elevation_profile`. The card surfaces these as
 * "indicative" so the user knows.
 *
 * Normalised against a shared global max (~460 m at Ditchling Beacon)
 * so a flat route LOOKS flat next to a hilly one.
 */

import type { CorridorId } from "@/lib/corridors";

export interface RouteDetails {
  /** Total ascent over the corridor, m. From backend `_SEGMENTS`. */
  total_climb_m: number;
  /** Per-person bike+rider single fare, EUR. Null = no ferry. From `_FERRY_PRICE_EUR`. */
  ferry_cost_eur: number | null;
  /** Human-readable ferry route name, e.g. "Newhaven → Dieppe". */
  ferry_label?: string;
  /** Normalised elevation samples 0..1 — drawn as a sparkline. */
  elevation: number[];
}

export const ROUTE_DETAILS: Record<CorridorId, RouteDetails> = {
  // London → Paris (Avenue Verte): 1,320 m total ascent.
  // Profile derived from 8 segments — South Downs ridge climb (~450 m),
  // Newhaven sea-level drop, ferry, Pays de Bray rolling French hills.
  "ldn-par": {
    total_climb_m: 1320,
    ferry_cost_eur: 65,
    ferry_label: "Newhaven → Dieppe",
    elevation: [
      0.065, 0.261, 0.674, 0.457, 0.283, 0.630, 0.978, 0.543, 0.152, 0.239,
      0.065, 0.065, 0.065, 0.326, 0.609, 0.435, 0.283, 0.457, 0.674, 0.457,
      0.239, 0.413, 0.565, 0.413, 0.283, 0.413, 0.500, 0.239,
    ],
  },

  // Amsterdam → Copenhagen (EuroVelo 7): 685 m total ascent.
  // Profile is genuinely flat — Dutch polders, North German plain, brief
  // Fehmarn ferry, flat Danish islands. Tiny ripples within ±170 m,
  // dwarfed by the global scale.
  "ams-cph": {
    total_climb_m: 685,
    ferry_cost_eur: 25,
    ferry_label: "Rødby → Puttgarden",
    elevation: [
      0.000, 0.043, 0.011, 0.130, 0.185, 0.109, 0.033, 0.283, 0.076, 0.239,
      0.098, 0.283, 0.141, 0.359, 0.152, 0.152, 0.152, 0.283, 0.163, 0.359,
      0.185,
    ],
  },

  // London → Brighton (South Downs classic): 480 m total ascent.
  // Profile is gentle for ~50 km, then a sharp spike at Ditchling Beacon
  // (the steepest sustained climb in southern England — ~16 % near the
  // top), then a fast drop to sea level at Brighton.
  "ldn-bri": {
    total_climb_m: 480,
    ferry_cost_eur: null,
    elevation: [
      0.022, 0.109, 0.130, 0.196, 0.326, 0.500, 0.696, 1.000, 0.761, 0.500,
      0.283, 0.174, 0.087,
    ],
  },
};
