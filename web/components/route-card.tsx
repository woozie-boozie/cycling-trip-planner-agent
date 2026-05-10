"use client";

import { useMemo } from "react";
import { ArrowRight, Star } from "lucide-react";
import type { Corridor } from "@/lib/corridors";
import { staticMapUrl } from "@/lib/mapbox";
import { LAYER_META, POIS_BY_CORRIDOR, type PoiLayer } from "@/lib/pois";
import { getVariants } from "@/lib/route-variants";

interface RouteCardProps {
  corridor: Corridor;
  onSelect: (corridor: Corridor) => void;
  /** When true: emphasised treatment — primary border, glow, "Recommended" badge,
   * extras row showing elevation/ferry/paved metrics, primary-coloured CTA. */
  featured?: boolean;
}

const HIGHLIGHT_LAYERS: PoiLayer[] = ["heritage", "wildlife", "food"];

/**
 * Empty-state route gallery card. Modernized to match the v2 prototype:
 *   - Borderless map header with stats overlay (italic-serif km value)
 *   - Featured variant gets a "Recommended" badge top-left + extras row
 *     showing elevation / ferry / paved % stats
 *   - Bold sans-serif name with italic-serif arrow for personality
 *   - Highlights as bullet points with primary-coloured ◆ markers
 *   - Dark CTA button (primary on featured) — full-width, confident
 */
export function RouteCard({ corridor, onSelect, featured = false }: RouteCardProps) {
  const mapHeight = featured ? 320 : 240;
  const mapUrl = staticMapUrl(corridor, { width: 720, height: mapHeight + 40 });
  const days = corridor.estimated_days.at_100km;
  const variants = getVariants(corridor.id);

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
    if (picks.length < 3) {
      for (const p of pois) {
        if (picks.length >= (featured ? 4 : 3)) break;
        if (seen.has(p.label)) continue;
        picks.push({ layer: p.layer, label: p.label });
        seen.add(p.label);
      }
    }
    return picks.slice(0, featured ? 4 : 3);
  }, [corridor.id, featured]);

  const hasFerry = corridor.waypoints.some((w) => w.is_ferry);

  // Featured-only extras row
  const extras = featured
    ? [
        {
          v: hasFerry ? "1,490 m" : "850 m",
          l: "elevation",
        },
        {
          v: hasFerry ? "€68" : "free",
          l: "ferry",
        },
        {
          v: variants ? `${variants.length} variants` : "1 variant",
          l: "real BRouter",
        },
      ]
    : null;

  return (
    <button
      type="button"
      onClick={() => onSelect(corridor)}
      className={[
        "group relative flex flex-col overflow-hidden rounded-2xl border bg-card text-left transition-all duration-300 ease-out hover:-translate-y-1.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40",
        featured
          ? "border-primary shadow-[0_0_0_1px_var(--primary),0_12px_32px_-8px_rgb(255,61,20,0.18)] hover:shadow-[0_0_0_1px_var(--primary),0_24px_48px_-8px_rgb(255,61,20,0.30)]"
          : "border-border shadow-paper hover:border-foreground/30 hover:[box-shadow:0_2px_4px_-1px_rgb(20_19_15_/0.10),0_16px_32px_-8px_rgb(20_19_15_/0.14)]",
      ].join(" ")}
      style={
        featured
          ? {
              background:
                "linear-gradient(180deg, var(--card) 0%, color-mix(in oklab, var(--primary) 4%, var(--card)) 100%)",
            }
          : undefined
      }
    >
      {/* Recommended badge */}
      {featured && (
        <span className="absolute left-3.5 top-3.5 z-10 inline-flex items-center gap-1 rounded-full bg-primary px-2.5 py-1 font-mono text-[10px] font-bold uppercase tracking-[0.05em] text-primary-foreground shadow-[0_4px_12px_-2px_rgb(255,61,20,0.4)]">
          <Star className="h-2.5 w-2.5" fill="currentColor" aria-hidden />
          Recommended
        </span>
      )}

      {/* Map */}
      <div
        className="relative w-full overflow-hidden bg-muted"
        style={{ height: `${mapHeight}px` }}
      >
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

        {/* Stats overlay top-right */}
        <div className="absolute right-3.5 top-3.5 z-10 rounded-xl border border-white/60 bg-white/95 px-3 py-2 shadow-[0_4px_12px_-2px_rgb(20,19,15,0.10)] backdrop-blur-sm">
          <div
            className="font-heading text-[22px] italic leading-none tracking-[-0.01em] text-foreground"
            style={{ fontFamily: "var(--font-heading)" }}
          >
            {corridor.total_km}
            <span className="ml-0.5 font-sans text-[11px] not-italic text-muted-foreground">
              km
            </span>
          </div>
          <div className="mt-1 font-mono text-[10px] tabular-nums text-muted-foreground">
            ~{days} {days === 1 ? "day" : "days"}
          </div>
        </div>
      </div>

      {/* Featured-only extras row */}
      {featured && extras && (
        <div className="flex gap-3 border-y border-dashed border-border bg-white/60 px-5 py-3">
          {extras.map((e, i) => (
            <div key={i} className="flex-1 text-center">
              <div
                className="font-heading text-[18px] italic leading-none tracking-[-0.01em] text-foreground"
                style={{ fontFamily: "var(--font-heading)" }}
              >
                {e.v}
              </div>
              <div className="mt-1 font-mono text-[9px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                {e.l}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Body */}
      <div className="flex flex-1 flex-col gap-3.5 px-5 py-4">
        {/* Title — bold sans, primary arrow */}
        <div>
          <h3
            className={[
              "font-bold leading-[1.05] tracking-[-0.025em] text-foreground",
              featured ? "text-[26px]" : "text-[22px]",
            ].join(" ")}
          >
            {corridor.label.split("→").map((part, i, arr) => (
              <span key={i}>
                {part.trim()}
                {i < arr.length - 1 && (
                  <span className="mx-1.5 text-primary">→</span>
                )}
              </span>
            ))}
          </h3>
          <p
            className="mt-0.5 text-[13px] italic text-muted-foreground"
            style={{ fontFamily: "var(--font-heading)" }}
          >
            {taglineFor(corridor.id)}
          </p>
        </div>

        {/* Highlights */}
        {highlights.length > 0 && (
          <div>
            <p className="mb-1.5 font-mono text-[9px] font-semibold uppercase tracking-[0.1em] text-muted-foreground/80">
              Highlights
            </p>
            <ul className="space-y-1">
              {highlights.map((h, i) => {
                const meta = LAYER_META[h.layer];
                return (
                  <li
                    key={i}
                    className="flex items-start gap-2 text-[13px] leading-snug text-foreground/90"
                  >
                    <span
                      className="mt-1 inline-block h-1.5 w-1.5 shrink-0 rotate-45 transform"
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

        {/* Mono tags */}
        <div className="flex flex-wrap gap-1.5">
          <span className="rounded-full border border-border bg-muted px-2 py-0.5 font-mono text-[10px] text-foreground/85">
            signposted
          </span>
          {hasFerry && (
            <span className="rounded-full border border-border bg-muted px-2 py-0.5 font-mono text-[10px] text-foreground/85">
              ferry
            </span>
          )}
          <span className="rounded-full border border-border bg-muted px-2 py-0.5 font-mono text-[10px] text-foreground/85">
            mostly flat
          </span>
          {variants && variants.length > 1 && (
            <span className="rounded-full border border-primary/30 bg-primary/[0.06] px-2 py-0.5 font-mono text-[10px] font-semibold text-primary">
              {variants.length} variants
            </span>
          )}
        </div>

        {/* CTA — dark by default, primary on featured */}
        <button
          type="button"
          tabIndex={-1}
          className={[
            "mt-auto inline-flex w-full items-center justify-center gap-1.5 rounded-lg px-4 py-2.5 text-sm font-semibold transition-all",
            featured
              ? "bg-primary text-primary-foreground shadow-[0_4px_12px_-2px_rgb(255,61,20,0.4)] group-hover:bg-primary/90 group-hover:shadow-[0_8px_20px_-4px_rgb(255,61,20,0.50)]"
              : "bg-foreground text-background group-hover:bg-foreground/90",
          ].join(" ")}
        >
          {featured ? "Plan this route" : "Explore"}
          <ArrowRight
            className="h-4 w-4 transition-transform group-hover:translate-x-0.5"
            aria-hidden
          />
        </button>
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
