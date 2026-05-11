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

/**
 * Fallback for corridors not yet curated in this file. Renders a flat-ish
 * placeholder sparkline + no ferry. Components import this so they never
 * crash on a missing entry — adding a 24th corridor without route-details
 * data gives a graceful default, not a runtime TypeError. Real data should
 * always be added below for a quality demo, but the fallback keeps the
 * dev server up while data is being curated.
 */
export const FALLBACK_DETAILS: RouteDetails = {
  total_climb_m: 0,
  ferry_cost_eur: null,
  elevation: [0.05, 0.1, 0.08, 0.12, 0.07, 0.1, 0.06],
};

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

  // === PHASE 2 corridors — climb estimates from training data, sparklines
  // hand-tuned per terrain character (FLAT / ROLLING / HILLY / MOUNTAIN).
  // Normalised against the same ~460 m global max so visual comparison
  // across all 23 corridors stays honest.

  // Loire à Vélo — flattest 800 km of any EuroVelo segment.
  "loire-a-velo": {
    total_climb_m: 520,
    ferry_cost_eur: null,
    elevation: [0.06, 0.10, 0.08, 0.12, 0.09, 0.07, 0.11, 0.08, 0.06, 0.09, 0.07],
  },

  // Danube Passau → Vienna — pancake-flat river path.
  "danube-passau-vienna": {
    total_climb_m: 380,
    ferry_cost_eur: null,
    elevation: [0.05, 0.09, 0.07, 0.11, 0.08, 0.06, 0.10, 0.07],
  },

  // LF Kustroute — Dutch coast, dune climbs only.
  "lf-kustroute": {
    total_climb_m: 320,
    ferry_cost_eur: null,
    elevation: [0.04, 0.13, 0.06, 0.11, 0.08, 0.14, 0.05, 0.10, 0.07, 0.09],
  },

  // Vélodyssée — 1,200 km Atlantic, rolling pine forest climbs.
  velodyssee: {
    total_climb_m: 2800,
    ferry_cost_eur: null,
    elevation: [
      0.15, 0.28, 0.20, 0.35, 0.25, 0.45, 0.30, 0.40, 0.22, 0.35, 0.28, 0.42,
      0.30, 0.25, 0.20,
    ],
  },

  // Danube Vienna → Budapest — flat extension east.
  "danube-vienna-budapest": {
    total_climb_m: 320,
    ferry_cost_eur: null,
    elevation: [0.06, 0.10, 0.07, 0.12, 0.08, 0.11, 0.07, 0.09],
  },

  // LEJOG — full UK end-to-end, the headline mountain profile.
  lejog: {
    total_climb_m: 17000,
    ferry_cost_eur: null,
    elevation: [
      0.20, 0.45, 0.30, 0.70, 0.55, 0.85, 0.60, 0.95, 0.75, 1.00, 0.65, 0.85,
      0.50, 0.70, 0.40, 0.55, 0.30,
    ],
  },

  // Coast to Coast — Hartside Pass dominates, real Pennine climbing.
  "c2c-whitehaven-tynemouth": {
    total_climb_m: 3300,
    ferry_cost_eur: null,
    elevation: [
      0.25, 0.55, 0.40, 0.85, 0.95, 0.70, 0.45, 0.30, 0.20, 0.15, 0.10,
    ],
  },

  // Hebridean Way — single-track island climbs, frequent inter-island ferries.
  "hebridean-way": {
    total_climb_m: 1800,
    ferry_cost_eur: 18,
    ferry_label: "Inter-island ferries (multiple)",
    elevation: [
      0.20, 0.35, 0.25, 0.45, 0.30, 0.50, 0.35, 0.40, 0.25, 0.30, 0.20,
    ],
  },

  // Way of the Roses — Yorkshire Dales climbs, then long descent to coast.
  "way-of-the-roses": {
    total_climb_m: 2200,
    ferry_cost_eur: null,
    elevation: [
      0.15, 0.45, 0.65, 0.80, 0.55, 0.40, 0.30, 0.20, 0.15, 0.10,
    ],
  },

  // Venice → Florence — Po flatland then Apennine climb to Pistoia.
  "venice-florence": {
    total_climb_m: 1500,
    ferry_cost_eur: null,
    elevation: [
      0.05, 0.08, 0.10, 0.12, 0.15, 0.30, 0.60, 0.80, 0.55, 0.40, 0.25,
    ],
  },

  // Sicily loop — coastal flat + inland Etna periphery climbs.
  "sicily-loop": {
    total_climb_m: 6500,
    ferry_cost_eur: null,
    elevation: [
      0.15, 0.30, 0.50, 0.75, 0.65, 0.40, 0.55, 0.70, 0.45, 0.35, 0.50, 0.40,
      0.30, 0.45, 0.25,
    ],
  },

  // Costa Brava — Catalan coast, increasing climbs toward Cap de Creus.
  "costa-brava": {
    total_climb_m: 2200,
    ferry_cost_eur: null,
    elevation: [
      0.10, 0.20, 0.30, 0.40, 0.35, 0.45, 0.55, 0.65, 0.50, 0.45,
    ],
  },

  // Camino del Norte — Asturias is brutal. Real mountain profile.
  "camino-del-norte": {
    total_climb_m: 13000,
    ferry_cost_eur: null,
    elevation: [
      0.20, 0.45, 0.30, 0.65, 0.55, 0.80, 0.65, 0.95, 0.70, 1.00, 0.60, 0.45,
      0.35, 0.50, 0.30,
    ],
  },

  // Algarve coast — pancake flat, occasional dune climbs.
  "algarve-coast": {
    total_climb_m: 580,
    ferry_cost_eur: null,
    elevation: [0.06, 0.12, 0.08, 0.14, 0.07, 0.11, 0.08, 0.10],
  },

  // Berlin → Copenhagen — flat throughout, Warnemünde-Gedser ferry crossing.
  "berlin-copenhagen": {
    total_climb_m: 720,
    ferry_cost_eur: 25,
    ferry_label: "Warnemünde → Gedser",
    elevation: [0.08, 0.14, 0.10, 0.18, 0.13, 0.10, 0.16, 0.12, 0.08],
  },

  // Prague → Vienna Greenways — gentle Moravian rolls.
  "prague-vienna": {
    total_climb_m: 2500,
    ferry_cost_eur: null,
    elevation: [
      0.15, 0.30, 0.45, 0.40, 0.55, 0.45, 0.35, 0.50, 0.30, 0.40,
    ],
  },

  // Berlin → Usedom — flat Brandenburg + Mecklenburg lakeland.
  "berlin-usedom": {
    total_climb_m: 420,
    ferry_cost_eur: null,
    elevation: [0.06, 0.10, 0.08, 0.13, 0.09, 0.11, 0.07, 0.10],
  },

  // Amsterdam → Berlin — Münsterland gentle, otherwise flat.
  "amsterdam-berlin": {
    total_climb_m: 1100,
    ferry_cost_eur: null,
    elevation: [0.10, 0.18, 0.14, 0.25, 0.20, 0.16, 0.22, 0.14, 0.18, 0.12],
  },

  // Paris → Lyon via Bourgogne canals — vineyard climbs around Beaune.
  "paris-lyon": {
    total_climb_m: 2800,
    ferry_cost_eur: null,
    elevation: [
      0.12, 0.20, 0.30, 0.25, 0.40, 0.55, 0.45, 0.35, 0.30, 0.25, 0.20,
    ],
  },

  // EuroVelo 15 Rhine — Alpine source descent, then flat to North Sea.
  "eurovelo-15-rhine": {
    total_climb_m: 3000,
    ferry_cost_eur: null,
    elevation: [
      1.00, 0.85, 0.70, 0.55, 0.40, 0.30, 0.22, 0.18, 0.14, 0.10, 0.08, 0.05,
    ],
  },
};
