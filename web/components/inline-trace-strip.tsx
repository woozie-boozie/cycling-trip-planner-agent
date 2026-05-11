"use client";

import { AlertCircle, Check, Loader2 } from "lucide-react";
import type { InlineTraceItem } from "@/lib/types";

interface InlineTraceStripProps {
  items: InlineTraceItem[];
}

/**
 * Per-message inline trace pills. Renders the agent's tool calls
 * next to its assistant bubble while the stream is in flight, so the
 * reader watches the agent think rather than waiting for the trace
 * sidebar to populate.
 *
 *   [ get_route                    ⟳ running… ]
 *   [ get_elevation_profile  →  ✓  85ms       ]
 *   [ find_accommodation     →  ✗  342ms      ]
 *
 * Visible in both text and visual modes — it's a universal upgrade.
 */
export function InlineTraceStrip({ items }: InlineTraceStripProps) {
  if (items.length === 0) return null;

  return (
    <div className="mb-2 flex flex-wrap gap-1.5">
      {items.map((item) => {
        const isRunning = item.status === "running";
        const isError = item.status === "error";
        return (
          <div
            key={item.toolUseId}
            className={[
              "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 font-mono text-[10.5px] transition-colors",
              isRunning &&
                "border border-primary/40 bg-primary/10 text-primary",
              isError &&
                "border border-destructive/40 bg-destructive/10 text-destructive",
              item.status === "done" &&
                "border border-border/60 bg-card text-foreground/85",
            ]
              .filter(Boolean)
              .join(" ")}
          >
            <span className="font-medium">{item.name}</span>
            {isRunning ? (
              <>
                <span className="text-primary/70">running…</span>
                <Loader2
                  className="h-3 w-3 animate-spin"
                  aria-hidden
                />
              </>
            ) : isError ? (
              <>
                <span className="text-muted-foreground">→</span>
                <AlertCircle className="h-3 w-3" aria-hidden />
                <span className="tabular-nums text-muted-foreground">
                  {item.latencyMs}ms
                </span>
              </>
            ) : (
              <>
                <span className="text-muted-foreground">→</span>
                <Check
                  className="h-3 w-3 text-emerald-600"
                  aria-hidden
                />
                <span className="tabular-nums text-muted-foreground">
                  {item.latencyMs}ms
                </span>
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}
