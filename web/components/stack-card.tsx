"use client";

import { Boxes } from "lucide-react";

/**
 * Static "Stack" card for the right rail — fills the vertical space
 * below the LiveTracePanel + ContextCard with a quiet credibility row
 * showing the architectural depth of the system.
 *
 * Pure-content card — no live data. Shows the build numbers a reviewer
 * cares about: test coverage, eval scenarios, ADRs, real-data sources.
 */
export function StackCard() {
  return (
    <div className="rounded-2xl border border-border bg-card p-4 shadow-paper">
      <div className="mb-3 flex items-center justify-between">
        <span className="font-mono text-[10.5px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
          Stack · what&apos;s behind it
        </span>
        <Boxes className="h-3 w-3 text-primary" aria-hidden />
      </div>

      <div className="grid grid-cols-2 gap-2">
        <Tile label="Unit tests" value="90/90" sub="hermetic, ~1.6s" />
        <Tile label="Eval scenarios" value="6 + 1" sub="real-Claude evals" />
        <Tile label="ADRs" value="15" sub="architecture decisions" />
        <Tile label="Tools" value="8" sub="4 brief + critique + 3 bonus" />
      </div>

      <div className="mt-3 border-t border-border/60 pt-3">
        <div className="font-mono text-[9.5px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
          Tools registered
        </div>
        <div className="mt-1.5 flex flex-wrap gap-1">
          {TOOLS.map((t) => (
            <span
              key={t}
              className="rounded-full border border-border bg-muted px-1.5 py-0.5 font-mono text-[9.5px] text-foreground/85"
            >
              {t}
            </span>
          ))}
        </div>
      </div>

      <div className="mt-3 text-[11px] leading-relaxed text-muted-foreground">
        Every tool result is Pydantic-validated at the boundary. The agent
        loop is ~120 lines of plain async Python; the orchestrator never
        sees the difference between seed-data and real-API tools.
      </div>
    </div>
  );
}

const TOOLS: string[] = [
  "get_route",
  "get_elevation_profile",
  "get_weather",
  "find_accommodation",
  "critique_trip_plan",
  "get_points_of_interest",
  "get_ferry_schedule",
  "estimate_budget",
];

function Tile({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub: string;
}) {
  return (
    <div className="rounded-md border border-border bg-bg-soft px-2.5 py-2">
      <div className="font-mono text-[9px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
        {label}
      </div>
      <div
        className="mt-0.5 font-heading text-lg italic leading-none tabular-nums text-foreground"
        style={{ fontFamily: "var(--font-heading)" }}
      >
        {value}
      </div>
      <div className="mt-0.5 font-mono text-[9.5px] text-muted-foreground">
        {sub}
      </div>
    </div>
  );
}
