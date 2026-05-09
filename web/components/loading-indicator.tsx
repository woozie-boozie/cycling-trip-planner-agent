"use client";

import { Bike } from "lucide-react";

export function LoadingIndicator() {
  return (
    <div className="flex gap-3">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-card text-foreground/80 ring-1 ring-border/40">
        <Bike className="h-4 w-4" aria-hidden />
      </div>
      <div className="rounded-2xl rounded-tl-sm bg-card px-4 py-3 ring-1 ring-border/40">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <div className="flex gap-1">
            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-primary [animation-delay:-0.3s]" />
            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-primary [animation-delay:-0.15s]" />
            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-primary" />
          </div>
          <span className="text-xs">Thinking — calling tools, drafting plan, self-critique…</span>
        </div>
      </div>
    </div>
  );
}
