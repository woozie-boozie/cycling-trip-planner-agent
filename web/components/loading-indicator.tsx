"use client";

import { useEffect, useMemo, useState } from "react";
import { Check, ChevronDown } from "lucide-react";
import type { TraceEvent, TraceResponse } from "@/lib/types";

interface LoadingIndicatorProps {
  /** Latest trace snapshot — surfaces tools + tokens + cost inline. */
  trace?: TraceResponse | null;
}

/**
 * Claude-style "thinking" panel — collapsed by default. The header is a
 * single dense line showing the agent is working + a stats summary. Click
 * the chevron to expand the full tool-call list. Mirrors Claude's
 * expandable thinking sections.
 *
 *   Collapsed:
 *     ● Thinking · 3.5s   17 tools · 219k tokens · $0.7428    [▾]
 *
 *   Expanded:
 *     ● Thinking · 3.5s                                       [▴]
 *     ────────────────────────────────────────────────────
 *     → get_route                                  245ms ✓
 *     → get_elevation_profile                      180ms ✓
 *     → get_weather                                312ms ✓
 *     ────────────────────────────────────────────────────
 *     17 tools · 219k tokens · $0.7428
 */
export function LoadingIndicator({ trace }: LoadingIndicatorProps) {
  const elapsed = useElapsed();
  const [open, setOpen] = useState(false);

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
  const tokensLabel = formatTokens(totalTokens);
  const latestTool = toolCalls.length > 0 ? toolCalls[toolCalls.length - 1] : null;

  return (
    <div className="rounded-xl border border-border/70 bg-card shadow-paper">
      {/* Header — clickable, single line */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="group flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-bg-soft/50"
        aria-expanded={open}
      >
        {/* Pulsing dot */}
        <span className="relative flex h-1.5 w-1.5 shrink-0">
          <span className="absolute inset-0 animate-ping rounded-full bg-primary opacity-75" />
          <span className="relative h-1.5 w-1.5 rounded-full bg-primary" />
        </span>

        {/* Title + elapsed */}
        <span className="flex shrink-0 items-baseline gap-2">
          <span className="text-[13px] font-semibold text-foreground">Thinking</span>
          <span className="font-mono text-[11px] tabular-nums text-muted-foreground">
            {elapsed.toFixed(1)}s
          </span>
        </span>

        {/* Currently-running tool — only when collapsed and a tool exists */}
        {!open && latestTool && (
          <span className="hidden min-w-0 items-baseline gap-1.5 truncate font-mono text-[11px] text-muted-foreground sm:inline-flex">
            <span className="text-primary">→</span>
            <span className="truncate">{latestTool.name}</span>
          </span>
        )}

        {/* Stats — pushed right */}
        <span className="ml-auto flex shrink-0 items-baseline gap-2 font-mono text-[10.5px] text-muted-foreground">
          <span>
            <span className="tabular-nums text-foreground/80">{toolCalls.length}</span> tools
          </span>
          <span className="text-muted-foreground/30">·</span>
          <span>
            <span className="tabular-nums text-foreground/80">{tokensLabel}</span> tokens
          </span>
          <span className="text-muted-foreground/30">·</span>
          <span className="tabular-nums text-foreground/80">{cost}</span>
        </span>

        {/* Chevron — rotates on open */}
        <ChevronDown
          className={[
            "h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200",
            open ? "rotate-180" : "rotate-0",
          ].join(" ")}
          aria-hidden
        />
      </button>

      {/* Expanded body — full tool list */}
      {open && (
        <div className="animate-in fade-in slide-in-from-top-1 duration-200 border-t border-border/60">
          {toolCalls.length === 0 ? (
            <div className="px-4 py-3 font-mono text-[11px] text-muted-foreground">
              No tool calls yet — the agent may be drafting text.
            </div>
          ) : (
            <ul className="max-h-[260px] overflow-y-auto px-4 py-2.5">
              {toolCalls.map((c, i) => (
                <li
                  key={i}
                  className="flex items-center gap-2 py-0.5 font-mono text-[11px] text-foreground/85"
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
        </div>
      )}
    </div>
  );
}

/** Compact token formatter — 1,234 stays "1,234"; 12,345 → "12.3k"; 1,234,567 → "1.2M". */
function formatTokens(n: number): string {
  if (n < 10_000) return n.toLocaleString();
  if (n < 1_000_000) return `${(n / 1_000).toFixed(1)}k`;
  return `${(n / 1_000_000).toFixed(1)}M`;
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
