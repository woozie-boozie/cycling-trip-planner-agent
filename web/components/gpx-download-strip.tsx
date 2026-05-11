"use client";

import { Download } from "lucide-react";
import { getGpxUrl } from "@/lib/api";
import type { DayRow } from "@/lib/parse-itinerary";

interface GpxDownloadStripProps {
  /** Corridor start city — backend looks up the route by (start, end). */
  start: string;
  /** Corridor end city. */
  end: string;
  /** Variant identifier (e.g. "v16a_beauvais"). When null, the backend
   *  uses the corridor's default variant. */
  variantName: string | null;
  /** Parsed day rows from the agent's response — drives the per-day
   *  download buttons. */
  days: DayRow[];
  /** Optional override for the corridor label (defaults to "start → end"). */
  label?: string;
}

/**
 * Download buttons for the planned route's GPX files.
 *
 * Renders above the itinerary markdown so cyclists can grab the file
 * they actually ride with — track polyline + named overnight stops,
 * the same artifact Komoot / Ride With GPS expose.
 *
 * Per-day downloads use the parsed `from`/`to` city names so the GPX
 * day boundaries line up with the markdown day breakdown exactly. The
 * full-trip download is one GPX containing every waypoint.
 *
 * Buttons render as anchors with the native ``download`` attribute —
 * the backend's ``Content-Disposition`` header names the file
 * (e.g. ``london-paris-v16a_beauvais-day-3.gpx``).
 */
export function GpxDownloadStrip({
  start,
  end,
  variantName,
  days,
  label,
}: GpxDownloadStripProps) {
  const fullUrl = getGpxUrl({
    start,
    end,
    variant: variantName,
    mode: "full",
  });
  const displayLabel = label ?? `${start} → ${end}`;

  return (
    <div className="rounded-xl border border-border bg-card shadow-sm">
      {/* Header — title + full-trip download */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 px-4 py-3">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            GPX downloads · for your head-unit
          </p>
          <h3 className="mt-0.5 text-[15px] font-semibold leading-tight tracking-[-0.01em] text-foreground">
            {displayLabel}
          </h3>
        </div>
        <a
          href={fullUrl}
          download
          className="inline-flex items-center gap-1.5 rounded-full bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground transition-colors hover:bg-primary/90"
        >
          <Download className="h-3.5 w-3.5" aria-hidden />
          Whole trip
        </a>
      </div>

      {/* Per-day download row */}
      <div className="flex flex-wrap gap-2 px-4 py-3">
        {days.map((d) => {
          if (!d.from || !d.to) {
            return (
              <button
                key={`day-${d.n}`}
                type="button"
                disabled
                className="inline-flex items-center gap-1.5 rounded-full border border-dashed border-border/60 px-2.5 py-1 font-mono text-[11px] tabular-nums text-muted-foreground/60"
                title={`Day ${d.n} — missing from/to in the agent's prose`}
              >
                Day {d.n}
              </button>
            );
          }
          const dayUrl = getGpxUrl({
            start,
            end,
            variant: variantName,
            mode: "day",
            day: d.n,
            fromCity: d.from,
            toCity: d.to,
          });
          return (
            <a
              key={`day-${d.n}`}
              href={dayUrl}
              download
              className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-2.5 py-1 font-mono text-[11px] tabular-nums text-foreground transition-colors hover:border-primary/50 hover:bg-primary/5"
              title={`Download Day ${d.n} GPX (${d.from} → ${d.to})`}
            >
              <Download className="h-3 w-3" aria-hidden />
              Day {d.n}
            </a>
          );
        })}
      </div>
    </div>
  );
}
