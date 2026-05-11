"use client";

import { useMemo } from "react";
import { ArrowUpRight, Sparkles } from "lucide-react";
import type { Corridor } from "@/lib/corridors";
import { staticMapUrl } from "@/lib/mapbox";
import { LAYER_META, POIS_BY_CORRIDOR, type PoiLayer } from "@/lib/pois";
import { getVariants } from "@/lib/route-variants";
import { ROUTE_DETAILS } from "@/lib/route-details";
import { ElevationSparkline } from "@/components/elevation-sparkline";

interface RouteCardProps {
  corridor: Corridor;
  onSelect: (corridor: Corridor) => void;
  /** Featured = the recommended pick. All cards are the same size; featured
   *  differentiates only with a tinted background, "Recommended" chip, and a
   *  primary-coloured CTA. No size or content-density differences. */
  featured?: boolean;
}

const HIGHLIGHT_LAYERS: PoiLayer[] = ["heritage", "wildlife", "food"];
const HIGHLIGHT_COUNT = 3;
const MAP_HEIGHT = 200;

/**
 * Empty-state route gallery card — modernised v5.
 *
 * All cards are the same size and content-density so a 3-up row aligns
 * cleanly. Featured differentiates only by:
 *   - "Recommended" chip on the map
 *   - subtle tinted background gradient
 *   - primary-coloured CTA arrow
 *
 * Stats live in a 2-row stack so they fit any card width:
 *   row 1 = elevation sparkline (full width)
 *   row 2 = ferry · routes (2 equal cells)
 */
export function RouteCard({ corridor, onSelect, featured = false }: RouteCardProps) {
  const mapUrl = staticMapUrl(corridor, { width: 720, height: MAP_HEIGHT + 40 });
  const days = corridor.estimated_days.at_100km;
  const variants = getVariants(corridor.id);
  const details = ROUTE_DETAILS[corridor.id];

  // Pick highlight POIs for the corridor — always 3, so heights align.
  const highlights = useMemo(() => {
    const pois = POIS_BY_CORRIDOR[corridor.id] ?? [];
    const picks: { layer: PoiLayer; label: string }[] = [];
    const seen = new Set<string>();
    for (const layer of HIGHLIGHT_LAYERS) {
      const found = pois.find((p) => p.layer === layer && !seen.has(p.label));
      if (found) {
        picks.push({ layer: found.layer, label: found.label });
        seen.add(found.label);
      }
    }
    if (picks.length < HIGHLIGHT_COUNT) {
      for (const p of pois) {
        if (picks.length >= HIGHLIGHT_COUNT) break;
        if (seen.has(p.label)) continue;
        picks.push({ layer: p.layer, label: p.label });
        seen.add(p.label);
      }
    }
    return picks.slice(0, HIGHLIGHT_COUNT);
  }, [corridor.id]);

  const hasFerry = details.ferry_cost_eur != null;
  const routeCount = variants?.length ?? 1;

  return (
    <button
      type="button"
      onClick={() => onSelect(corridor)}
      className={[
        "group relative flex h-full flex-col gap-4 overflow-hidden rounded-2xl border p-4 text-left transition-all duration-300 ease-out hover:-translate-y-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40",
        featured
          ? "border-foreground/10 bg-[linear-gradient(180deg,rgba(255,61,20,0.04)_0%,rgba(255,255,255,1)_60%)] shadow-[0_1px_2px_-1px_rgb(20_19_15_/0.06),0_8px_24px_-8px_rgb(255_61_20_/0.18)] hover:shadow-[0_2px_4px_-1px_rgb(20_19_15_/0.08),0_24px_48px_-12px_rgb(255_61_20_/0.28)]"
          : "border-border/80 bg-card shadow-paper hover:border-foreground/15 hover:shadow-lift",
      ].join(" ")}
    >
      {/* Map — same height across all cards */}
      <div
        className="relative w-full overflow-hidden rounded-xl bg-muted ring-1 ring-foreground/5"
        style={{ height: `${MAP_HEIGHT}px` }}
      >
        {mapUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={mapUrl}
            alt={`${corridor.label} route map`}
            className="h-full w-full object-cover transition-transform duration-700 ease-out group-hover:scale-[1.05]"
            loading="lazy"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-xs text-muted-foreground">
            map preview unavailable
          </div>
        )}

        {/* Recommended chip — top-left */}
        {featured && (
          <span className="absolute left-3 top-3 z-10 inline-flex items-center gap-1.5 rounded-full bg-foreground/95 px-2.5 py-1 font-mono text-[9.5px] font-semibold uppercase tracking-[0.08em] text-background backdrop-blur-md">
            <Sparkles className="h-2.5 w-2.5 text-primary" aria-hidden />
            Recommended
          </span>
        )}

        {/* Single horizontal stats pill — bottom-right */}
        <div className="absolute bottom-3 right-3 z-10 inline-flex items-center gap-2 rounded-full bg-white/95 px-3 py-1.5 font-mono text-[11px] tabular-nums text-foreground shadow-[0_2px_8px_-1px_rgb(20,19,15,0.12)] backdrop-blur-md">
          <span className="font-semibold">{corridor.total_km}</span>
          <span className="text-muted-foreground/70">km</span>
          <span className="text-muted-foreground/30">·</span>
          <span>~{days}d</span>
        </div>
      </div>

      {/* Title — same size across all cards */}
      <div>
        <h3 className="text-[20px] font-bold leading-[1.05] tracking-[-0.025em] text-foreground">
          {corridor.label.split("→").map((part, i, arr) => (
            <span key={i}>
              {part.trim()}
              {i < arr.length - 1 && (
                <span className="mx-1.5 font-normal text-primary">→</span>
              )}
            </span>
          ))}
        </h3>
        <p className="mt-1 text-[13px] text-muted-foreground">
          {taglineFor(corridor.id)}
        </p>
      </div>

      {/* Stats — 2-row stack so they fit any card width.
          Row 1 = elevation sparkline (full width)
          Row 2 = ferry · routes (2 equal cells) */}
      <div className="overflow-hidden rounded-xl border border-border/60">
        <ElevationStat climbM={details.total_climb_m} elevation={details.elevation} />
        <div className="grid grid-cols-2 border-t border-border/60 bg-card">
          <FerryStat
            cost={details.ferry_cost_eur}
            label={details.ferry_label ?? null}
          />
          <div className="border-l border-border/60">
            <RoutesStat count={routeCount} />
          </div>
        </div>
      </div>

      {/* Highlights — always 3 for consistent height */}
      <ul className="space-y-1.5">
        {highlights.map((h, i) => {
          const meta = LAYER_META[h.layer];
          return (
            <li
              key={i}
              className="flex items-center gap-2 text-[13px] leading-none text-foreground/85"
            >
              <span
                className="h-1.5 w-1.5 shrink-0 rounded-full"
                style={{ background: meta.color }}
                aria-hidden
              />
              <span className="truncate">{h.label}</span>
            </li>
          );
        })}
      </ul>

      {/* Footer — meta + CTA arrow */}
      <div className="mt-auto flex items-center justify-between border-t border-border/60 pt-3">
        <div className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
          <span>signposted</span>
          <span className="text-muted-foreground/30">·</span>
          <span>{hasFerry ? "ferry" : "land only"}</span>
        </div>
        <span
          className={[
            "inline-flex items-center gap-1 text-[13px] font-semibold transition-colors",
            featured ? "text-primary" : "text-foreground/80 group-hover:text-foreground",
          ].join(" ")}
        >
          {featured ? "Plan this" : "Explore"}
          <ArrowUpRight
            className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5"
            aria-hidden
          />
        </span>
      </div>
    </button>
  );
}

function ElevationStat({ climbM, elevation }: { climbM: number; elevation: number[] }) {
  return (
    <div
      className="bg-card px-3 py-2.5"
      title="Indicative profile — derived from segment-level gain/loss. The agent fetches BRouter-precise samples per segment when you plan the route."
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-[9px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">
          Elevation
        </span>
        <span className="font-mono text-[10px] font-semibold tabular-nums text-foreground/80">
          ↑{climbM.toLocaleString()} m total
        </span>
      </div>
      <div className="mt-2 h-8 w-full">
        <ElevationSparkline
          points={elevation}
          width={300}
          height={32}
          className="h-full w-full"
        />
      </div>
    </div>
  );
}

function FerryStat({ cost, label }: { cost: number | null; label: string | null }) {
  return (
    <div className="px-3 py-2.5 text-center">
      <div className="font-mono text-[9px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">
        Ferry
      </div>
      <div className="mt-1 text-[16px] font-bold leading-none tracking-[-0.02em] tabular-nums text-foreground">
        {cost == null ? "—" : `€${cost}`}
      </div>
      <div className="mt-1 truncate font-mono text-[9px] text-muted-foreground/80">
        {cost == null ? "no crossing" : (label ?? "single fare")}
      </div>
    </div>
  );
}

function RoutesStat({ count }: { count: number }) {
  return (
    <div className="px-3 py-2.5 text-center">
      <div className="font-mono text-[9px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">
        Routes
      </div>
      <div className="mt-1 text-[16px] font-bold leading-none tracking-[-0.02em] tabular-nums text-foreground">
        {count}
      </div>
      <div className="mt-1 font-mono text-[9px] text-muted-foreground/80">
        {count === 1 ? "single path" : "to compare"}
      </div>
    </div>
  );
}

function taglineFor(corridorId: Corridor["id"]): string {
  switch (corridorId) {
    case "ldn-par":
      return "Avenue Verte · the headline route";
    case "ams-cph":
      return "EuroVelo 7 · the Baltic corridor";
    case "ldn-bri":
      return "South Downs classic · 1-day";
  }
}
