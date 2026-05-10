"use client";

import type { LucideIcon } from "lucide-react";

interface StatCardProps {
  label: string;
  value: string;
  hint?: string;
  icon: LucideIcon;
  /** When set, shifts the value colour (used for cost) */
  accent?: "default" | "primary";
}

/**
 * Compact statistic display — borderless, leans on background contrast
 * and typography hierarchy instead of generic dashboard borders.
 *
 *   ┌──────────────────────────┐
 *   │ ICON  TOKENS             │
 *   │       19,277 tokens      │  ← prominent value
 *   │       18,443 in · 834 out│  ← hint (smaller)
 *   └──────────────────────────┘
 */
export function StatCard({ label, value, hint, icon: Icon, accent = "default" }: StatCardProps) {
  return (
    <div className="rounded-xl bg-card/60 px-3 py-2.5 ring-1 ring-border/50 transition-colors hover:bg-card/80">
      <div className="flex items-center gap-1.5">
        <Icon className="h-3 w-3 text-muted-foreground/70" aria-hidden />
        <span className="text-[9.5px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
          {label}
        </span>
      </div>
      <div
        className={[
          "mt-1 font-heading text-2xl italic tabular-nums leading-none",
          accent === "primary" ? "text-primary" : "text-foreground",
        ].join(" ")}
        style={{ fontFamily: "var(--font-heading)" }}
      >
        {value}
      </div>
      {hint ? (
        <div className="mt-1 font-mono text-[10px] text-muted-foreground/80">
          {hint}
        </div>
      ) : null}
    </div>
  );
}
