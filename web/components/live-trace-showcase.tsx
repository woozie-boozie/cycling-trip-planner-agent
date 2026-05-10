"use client";

import { useEffect, useState } from "react";

/**
 * Decorative dark "live trace" card that lives in the empty-state hero.
 *
 * Animates a fake `/chat/stream` SSE timeline so the page demonstrates
 * what the agent does without requiring an actual session. Loops every
 * ~6 seconds. The styling mirrors the kind of receipts a developer
 * would see in a real session — same tool names, same latency shape —
 * just played as an ambient ad for the system's depth.
 *
 * Once the user sends a real message the conversation takes over, so
 * this component only renders on the empty state. The right-rail trace
 * panel handles real session data.
 */

interface TraceEvent {
  ts: string;
  /** When `tool` is set, the line renders as a tool-call pill. */
  tool?: string;
  args?: string;
  latency?: number;
  /** When `text` is set, the line renders as user/assistant prose. */
  text?: string;
  type?: "user" | "thinking";
}

const TIMELINE: TraceEvent[] = [
  { ts: "0.0s", text: 'User: "plan London → Paris, 100km/day, June"', type: "user" },
  { ts: "0.4s", tool: "get_route", args: 'start="london" end="paris"', latency: 245 },
  { ts: "0.7s", tool: "get_elevation_profile", args: "×4 segments", latency: 180 },
  { ts: "1.2s", tool: "get_weather", args: "london, june", latency: 312 },
  { ts: "1.8s", tool: "find_accommodation", args: "×4 cities", latency: 220 },
  { ts: "2.4s", tool: "critique_trip_plan", args: "self-review", latency: 95 },
  { ts: "2.5s", text: "agent shipping plan…", type: "thinking" },
];

export function LiveTraceShowcase() {
  const [step, setStep] = useState(0);
  const [stats, setStats] = useState({ tools: 0, tokens: 0, cost: "0.000" });

  useEffect(() => {
    if (step < TIMELINE.length - 1) {
      const id = setTimeout(
        () => {
          const next = step + 1;
          setStep(next);
          const completedTools = TIMELINE.slice(0, next + 1).filter(
            (e) => e.tool,
          ).length;
          setStats({
            tools: completedTools,
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

  const visible = TIMELINE.slice(0, step + 1);
  const isFinalThinking =
    visible[visible.length - 1]?.type === "thinking" &&
    step === TIMELINE.length - 1;

  return (
    <div
      className="relative flex flex-col overflow-hidden rounded-2xl bg-[#0A0A09] p-5 text-white shadow-[0_20px_50px_-20px_rgba(10,10,9,0.4)]"
      // Decorative top-right + bottom-left orange radials = warm ambient
      // light without competing for attention with content.
      style={{
        backgroundImage:
          "radial-gradient(circle at 100% 0%, rgba(255,61,20,0.18), transparent 50%), radial-gradient(circle at 0% 100%, rgba(255,61,20,0.08), transparent 50%)",
      }}
    >
      {/* Header — LIVE · /chat/stream + session id */}
      <div className="relative mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2 font-mono text-[10.5px] font-medium uppercase tracking-[0.08em] text-white/55">
          <span className="relative flex h-1.5 w-1.5">
            <span className="absolute inset-0 animate-ping rounded-full bg-primary opacity-75" />
            <span className="relative h-1.5 w-1.5 rounded-full bg-primary" />
          </span>
          live · /chat/stream
        </div>
        <span className="font-mono text-[10px] text-white/40">
          5cafa236-d150
        </span>
      </div>

      {/* Stream — fixed minimum height so the card doesn't jump as lines stream */}
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
              <>
                <span className="shrink-0 text-primary">→</span>
                <span className="font-semibold text-white">{e.tool}</span>
                <span className="text-[11px] text-white/45">({e.args})</span>
                {i < visible.length - 1 && (
                  <span className="text-[#18A957]">✓</span>
                )}
                <span className="ml-auto text-[10px] text-white/35">
                  {e.latency}ms
                </span>
              </>
            ) : (
              <span
                className={
                  e.type === "user"
                    ? "text-white/60"
                    : "text-white"
                }
              >
                {e.text}
                {isFinalThinking && i === visible.length - 1 && (
                  <span
                    className="ml-1 inline-block animate-pulse text-primary"
                    aria-hidden
                  >
                    ▌
                  </span>
                )}
              </span>
            )}
          </div>
        ))}
      </div>

      {/* Stat trio */}
      <div className="relative grid grid-cols-3 overflow-hidden rounded-xl border border-white/[0.08] bg-white/[0.03]">
        <Stat label="Tool calls" value={stats.tools.toString()} accent />
        <Stat
          label="Tokens"
          value={stats.tokens.toLocaleString()}
          divider
        />
        <Stat label="Cost" value={`$${stats.cost}`} divider />
      </div>

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
