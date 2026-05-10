"use client";

import { ArrowRight, Bed, Building2, Mountain, Ship, Tent } from "lucide-react";
import type { AccomType, DayRow } from "@/lib/parse-itinerary";

interface ItineraryCardProps {
  days: DayRow[];
  /** Optional title — e.g. "Amsterdam → Copenhagen · 11 days" */
  title?: string;
  /** Optional subtitle — e.g. "Inland EV7/12 · 836km" */
  subtitle?: string;
}

/**
 * Day-by-day visual card. Each row condenses a day's plan into:
 *   number · date (if known) · from → to · mini elevation · km · climb · accom
 *
 * Renders only when `parseItinerary()` extracts ≥3 day rows from the
 * agent's markdown response. Otherwise the visual response renderer
 * falls through to MarkdownRenderer.
 */
export function ItineraryCard({ days, title, subtitle }: ItineraryCardProps) {
  const totalKm = days.reduce((s, d) => s + (d.km ?? 0), 0);
  const totalClimb = days.reduce((s, d) => s + (d.climb ?? 0), 0);

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
      {/* Header */}
      <div className="border-b border-border/60 px-4 py-3">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          Day-by-day plan · {days.length} days
        </p>
        <h3
          className="font-heading mt-0.5 text-xl italic leading-tight text-foreground"
          style={{ fontFamily: "var(--font-heading)" }}
        >
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
        {days.map((d) => (
          <DayRowComponent key={d.n} day={d} />
        ))}
      </div>
    </div>
  );
}

function DayRowComponent({ day }: { day: DayRow }) {
  const isFerry = day.has_ferry || day.accom_type === "ferry";
  return (
    <div className="grid grid-cols-[28px_1fr_auto] items-start gap-2 px-3 py-2 transition-colors hover:bg-muted/30">
      {/* Day number */}
      <div className="flex h-7 w-7 items-center justify-center text-muted-foreground">
        <span
          className="font-heading text-base italic"
          style={{ fontFamily: "var(--font-heading)" }}
        >
          {day.n}
        </span>
      </div>

      {/* Route + accommodation */}
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
        <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-muted-foreground">
          {isFerry ? (
            <span className="inline-flex items-center gap-1 text-primary">
              <Ship className="h-3 w-3" aria-hidden /> ferry crossing
            </span>
          ) : (
            <>
              {day.km != null && (
                <span className="font-mono tabular-nums">
                  <strong className="font-semibold text-foreground">
                    {day.km}
                  </strong>
                  km
                </span>
              )}
              {day.climb != null && day.climb > 0 && (
                <span className="font-mono tabular-nums">
                  ↑
                  <strong className="font-semibold text-foreground">
                    {day.climb}
                  </strong>
                  m
                </span>
              )}
            </>
          )}
          {day.accommodation && (
            <span className="inline-flex items-center gap-1">
              <AccomGlyph type={day.accom_type ?? "unknown"} />
              <span className="truncate">{day.accommodation}</span>
            </span>
          )}
        </div>
      </div>

      {/* Mini elevation pictogram (compact, decorative) */}
      <div className="flex h-7 items-center">
        <ElevPictogram km={day.km} climb={day.climb} />
      </div>
    </div>
  );
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

/**
 * Tiny elevation pictogram derived from km + climb. Not a real profile —
 * just a heuristic gradient pictogram that gives the row visual texture.
 * Days with no climb / no km render as a flat line.
 */
function ElevPictogram({ km, climb }: { km?: number; climb?: number }) {
  const w = 56;
  const h = 22;
  if (!km || !climb || climb < 30) {
    return (
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
        <line
          x1="2"
          y1={h - 2}
          x2={w - 2}
          y2={h - 2}
          stroke="var(--muted-foreground)"
          strokeWidth="1"
          opacity="0.5"
        />
      </svg>
    );
  }

  // Synthetic profile: 8-point sin wave biased by gradient ratio
  const ratio = Math.min(1, climb / Math.max(40, km * 12));
  const points = 10;
  const peak = h * 0.85 * ratio;
  const path = Array.from({ length: points }, (_, i) => {
    const x = (i / (points - 1)) * (w - 4) + 2;
    const offset = Math.sin((i / (points - 1)) * Math.PI * 1.5) * peak;
    const drift = (i / (points - 1)) * (peak * 0.4);
    const y = h - 2 - Math.max(0, offset - drift);
    return `${x.toFixed(1)} ${y.toFixed(1)}`;
  });
  const linePath = "M " + path.join(" L ");
  const areaPath = `M 2 ${h - 2} L ${path.join(" L ")} L ${w - 2} ${h - 2} Z`;

  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
      <path
        d={areaPath}
        fill="var(--primary)"
        opacity="0.18"
      />
      <path
        d={linePath}
        fill="none"
        stroke="var(--primary)"
        strokeWidth="1.2"
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity="0.7"
      />
      <Mountain
        className="hidden"
        aria-hidden
      />
    </svg>
  );
}
