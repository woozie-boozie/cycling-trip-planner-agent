"use client";

import { useEffect, useMemo, useState } from "react";
import { Check } from "lucide-react";
import type { TraceEvent, TraceResponse } from "@/lib/types";

interface LoadingIndicatorProps {
  /** Latest trace snapshot — surfaces tools + tokens + cost inline. */
  trace?: TraceResponse | null;
}

/**
 * Claude-style "thinking" panel — replaces the right-rail trace card.
 * Only visible while the agent is mid-turn; goes away the moment the
 * turn settles. Shows:
 *
 *   ● Thinking · 12.4s
 *   → get_route                  245ms ✓
 *   → get_elevation_profile      180ms ✓
 *   → get_weather                running…
 *
 *   8 tools · 15,418 tokens · $0.0485
 *
 * The stats row uses the most-recent /trace snapshot, which is
 * accurate for prior turns and a useful lagging indicator for the
 * current one (final numbers land on the message bubble after `done`).
 */
export function LoadingIndicator({ trace }: LoadingIndicatorProps) {
  const elapsed = useElapsed();

  const toolCalls = useMemo(() => {
    if (!trace) return [] as { name: string; latency: number; isError: boolean }[];
    const useEvents = new Map<string, TraceEvent>();
    const out: { name: string; latency: number; isError: boolean }[] = [];
    for (const e of trace.events) {
      if (e.type === "tool_use") {
        const id = String(e.payload.id ?? "");
        if (id) useEvents.set(id, e);
      }
      if (e.type === "tool_result") {
        const id = String(e.payload.tool_use_id ?? "");
        const useE = id ? useEvents.get(id) : undefined;
        if (!useE) continue;
        out.push({
          name: String(useE.payload.name ?? "unknown"),
          latency: Number(e.payload.latency_ms ?? 0),
          isError: Boolean(e.payload.is_error),
        });
      }
    }
    return out;
  }, [trace]);

  const totalTokens = trace ? trace.total_input_tokens + trace.total_output_tokens : 0;
  const cost = trace ? `$${trace.estimated_cost_usd.toFixed(4)}` : "$0.0000";

  return (
    <div className="rounded-xl border border-border/70 bg-card p-4 shadow-paper">
      {/* Header */}
      <div className="flex items-center gap-2">
        <span className="relative flex h-1.5 w-1.5">
          <span className="absolute inset-0 animate-ping rounded-full bg-primary opacity-75" />
          <span className="relative h-1.5 w-1.5 rounded-full bg-primary" />
        </span>
        <span className="text-[13px] font-semibold text-foreground">Thinking</span>
        <span className="font-mono text-[11px] tabular-nums text-muted-foreground">
          {elapsed.toFixed(1)}s
        </span>
      </div>

      {/* Tool list */}
      {toolCalls.length > 0 && (
        <ul className="mt-3 space-y-1">
          {toolCalls.map((c, i) => (
            <li
              key={i}
              className="flex items-center gap-2 font-mono text-[11px] text-foreground/85"
            >
              <span className="text-primary">→</span>
              <span>{c.name}</span>
              <span className="ml-auto flex items-center gap-1.5">
                <span className="tabular-nums text-muted-foreground/70">
                  {c.latency}ms
                </span>
                {c.isError ? (
                  <span className="text-destructive">✗</span>
                ) : (
                  <Check className="h-3 w-3 text-emerald-600" aria-hidden />
                )}
              </span>
            </li>
          ))}
        </ul>
      )}

      {/* Inline stats — tools · tokens · cost (claude-style) */}
      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-border/50 pt-2.5 font-mono text-[10.5px] uppercase tracking-[0.08em] text-muted-foreground">
        <span>
          <span className="tabular-nums text-foreground/80">{toolCalls.length}</span> tools
        </span>
        <span className="text-muted-foreground/30">·</span>
        <span>
          <span className="tabular-nums text-foreground/80">{totalTokens.toLocaleString()}</span> tokens
        </span>
        <span className="text-muted-foreground/30">·</span>
        <span>
          <span className="tabular-nums text-foreground/80">{cost}</span>
        </span>
      </div>
    </div>
  );
}

/** Elapsed-seconds counter, updates every 100ms while mounted. */
function useElapsed() {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const start = Date.now();
    const id = setInterval(() => {
      setElapsed((Date.now() - start) / 1000);
    }, 100);
    return () => clearInterval(id);
  }, []);
  return elapsed;
}
