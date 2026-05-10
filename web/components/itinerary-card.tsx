"use client";

import { useMemo } from "react";
import { ArrowRight, Bed, Building2, Ship, Tent } from "lucide-react";
import { ElevationSparkline } from "@/components/elevation-sparkline";
import type { Corridor, CorridorWaypoint } from "@/lib/corridors";
import type { AccomType, DayRow } from "@/lib/parse-itinerary";

interface ItineraryCardProps {
  days: DayRow[];
  /** Optional title — e.g. "Amsterdam → Copenhagen · 11 days" */
  title?: string;
  /** Optional subtitle — e.g. "Inland EV7/12 · 836km" */
  subtitle?: string;
  /** Conversation-scoped corridor — used to fill in missing per-day km
   *  by matching from/to against the corridor waypoints. */
  corridor?: Corridor | null;
}

/**
 * Day-by-day visual card. Each row condenses a day's plan into:
 *   number · date (if known) · from → to · mini elevation · km · climb · accom
 *
 * Renders only when `parseItinerary()` extracts ≥3 day rows from the
 * agent's markdown response. Otherwise the visual response renderer
 * falls through to MarkdownRenderer.
 */
export function ItineraryCard({ days, title, subtitle, corridor }: ItineraryCardProps) {
  // Enrich each day's km from corridor waypoints when the agent's
  // markdown didn't include a "Distance: N km" line. Memoised so the
  // expensive name-matching only re-runs when inputs change.
  const enriched = useMemo(
    () => days.map((d) => enrichKm(d, corridor ?? null)),
    [days, corridor],
  );

  const totalKm = enriched.reduce((s, d) => s + (d.km ?? 0), 0);
  const totalClimb = enriched.reduce((s, d) => s + (d.climb ?? 0), 0);
  const maxKm = Math.max(1, ...enriched.map((d) => d.km ?? 0));

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
      {/* Header */}
      <div className="border-b border-border/60 px-4 py-3">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          Day-by-day plan · {days.length} days
        </p>
        <h3 className="mt-0.5 text-xl font-bold leading-tight tracking-[-0.02em] text-foreground">
          {title ?? "Trip plan"}
        </h3>
        {subtitle && (
          <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p>
        )}
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-0.5 font-mono text-[11px] tabular-nums text-muted-foreground">
          <span>
            <strong className="font-semibold text-foreground">
              {Math.round(totalKm)}
            </strong>{" "}
            km
          </span>
          <span>
            <strong className="font-semibold text-foreground">
              {days.length}
            </strong>{" "}
            d
          </span>
          {totalClimb > 0 && (
            <span>
              ↑
              <strong className="font-semibold text-foreground">
                {totalClimb}
              </strong>{" "}
              m
            </span>
          )}
        </div>
      </div>

      {/* Day rows */}
      <div className="divide-y divide-border/60">
        {enriched.map((d) => (
          <DayRowComponent key={d.n} day={d} maxKm={maxKm} />
        ))}
      </div>
    </div>
  );
}

/**
 * Fill in a day's km when the agent's markdown only reported climb.
 * Match the day's `from`/`to` against the corridor's waypoints by
 * loose case-insensitive substring, take the absolute difference of
 * `km_from_start`. If either endpoint is unmatched, leave km null.
 */
function enrichKm(day: DayRow, corridor: Corridor | null): DayRow {
  if (day.km != null && day.km > 0) return day;
  if (!corridor || !day.from || !day.to) return day;

  const from = findWaypoint(corridor.waypoints, day.from);
  const to = findWaypoint(corridor.waypoints, day.to);
  if (!from || !to) return day;

  const km = Math.abs(to.km_from_start - from.km_from_start);
  if (km <= 0) return day;
  return { ...day, km };
}

function findWaypoint(waypoints: CorridorWaypoint[], name: string): CorridorWaypoint | null {
  const norm = name.trim().toLowerCase();
  if (!norm) return null;
  // Exact match first
  const exact = waypoints.find((w) => w.name.toLowerCase() === norm);
  if (exact) return exact;
  // Substring fallback — handles "Forges-les-Eaux" vs "Forges Les Eaux".
  return (
    waypoints.find((w) => norm.includes(w.name.toLowerCase())) ??
    waypoints.find((w) => w.name.toLowerCase().includes(norm)) ??
    null
  );
}

function DayRowComponent({ day, maxKm }: { day: DayRow; maxKm: number }) {
  const isFerry = day.has_ferry || day.accom_type === "ferry";
  const profile = dayProfile(day.km, day.climb, day.n, isFerry);

  // Relative-length bar (0..1) — for quick "how much cycling" comparison
  // across days. Ferry days = 0; rest of the bar fills proportional to
  // the day's km against the longest cycling day.
  const lengthRatio = isFerry ? 0 : Math.min(1, (day.km ?? 0) / maxKm);
  const intensityLabel = labelForIntensity(day.km, day.climb, isFerry);

  return (
    <div className="grid grid-cols-[28px_1fr_220px] items-center gap-4 px-4 py-3.5 transition-colors hover:bg-muted/30">
      {/* Day number */}
      <div className="flex h-7 w-7 items-center justify-center text-muted-foreground">
        <span className="text-base font-bold tabular-nums">{day.n}</span>
      </div>

      {/* Route + accommodation + distance bar */}
      <div className="min-w-0">
        <div className="flex items-center gap-2 text-sm">
          {day.date && (
            <span className="font-mono text-[10px] tabular-nums text-muted-foreground">
              {day.date}
            </span>
          )}
          <span className="truncate font-medium text-foreground">
            {day.from ? (
              <>
                {day.from}{" "}
                <ArrowRight
                  className="inline h-3 w-3 text-muted-foreground"
                  aria-hidden
                />{" "}
                {day.to}
              </>
            ) : (
              day.to ?? "—"
            )}
          </span>
        </div>

        {/* Stat row — km is now the headline number, with a relative bar */}
        <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
          {isFerry ? (
            <span className="inline-flex items-center gap-1 font-semibold text-primary">
              <Ship className="h-3 w-3" aria-hidden /> Ferry crossing
            </span>
          ) : (
            <>
              {day.km != null && day.km > 0 && (
                <span className="font-mono tabular-nums">
                  <strong className="text-[13px] font-bold text-foreground">
                    {day.km}
                  </strong>
                  <span className="ml-0.5">km</span>
                </span>
              )}
              {intensityLabel && (
                <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-muted-foreground/80">
                  · {intensityLabel}
                </span>
              )}
            </>
          )}
          {day.accommodation && (
            <span className="inline-flex min-w-0 items-center gap-1">
              <AccomGlyph type={day.accom_type ?? "unknown"} />
              <span className="truncate">{day.accommodation}</span>
            </span>
          )}
        </div>

        {/* Relative-length bar — fills proportional to longest cycling day.
            Skipped for ferries (rendered as faint dashed track). */}
        <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-border/60">
          {isFerry ? (
            <div
              className="h-full w-full"
              style={{
                backgroundImage:
                  "repeating-linear-gradient(90deg, var(--muted-foreground) 0 4px, transparent 4px 8px)",
                opacity: 0.35,
              }}
              aria-hidden
            />
          ) : (
            <div
              className="h-full rounded-full bg-primary transition-all duration-500"
              style={{ width: `${Math.max(4, lengthRatio * 100)}%` }}
              aria-hidden
            />
          )}
        </div>
      </div>

      {/* Per-day elevation sparkline */}
      <div
        className="flex flex-col items-end justify-center"
        title={
          isFerry
            ? `Day ${day.n} · ferry crossing (sea-level)`
            : `Day ${day.n} indicative profile${day.climb ? ` · ↑${day.climb} m` : ""}${day.km ? ` over ${day.km} km` : ""}`
        }
      >
        <div className="flex w-full items-baseline justify-between gap-2">
          <span className="font-mono text-[9.5px] font-semibold uppercase tracking-[0.1em] text-muted-foreground/80">
            {isFerry ? "Crossing" : "Elevation"}
          </span>
          {!isFerry && day.climb != null && day.climb > 0 && (
            <span className="font-mono text-[9.5px] font-semibold tabular-nums text-foreground/70">
              ↑{day.climb}m
            </span>
          )}
        </div>
        <div className="mt-1 h-7 w-full">
          <ElevationSparkline
            points={profile}
            width={210}
            height={28}
            color={isFerry ? "var(--muted-foreground)" : "var(--primary)"}
            className="h-full w-full"
          />
        </div>
      </div>
    </div>
  );
}

/**
 * Friendly intensity label for a cycling day, based on km. Lets the user
 * tell at a glance whether a day is easy/hard without doing the math.
 */
function labelForIntensity(
  km: number | undefined,
  _climbM: number | undefined,
  isFerry: boolean,
): string | null {
  if (isFerry) return null;
  if (km == null || km <= 0) return null;
  if (km < 50) return "Easy day";
  if (km < 80) return "Steady";
  if (km < 110) return "Long day";
  return "Brutal";
}

/**
 * Generate a believable normalised elevation profile for a single day.
 *
 *   - Ferry days: a near-flat sea-level line — there's no cycling.
 *   - Both km + climb known: intensity = m/km, capped at 15 m/km
 *     (mountainous). Drives peak height.
 *   - Only climb known: assume a typical 70 km day for intensity calc.
 *   - Only km known: low intensity (assume gentle terrain).
 *   - Neither known: a quiet near-flat line so the row still has rhythm.
 *
 * Three layered sine waves at different frequencies, phase-shifted by
 * `dayNumber × 0.7` so consecutive days don't look identical.
 *
 * Indicative — true within-day terrain comes from BRouter via
 * `get_elevation_profile` when the agent plans the segment.
 */
function dayProfile(
  km: number | undefined,
  climbM: number | undefined,
  dayNumber: number,
  isFerry: boolean,
): number[] {
  // Ferry day — completely flat sea-level line with tiny ripple
  if (isFerry) {
    return Array.from({ length: 18 }, (_, i) =>
      0.06 + Math.sin(i * 0.6) * 0.015,
    );
  }

  // Estimate intensity — m of climb per km. Cap at ~15 m/km mountainous.
  let intensity: number;
  if (km && km > 0 && climbM && climbM > 0) {
    intensity = Math.min(1, climbM / km / 15);
  } else if (climbM && climbM > 0) {
    // Only climb known — assume a typical 70 km day.
    intensity = Math.min(1, climbM / 70 / 15);
  } else if (km && km > 0) {
    // Only km known — assume gentle terrain (~3 m/km).
    intensity = 0.2;
  } else {
    // Nothing known — quiet near-flat line.
    intensity = 0.12;
  }

  const phase = dayNumber * 0.7;
  const points = 24;
  return Array.from({ length: points }, (_, i) => {
    const t = i / (points - 1);
    const w =
      Math.sin(t * Math.PI * 4 + phase) * 0.40 +
      Math.sin(t * Math.PI * 7 + phase * 2) * 0.25 +
      Math.sin(t * Math.PI * 2 + phase * 0.5) * 0.35;
    const normalised = (w + 1) / 2; // 0..1
    return Math.max(0.05, Math.min(1, 0.10 + normalised * 0.85 * intensity));
  });
}

function AccomGlyph({ type }: { type: AccomType }) {
  const className = "h-3 w-3 text-muted-foreground";
  switch (type) {
    case "camping":
      return <Tent className={className} aria-hidden />;
    case "hostel":
      return <Bed className={className} aria-hidden />;
    case "hotel":
    case "guesthouse":
      return <Building2 className={className} aria-hidden />;
    case "ferry":
      return <Ship className={className} aria-hidden />;
    default:
      return <Bed className={className} aria-hidden />;
  }
}

