"use client";

import { useEffect, useMemo, useState } from "react";
import type { TraceEvent, TraceResponse } from "@/lib/types";

/**
 * Persistent dark trace panel — the single home for "what the agent is
 * doing" on this page. Replaces the previous right-rail TracePanel +
 * StatCard 2x2 grid; lives at the same screen position throughout the
 * user's journey so context never moves.
 *
 * Two modes, picked by the parent based on whether a real session exists:
 *
 *   - `mode="demo"`   — looped fake timeline (used on the empty state).
 *                       Demonstrates what the agent does without forcing
 *                       the user to interact first.
 *
 *   - `mode="live"`   — real session data: session_id, iterations count,
 *                       tool-call list with latencies, total tokens, cost.
 *                       Updates every time the parent passes a fresh
 *                       trace prop.
 */

interface DemoEvent {
  ts: string;
  tool?: string;
  args?: string;
  latency?: number;
  text?: string;
  type?: "user" | "thinking";
}

const DEMO_TIMELINE: DemoEvent[] = [
  { ts: "0.0s", text: 'User: "plan London → Paris, 100km/day, June"', type: "user" },
  { ts: "0.4s", tool: "get_route", args: 'start="london" end="paris"', latency: 245 },
  { ts: "0.7s", tool: "get_elevation_profile", args: "×4 segments", latency: 180 },
  { ts: "1.2s", tool: "get_weather", args: "london, june", latency: 312 },
  { ts: "1.8s", tool: "find_accommodation", args: "×4 cities", latency: 220 },
  { ts: "2.4s", tool: "critique_trip_plan", args: "self-review", latency: 95 },
  { ts: "2.5s", text: "agent shipping plan…", type: "thinking" },
];

interface LiveTracePanelProps {
  mode: "demo" | "live";
  /** Real session id (live mode only). Trimmed for display. */
  sessionId?: string | null;
  /** Real trace data from /trace/{session_id}. */
  trace?: TraceResponse | null;
  /** Whether a turn is currently in flight — drives the pulsing dot + cursor. */
  isPending?: boolean;
}

export function LiveTracePanel({
  mode,
  sessionId,
  trace,
  isPending,
}: LiveTracePanelProps) {
  if (mode === "demo") return <DemoTrace />;
  return (
    <RealTrace
      sessionId={sessionId ?? null}
      trace={trace ?? null}
      isPending={Boolean(isPending)}
    />
  );
}

// ---------------------------------------------------------------------------
// DemoTrace — looped fake timeline used on the empty state
// ---------------------------------------------------------------------------

function DemoTrace() {
  const [step, setStep] = useState(0);
  const [stats, setStats] = useState({ tools: 0, tokens: 0, cost: "0.000" });

  useEffect(() => {
    if (step < DEMO_TIMELINE.length - 1) {
      const id = setTimeout(
        () => {
          const next = step + 1;
          setStep(next);
          const completed = DEMO_TIMELINE.slice(0, next + 1).filter(
            (e) => e.tool,
          ).length;
          setStats({
            tools: completed,
            tokens: Math.round((next + 1) * 1850 + Math.random() * 300),
            cost: ((next + 1) * 0.012).toFixed(3),
          });
        },
        step === 0 ? 800 : 700,
      );
      return () => clearTimeout(id);
    }
    // Restart loop after a pause
    const id = setTimeout(() => {
      setStep(0);
      setStats({ tools: 0, tokens: 0, cost: "0.000" });
    }, 4500);
    return () => clearTimeout(id);
  }, [step]);

  const visible = DEMO_TIMELINE.slice(0, step + 1);
  const isFinalThinking =
    visible[visible.length - 1]?.type === "thinking" &&
    step === DEMO_TIMELINE.length - 1;

  return (
    <PanelShell sessionId="demo · 5cafa236" pulse>
      <div className="relative mb-4 min-h-[140px] font-mono text-[12px] leading-[1.7] text-white/85">
        {visible.map((e, i) => (
          <div
            key={`${step}-${i}`}
            className="flex items-baseline gap-2.5 opacity-0"
            style={{ animation: "traceIn 0.5s forwards" }}
          >
            <span className="w-9 shrink-0 text-[10px] text-white/30">
              {e.ts}
            </span>
            {e.tool ? (
              <ToolLine
                tool={e.tool}
                args={e.args ?? ""}
                latency={e.latency}
                done={i < visible.length - 1}
              />
            ) : (
              <span className={e.type === "user" ? "text-white/60" : "text-white"}>
                {e.text}
                {isFinalThinking && i === visible.length - 1 && (
                  <span className="ml-1 inline-block animate-pulse text-primary" aria-hidden>
                    ▌
                  </span>
                )}
              </span>
            )}
          </div>
        ))}
      </div>
      <StatTrio
        toolCalls={stats.tools}
        tokens={stats.tokens}
        cost={`$${stats.cost}`}
      />
      <KeyframesStyle />
    </PanelShell>
  );
}

// ---------------------------------------------------------------------------
// RealTrace — live session data
// ---------------------------------------------------------------------------

function RealTrace({
  sessionId,
  trace,
  isPending,
}: {
  sessionId: string | null;
  trace: TraceResponse | null;
  isPending: boolean;
}) {
  // Derive a flat tool-call summary list from the trace events. Pair
  // each `tool_use` with its `tool_result` so we can show name + latency.
  const toolCalls = useMemo(() => {
    if (!trace) return [] as { name: string; latency: number; isError: boolean; iter: number }[];
    const useEvents = new Map<string, TraceEvent>();
    const out: { name: string; latency: number; isError: boolean; iter: number }[] = [];
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
          iter: useE.iteration ?? 0,
        });
      }
    }
    return out;
  }, [trace]);

  const totalTokens = trace
    ? trace.total_input_tokens + trace.total_output_tokens
    : 0;

  const sessionLabel = sessionId
    ? `live · ${sessionId.slice(0, 8)}`
    : "live · new";

  return (
    <PanelShell sessionId={sessionLabel} pulse={isPending}>
      <div className="relative mb-4 min-h-[140px] font-mono text-[12px] leading-[1.7] text-white/85">
        {toolCalls.length === 0 ? (
          <div className="flex h-full min-h-[140px] flex-col items-start justify-center gap-2 text-white/40">
            <div className="text-[11px]">
              {isPending
                ? "agent thinking…"
                : "Send a message — tool calls stream here in real time."}
            </div>
            {isPending && (
              <div className="text-primary">
                <span className="animate-pulse">▌</span>
              </div>
            )}
          </div>
        ) : (
          <div className="max-h-[180px] overflow-y-auto pr-1">
            {toolCalls.map((c, i) => (
              <div key={i} className="flex items-baseline gap-2.5">
                <span className="w-9 shrink-0 text-[10px] text-white/30">
                  i{c.iter}
                </span>
                <ToolLine
                  tool={c.name}
                  args=""
                  latency={c.latency}
                  done
                  error={c.isError}
                />
              </div>
            ))}
          </div>
        )}
      </div>
      <StatTrio
        toolCalls={toolCalls.length}
        tokens={totalTokens}
        cost={trace ? `$${trace.estimated_cost_usd.toFixed(4)}` : "$0.0000"}
      />
      <KeyframesStyle />
    </PanelShell>
  );
}

// ---------------------------------------------------------------------------
// Shared shell + sub-pieces
// ---------------------------------------------------------------------------

function PanelShell({
  sessionId,
  pulse,
  children,
}: {
  sessionId: string;
  pulse: boolean;
  children: React.ReactNode;
}) {
  return (
    <div
      className="relative flex flex-col overflow-hidden rounded-2xl bg-[#0A0A09] p-5 text-white shadow-[0_20px_50px_-20px_rgba(10,10,9,0.4)]"
      style={{
        backgroundImage:
          "radial-gradient(circle at 100% 0%, rgba(255,61,20,0.18), transparent 50%), radial-gradient(circle at 0% 100%, rgba(255,61,20,0.08), transparent 50%)",
      }}
    >
      <div className="relative mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2 font-mono text-[10.5px] font-medium uppercase tracking-[0.08em] text-white/55">
          <span className="relative flex h-1.5 w-1.5">
            {pulse && (
              <span className="absolute inset-0 animate-ping rounded-full bg-primary opacity-75" />
            )}
            <span className="relative h-1.5 w-1.5 rounded-full bg-primary" />
          </span>
          {sessionId}
          <span className="text-white/30">·</span>
          <span>/chat/stream</span>
        </div>
      </div>
      {children}
    </div>
  );
}

function ToolLine({
  tool,
  args,
  latency,
  done,
  error = false,
}: {
  tool: string;
  args: string;
  latency?: number;
  done: boolean;
  error?: boolean;
}) {
  return (
    <>
      <span className="shrink-0 text-primary">→</span>
      <span className="font-semibold text-white">{tool}</span>
      {args && <span className="text-[11px] text-white/45">({args})</span>}
      {done && (
        <span className={error ? "text-[#FF6B3D]" : "text-[#18A957]"}>
          {error ? "✗" : "✓"}
        </span>
      )}
      {latency != null && (
        <span className="ml-auto text-[10px] text-white/35">{latency}ms</span>
      )}
    </>
  );
}

function StatTrio({
  toolCalls,
  tokens,
  cost,
}: {
  toolCalls: number;
  tokens: number;
  cost: string;
}) {
  return (
    <div className="relative grid grid-cols-3 overflow-hidden rounded-xl border border-white/[0.08] bg-white/[0.03]">
      <Stat label="Tool calls" value={toolCalls.toString()} accent />
      <Stat label="Tokens" value={tokens.toLocaleString()} divider />
      <Stat label="Cost" value={cost} divider />
    </div>
  );
}

function Stat({
  label,
  value,
  accent = false,
  divider = false,
}: {
  label: string;
  value: string;
  accent?: boolean;
  divider?: boolean;
}) {
  return (
    <div
      className={[
        "px-3 py-2.5",
        divider && "border-l border-white/[0.06]",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <div className="font-mono text-[9px] font-medium uppercase tracking-[0.06em] text-white/40">
        {label}
      </div>
      <div
        className={[
          "mt-0.5 text-[18px] font-bold tracking-[-0.02em] tabular-nums",
          accent ? "text-primary" : "text-white",
        ].join(" ")}
      >
        {value}
      </div>
    </div>
  );
}

function KeyframesStyle() {
  return (
    <style jsx>{`
      @keyframes traceIn {
        from {
          opacity: 0;
          transform: translateX(-8px);
        }
        to {
          opacity: 1;
          transform: translateX(0);
        }
      }
    `}</style>
  );
}
