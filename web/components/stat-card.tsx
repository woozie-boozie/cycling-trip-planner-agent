"use client";

import type { LucideIcon } from "lucide-react";

interface StatCardProps {
  label: string;
  value: string;
  hint?: string;
  icon: LucideIcon;
}

export function StatCard({ label, value, hint, icon: Icon }: StatCardProps) {
  return (
    <div className="rounded-lg border border-border/40 bg-card p-3">
      <div className="mb-1 flex items-center gap-1.5">
        <Icon className="h-3 w-3 text-muted-foreground" aria-hidden />
        <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
          {label}
        </span>
      </div>
      <div className="font-mono text-base font-semibold tabular-nums text-foreground">{value}</div>
      {hint ? <div className="mt-0.5 text-[10px] text-muted-foreground/70">{hint}</div> : null}
    </div>
  );
}
