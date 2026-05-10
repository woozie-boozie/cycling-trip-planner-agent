"use client";

import { useMemo } from "react";
import { ArrowRight, Mountain, Ship, Sparkles } from "lucide-react";
import type { Corridor } from "@/lib/corridors";
import { staticMapUrl } from "@/lib/mapbox";
import { LAYER_META, POIS_BY_CORRIDOR, type PoiLayer } from "@/lib/pois";

interface RouteCardProps {
  corridor: Corridor;
  onSelect: (corridor: Corridor) => void;
}

// Layers we surface as "highlights" on the gallery card. Heritage +
// wildlife + food cover most of the "why ride this corridor" answers
// without needing the user to toggle anything.
const HIGHLIGHT_LAYERS: PoiLayer[] = ["heritage", "wildlife", "food"];

/**
 * Empty-state route gallery card. Each card pairs a tall Mapbox static
 * thumbnail with corridor stats, three highlight POIs (heritage,
 * wildlife, food — surfaced from `pois.ts`), and a primary CTA.
 *
 * The card is the user's first visual impression — biased toward
 * confident typography (italic serif title, mono-stat row) and visible
 * social-proof signals (highlights, ferry/signposted badges) over
 * dense paragraph copy.
 */
export function RouteCard({ corridor, onSelect }: RouteCardProps) {
  const mapUrl = staticMapUrl(corridor, { width: 720, height: 440 });
  const hasFerry = corridor.waypoints.some((w) => w.is_ferry);
  const days = corridor.estimated_days.at_100km;

  // Pick three notable POIs across heritage / wildlife / food to use
  // as the card's "highlights" strip. Picks the first one of each
  // layer found, falling back to whatever the corridor has when a
  // layer is empty.
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
    // Top up if we didn't find one in each preferred layer.
    if (picks.length < 3) {
      for (const p of pois) {
        if (picks.length >= 3) break;
        if (seen.has(p.label)) continue;
        picks.push({ layer: p.layer, label: p.label });
        seen.add(p.label);
      }
    }
    return picks;
  }, [corridor.id]);

  return (
    <button
      type="button"
      onClick={() => onSelect(corridor)}
      className="group relative flex flex-col overflow-hidden rounded-2xl border border-border bg-card text-left shadow-sm transition-all duration-200 hover:-translate-y-1 hover:border-primary/50 hover:shadow-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
    >
      {/* Thumbnail */}
      <div className="relative aspect-[16/11] w-full overflow-hidden bg-muted">
        {mapUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={mapUrl}
            alt={`${corridor.label} route map`}
            className="h-full w-full object-cover transition-transform duration-500 ease-out group-hover:scale-[1.04]"
            loading="lazy"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-xs text-muted-foreground">
            map preview unavailable
          </div>
        )}

        {/* Soft gradient overlay — improves legibility of the distance pill
            and the bottom-edge title float on dense maps. */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 bottom-0 h-24 bg-gradient-to-t from-card/95 via-card/60 to-transparent"
        />

        {/* Top-right pills */}
        <div className="absolute right-3 top-3 flex flex-col items-end gap-1.5">
          <span className="rounded-full bg-background/95 px-3 py-1 font-mono text-[11px] font-semibold tabular-nums text-foreground shadow-sm backdrop-blur-sm">
            {corridor.total_km} km
          </span>
          <span className="rounded-full bg-background/95 px-3 py-1 font-mono text-[11px] tabular-nums text-muted-foreground shadow-sm backdrop-blur-sm">
            ~{days} {days === 1 ? "day" : "days"}
          </span>
        </div>

        {/* Title floats up over the map's bottom edge — italic-serif voice */}
        <div className="absolute inset-x-0 bottom-0 px-5 pb-3">
          <h3
            className="font-heading text-2xl italic leading-[1.05] tracking-tight text-foreground drop-shadow-sm"
            style={{ fontFamily: "var(--font-heading)" }}
          >
            {corridor.label}
          </h3>
        </div>
      </div>

      {/* Body */}
      <div className="flex flex-1 flex-col gap-3 px-5 py-4">
        {/* Highlight POIs from heritage / wildlife / food layers */}
        {highlights.length > 0 && (
          <div className="space-y-1.5">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Highlights along the way
            </p>
            <ul className="space-y-1">
              {highlights.map((h, i) => {
                const meta = LAYER_META[h.layer];
                return (
                  <li
                    key={i}
                    className="flex items-center gap-2 text-[12.5px] leading-snug text-foreground/85"
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
          </div>
        )}

        {/* Tags row */}
        <div className="flex flex-wrap items-center gap-1.5 border-t border-border/60 pt-3">
          <span className="inline-flex items-center gap-1 rounded-full bg-muted/60 px-2 py-0.5 text-[10px] text-muted-foreground">
            <Sparkles className="h-2.5 w-2.5" aria-hidden /> signposted
          </span>
          {hasFerry ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-muted/60 px-2 py-0.5 text-[10px] text-muted-foreground">
              <Ship className="h-2.5 w-2.5" aria-hidden /> ferry
            </span>
          ) : null}
          <span className="inline-flex items-center gap-1 rounded-full bg-muted/60 px-2 py-0.5 text-[10px] text-muted-foreground">
            <Mountain className="h-2.5 w-2.5" aria-hidden /> mostly flat
          </span>
        </div>

        {/* Primary CTA — fills width, bigger, more confident */}
        <div className="mt-1 inline-flex w-full items-center justify-between rounded-lg border border-primary/40 bg-primary/5 px-3.5 py-2 text-sm font-semibold text-primary transition-colors group-hover:border-primary group-hover:bg-primary group-hover:text-primary-foreground">
          Plan this trip
          <ArrowRight
            className="h-4 w-4 transition-transform group-hover:translate-x-0.5"
            aria-hidden
          />
        </div>
      </div>
    </button>
  );
}
