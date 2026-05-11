"use client";

import { Activity, Coins, Cpu, Wrench } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { StatCard } from "@/components/stat-card";
import { ToolCallRow } from "@/components/tool-call-row";
import { RouteMap } from "@/components/route-map";
import type { Corridor } from "@/lib/corridors";
import type { TraceEvent, TraceResponse } from "@/lib/types";

interface TracePanelProps {
  trace: TraceResponse | null;
  isLoading: boolean;
  hasSession: boolean;
  corridor: Corridor | null;
}

interface ToolCallSummary {
  name: string;
  iteration: number;
  isError: boolean;
  latencyMs: number;
}

function summarizeToolCalls(events: TraceEvent[]): ToolCallSummary[] {
  // Pair tool_use events with their tool_result counterparts by tool_use_id
  // so we can show latency + error status per call.
  const calls: ToolCallSummary[] = [];
  const useEventsById = new Map<string, TraceEvent>();

  for (const e of events) {
    if (e.type === "tool_use") {
      const id = String(e.payload.id ?? "");
      if (id) useEventsById.set(id, e);
    }
    if (e.type === "tool_result") {
      const id = String(e.payload.tool_use_id ?? "");
      const useEvent = id ? useEventsById.get(id) : undefined;
      if (!useEvent) continue;
      calls.push({
        name: String(useEvent.payload.name ?? "unknown"),
        iteration: useEvent.iteration,
        isError: Boolean(e.payload.is_error),
        latencyMs: Number(e.payload.latency_ms ?? 0),
      });
    }
  }

  return calls;
}

function countAssistantTexts(events: TraceEvent[]): number {
  return events.filter((e) => e.type === "assistant_text").length;
}

function maxIteration(events: TraceEvent[]): number {
  return events.reduce((max, e) => Math.max(max, e.iteration ?? 0), 0);
}

export function TracePanel({ trace, isLoading, hasSession, corridor }: TracePanelProps) {
  if (!hasSession && !isLoading) {
    return (
      <div className="flex h-full flex-col gap-3">
        <RouteMap corridor={corridor} />
        <EmptyTrace />
      </div>
    );
  }

  if (isLoading && !trace) {
    return (
      <div className="flex h-full flex-col gap-3">
        <RouteMap corridor={corridor} />
        <LoadingTrace />
      </div>
    );
  }

  if (!trace) {
    return (
      <div className="flex h-full flex-col gap-3">
        <RouteMap corridor={corridor} />
        <EmptyTrace />
      </div>
    );
  }

  const calls = summarizeToolCalls(trace.events);
  const iterations = maxIteration(trace.events);
  const assistantTurns = countAssistantTexts(trace.events);

  return (
    <div className="flex h-full flex-col gap-3">
      {/* Map at the top — always visible, updates as we recognise the corridor */}
      <RouteMap corridor={corridor} />

      {/* Header */}
      <div>
        <h3 className="font-mono text-[10px] font-semibold uppercase tracking-[0.15em] text-muted-foreground">
          Trace · receipts
        </h3>
        <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground/80">
          Every tool call this session — latencies, tokens, cost. Same data the
          eval harness asserts.
        </p>
      </div>

      {/* Stats grid — borderless cards, italic-serif numbers */}
      <div className="grid grid-cols-2 gap-2">
        <StatCard
          label="Iterations"
          value={String(iterations)}
          hint={`${assistantTurns} assistant turns`}
          icon={Activity}
        />
        <StatCard
          label="Tool calls"
          value={String(calls.length)}
          icon={Wrench}
        />
        <StatCard
          label="Tokens"
          value={(trace.total_input_tokens + trace.total_output_tokens).toLocaleString()}
          hint={`${trace.total_input_tokens.toLocaleString()} in · ${trace.total_output_tokens.toLocaleString()} out`}
          icon={Cpu}
        />
        <StatCard
          label="Est. cost"
          value={`$${trace.estimated_cost_usd.toFixed(4)}`}
          hint="Sonnet pricing"
          icon={Coins}
          accent="primary"
        />
      </div>

      {/* Tool call list */}
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="mb-2 flex items-center justify-between">
          <h4 className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            Tool calls
          </h4>
          {calls.length > 0 ? (
            <span className="text-[10px] text-muted-foreground/70">
              {calls.filter((c) => !c.isError).length}/{calls.length} ok
            </span>
          ) : null}
        </div>
        <div className="flex-1 space-y-1.5 overflow-y-auto pr-1">
          {calls.length === 0 ? (
            <p className="text-xs text-muted-foreground/70">
              No tool calls yet — the agent might still be planning.
            </p>
          ) : (
            calls.map((c, idx) => (
              <ToolCallRow
                key={`${c.name}-${idx}`}
                name={c.name}
                isError={c.isError}
                latencyMs={c.latencyMs}
                iteration={c.iteration}
              />
            ))
          )}
        </div>
      </div>

      {/* Session id at bottom for debugging */}
      <div className="border-t border-border/30 pt-2">
        <p className="font-mono text-[10px] text-muted-foreground/60">
          session · {trace.session_id.slice(0, 13)}…
        </p>
      </div>
    </div>
  );
}

function EmptyTrace() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 px-4 text-center">
      <Wrench className="h-5 w-5 text-muted-foreground/40" aria-hidden />
      <h3 className="text-xs font-medium text-muted-foreground">No trace yet</h3>
      <p className="max-w-[180px] text-[11px] leading-relaxed text-muted-foreground/70">
        Send a message and the agent&apos;s tool calls + cost + iterations show up here.
      </p>
    </div>
  );
}

function LoadingTrace() {
  return (
    <div className="flex flex-col gap-3">
      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Trace · receipts
        </h3>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <Skeleton className="h-16 w-full rounded-lg" />
        <Skeleton className="h-16 w-full rounded-lg" />
        <Skeleton className="h-16 w-full rounded-lg" />
        <Skeleton className="h-16 w-full rounded-lg" />
      </div>
      <div className="space-y-1.5">
        <Skeleton className="h-7 w-full rounded-md" />
        <Skeleton className="h-7 w-full rounded-md" />
        <Skeleton className="h-7 w-full rounded-md" />
      </div>
    </div>
  );
}
