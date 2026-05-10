"use client";

import { useMemo } from "react";
import { ArrowUpRight, Sparkles } from "lucide-react";
import type { Corridor } from "@/lib/corridors";
import { staticMapUrl } from "@/lib/mapbox";
import { LAYER_META, POIS_BY_CORRIDOR, type PoiLayer } from "@/lib/pois";
import { getVariants } from "@/lib/route-variants";

interface RouteCardProps {
  corridor: Corridor;
  onSelect: (corridor: Corridor) => void;
  /** When true: emphasised treatment — subtle gradient, "Recommended"
   *  chip, extras row showing elevation/ferry/paved metrics, primary CTA. */
  featured?: boolean;
  /** When true: tighter spacing, smaller map, fewer highlights. */
  compact?: boolean;
}

const HIGHLIGHT_LAYERS: PoiLayer[] = ["heritage", "wildlife", "food"];

/**
 * Empty-state route gallery card — modernised v3.
 *
 *   - One single border treatment across all cards (no double-border on
 *     featured). Differentiation comes from a soft tinted background +
 *     "Recommended" chip, not louder shadows.
 *   - Map sits in a rounded inner frame inside the card (modern bento
 *     feel, not full-bleed top).
 *   - Stats overlay on the map is a single horizontal pill.
 *   - Highlights are bullet rows with coloured dot markers.
 *   - CTA is a quiet link with an arrow — the card itself is the button.
 */
export function RouteCard({ corridor, onSelect, featured = false, compact = false }: RouteCardProps) {
  const mapHeight = featured ? 240 : compact ? 170 : 200;
  const mapUrl = staticMapUrl(corridor, { width: 720, height: mapHeight + 40 });
  const days = corridor.estimated_days.at_100km;
  const variants = getVariants(corridor.id);
  const highlightCount = featured ? 4 : compact ? 3 : 3;

  // Pick highlight POIs for the corridor
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
    if (picks.length < highlightCount) {
      for (const p of pois) {
        if (picks.length >= highlightCount) break;
        if (seen.has(p.label)) continue;
        picks.push({ layer: p.layer, label: p.label });
        seen.add(p.label);
      }
    }
    return picks.slice(0, highlightCount);
  }, [corridor.id, highlightCount]);

  const hasFerry = corridor.waypoints.some((w) => w.is_ferry);

  // Featured-only extras row
  const extras = featured
    ? [
        { v: hasFerry ? "1,490" : "850", u: "m", l: "elevation" },
        { v: hasFerry ? "€68" : "free", u: "", l: "ferry cost" },
        {
          v: variants ? String(variants.length) : "1",
          u: "",
          l: variants && variants.length === 1 ? "route" : "routes",
        },
      ]
    : null;

  return (
    <button
      type="button"
      onClick={() => onSelect(corridor)}
      className={[
        "group relative flex flex-col gap-4 overflow-hidden rounded-2xl border p-4 text-left transition-all duration-300 ease-out hover:-translate-y-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40",
        featured
          ? "border-foreground/10 bg-[linear-gradient(180deg,rgba(255,61,20,0.04)_0%,rgba(255,255,255,1)_60%)] shadow-[0_1px_2px_-1px_rgb(20_19_15_/0.06),0_8px_24px_-8px_rgb(255_61_20_/0.18)] hover:shadow-[0_2px_4px_-1px_rgb(20_19_15_/0.08),0_24px_48px_-12px_rgb(255_61_20_/0.28)]"
          : "border-border/80 bg-card shadow-paper hover:border-foreground/15 hover:shadow-lift",
      ].join(" ")}
    >
      {/* Map — rounded inner frame, modern bento feel */}
      <div
        className="relative w-full overflow-hidden rounded-xl bg-muted ring-1 ring-foreground/5"
        style={{ height: `${mapHeight}px` }}
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

        {/* Recommended chip — top-left, modern pill */}
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

      {/* Title */}
      <div>
        <h3
          className={[
            "font-bold leading-[1.05] tracking-[-0.025em] text-foreground",
            featured ? "text-[24px]" : compact ? "text-[18px]" : "text-[20px]",
          ].join(" ")}
        >
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

      {/* Featured-only extras row — clean stat trio */}
      {featured && extras && (
        <div className="grid grid-cols-3 divide-x divide-border/60 rounded-xl border border-border/60 bg-bg-soft/60">
          {extras.map((e, i) => (
            <div key={i} className="px-3 py-2.5 text-center">
              <div className="text-[18px] font-bold leading-none tracking-[-0.02em] tabular-nums text-foreground">
                {e.v}
                {e.u && (
                  <span className="ml-0.5 text-[11px] font-medium text-muted-foreground">
                    {e.u}
                  </span>
                )}
              </div>
              <div className="mt-1 font-mono text-[9px] font-medium uppercase tracking-[0.08em] text-muted-foreground/80">
                {e.l}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Highlights */}
      {highlights.length > 0 && (
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
      )}

      {/* Footer — CTA arrow link, no chip noise */}
      <div className="mt-auto flex items-center justify-between border-t border-border/60 pt-3">
        <div className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
          <span>signposted</span>
          <span className="text-muted-foreground/30">·</span>
          <span>{hasFerry ? "ferry" : "land only"}</span>
          {variants && variants.length > 1 && (
            <>
              <span className="text-muted-foreground/30">·</span>
              <span className="text-primary">{variants.length} routes</span>
            </>
          )}
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
