"use client";

import { ArrowRight, MountainSnow, Ship } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { Corridor } from "@/lib/corridors";
import { staticMapUrl } from "@/lib/mapbox";

interface RouteCardProps {
  corridor: Corridor;
  onSelect: (corridor: Corridor) => void;
}

/**
 * Each card pairs a Mapbox static thumbnail with corridor stats and a
 * single-button CTA. Hover lifts and the CTA cues the click target.
 *
 * The thumbnail is fetched as a plain <img>; Mapbox returns ~80kB JPEG
 * per card so loading three is ~240kB total — comparable to a single
 * uncompressed product photo. No JS map runtime needed for previews.
 */
export function RouteCard({ corridor, onSelect }: RouteCardProps) {
  const mapUrl = staticMapUrl(corridor, { width: 600, height: 280 });
  const hasFerry = corridor.waypoints.some((w) => w.is_ferry);
  const days = corridor.estimated_days.at_100km;

  return (
    <button
      type="button"
      onClick={() => onSelect(corridor)}
      className="group flex flex-col overflow-hidden rounded-xl border border-border bg-card text-left shadow-sm transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
    >
      {/* Thumbnail */}
      <div className="relative aspect-[16/8] w-full overflow-hidden bg-muted">
        {mapUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={mapUrl}
            alt={`${corridor.label} route map`}
            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.02]"
            loading="lazy"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-xs text-muted-foreground">
            map preview unavailable
          </div>
        )}

        {/* Distance pill — bottom-right of thumbnail */}
        <div className="absolute right-2 top-2 rounded-full bg-background/95 px-2.5 py-1 text-[11px] font-medium text-foreground shadow-sm backdrop-blur-sm">
          {corridor.total_km} km
        </div>
      </div>

      {/* Body */}
      <div className="flex flex-1 flex-col gap-2 px-4 py-3">
        <div className="flex items-baseline justify-between gap-2">
          <h3 className="font-semibold leading-tight tracking-tight text-foreground">
            {corridor.label}
          </h3>
          <span className="font-mono text-[11px] tabular-nums text-muted-foreground">
            ~{days}d
          </span>
        </div>

        <p className="line-clamp-2 text-sm leading-snug text-muted-foreground">
          {corridor.description}
        </p>

        <div className="mt-1 flex flex-wrap items-center gap-1.5">
          {hasFerry ? (
            <Badge variant="outline" className="gap-1 text-[10px] font-normal">
              <Ship className="h-3 w-3" aria-hidden /> ferry
            </Badge>
          ) : null}
          <Badge variant="outline" className="gap-1 text-[10px] font-normal">
            <MountainSnow className="h-3 w-3" aria-hidden /> signposted
          </Badge>
        </div>

        <div className="mt-2 flex items-center gap-1 text-sm font-medium text-primary opacity-90 transition-opacity group-hover:opacity-100">
          Plan this trip
          <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" aria-hidden />
        </div>
      </div>
    </button>
  );
}
