"use client";

import { useState } from "react";
import Image from "next/image";
import { Bike, ChevronDown, User } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { MarkdownRenderer } from "@/components/markdown-renderer";
import { VisualResponse } from "@/components/visual-response";
import type { Corridor } from "@/lib/corridors";
import type { RouteVariantSummary } from "@/lib/route-variants";
import type { ToolCallSummary, UiMessage } from "@/lib/types";
import type { ViewMode } from "@/lib/view-mode";

interface MessageBubbleProps {
  message: UiMessage;
  /** When "visual", assistant messages route through `VisualResponse` */
  viewMode?: ViewMode;
  /** Conversation-scoped corridor used by visual mode for card rendering */
  corridor?: Corridor | null;
  /**
   * Fired when the user commits to a variant via the comparison card's
   * "Plan this route →" CTA. Routed up to the page-level handler that
   * dispatches a curated chat message ("Let's go with the X route…") so
   * the agent can proceed to day-by-day planning without the user typing.
   */
  onPickVariant?: (variant: RouteVariantSummary) => void;
}

/**
 * Bubble layout for a single message.
 *
 *   - User messages stay right-aligned and capped at ~640px so short
 *     prompts don't sprawl across the 1200px conversation column.
 *   - Assistant messages fill the column width so visual responses
 *     (maps, itinerary cards) get room to breathe; markdown text inside
 *     self-caps at a comfortable reading measure (~70 chars).
 */
function formatCached(n: number): string {
  if (n >= 10_000) return `${(n / 1000).toFixed(1).replace(/\.0$/, "")}k`;
  return n.toLocaleString();
}

/**
 * Per-turn footer: iter count, tool count (tappable to expand the list),
 * input + cached tokens, output tokens.
 *
 * The "tools" badge becomes a button with a rotating chevron when the
 * turn made at least one tool call. Tapping expands a panel below the
 * stats row that lists every call in invocation order with the arg keys
 * the agent passed — exactly the same trace the backend stores, just
 * surfaced inline so reviewers don't have to open the trace panel
 * separately to see what fired.
 */
function MessageMetaFooter({
  meta,
}: {
  meta: NonNullable<UiMessage["meta"]>;
}) {
  const [toolsOpen, setToolsOpen] = useState(false);
  const toolCount = meta.tool_calls.length;
  const hasTools = toolCount > 0;

  return (
    <div className="mt-3 border-t border-border/30 pt-2.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge variant="secondary" className="font-mono text-[10px]">
          {meta.iterations} iter
        </Badge>

        {/* Tools — tappable to reveal the call list, plain Badge when zero */}
        {hasTools ? (
          <button
            type="button"
            onClick={() => setToolsOpen((v) => !v)}
            aria-expanded={toolsOpen}
            aria-controls="tool-call-list"
            className={[
              "inline-flex items-center gap-1 rounded-md border-transparent bg-secondary px-2.5 py-0.5 font-mono text-[10px] font-semibold text-secondary-foreground transition-colors",
              "hover:bg-secondary/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
            ].join(" ")}
          >
            {toolCount} {toolCount === 1 ? "tool" : "tools"}
            <ChevronDown
              className={[
                "h-3 w-3 transition-transform duration-200",
                toolsOpen ? "rotate-180" : "",
              ].join(" ")}
              aria-hidden
            />
          </button>
        ) : (
          <Badge variant="secondary" className="font-mono text-[10px]">
            0 tools
          </Badge>
        )}

        <Badge
          variant="secondary"
          className="font-mono text-[10px]"
          title={
            meta.cache_read_tokens
              ? `${meta.input_tokens.toLocaleString()} newly billed input + ${(meta.cache_read_tokens ?? 0).toLocaleString()} read from prompt cache (~10% rate)`
              : undefined
          }
        >
          {meta.input_tokens.toLocaleString()} in
          {meta.cache_read_tokens
            ? ` · ${formatCached(meta.cache_read_tokens)} cached`
            : ""}
        </Badge>
        <Badge variant="secondary" className="font-mono text-[10px]">
          {meta.output_tokens.toLocaleString()} out
        </Badge>
      </div>

      {/* Expanded tool-call panel */}
      {toolsOpen && hasTools ? (
        <ToolCallList id="tool-call-list" calls={meta.tool_calls} />
      ) : null}
    </div>
  );
}

/**
 * Numbered list of every tool call the agent made this turn, in order.
 * Each row shows the tool name + the named args the agent supplied
 * (just the keys — values are in the full trace if a reviewer needs them).
 *
 * Repeated tool names are common on fan-out turns (e.g. 4× get_weather
 * for a 4-day plan). Grouping would hide the call order; listing
 * preserves it so the user can see the parallel-dispatch pattern.
 */
function ToolCallList({ id, calls }: { id: string; calls: ToolCallSummary[] }) {
  // Per-tool colour cue — keeps long lists scannable. Same hue family
  // across runs of the same tool, distinct hues across different tools.
  const colorFor = (name: string): string => {
    let hash = 0;
    for (let i = 0; i < name.length; i++) {
      hash = (hash * 31 + name.charCodeAt(i)) | 0;
    }
    const palette = [
      "bg-orange-100 text-orange-800",
      "bg-blue-100 text-blue-800",
      "bg-emerald-100 text-emerald-800",
      "bg-purple-100 text-purple-800",
      "bg-amber-100 text-amber-800",
      "bg-rose-100 text-rose-800",
      "bg-sky-100 text-sky-800",
      "bg-lime-100 text-lime-800",
    ];
    return palette[Math.abs(hash) % palette.length];
  };

  return (
    <ol
      id={id}
      className="mt-2 space-y-1 rounded-md border border-border/40 bg-muted/30 p-2 font-mono text-[11px]"
    >
      {calls.map((call, i) => {
        const args = call.args && call.args.length > 0 ? call.args.join(", ") : "";
        return (
          <li
            key={`${call.name}-${i}`}
            className="flex items-baseline gap-2 leading-tight"
          >
            <span className="w-5 shrink-0 text-right text-muted-foreground/70">
              {i + 1}
            </span>
            <span
              className={[
                "rounded px-1.5 py-0.5 text-[10px] font-semibold",
                colorFor(call.name),
              ].join(" ")}
            >
              {call.name}
            </span>
            {args ? (
              <span className="text-muted-foreground">({args})</span>
            ) : (
              <span className="text-muted-foreground/50">()</span>
            )}
          </li>
        );
      })}
    </ol>
  );
}

export function MessageBubble({
  message,
  viewMode = "text",
  corridor = null,
  onPickVariant,
}: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : "flex-row"}`}>
      {/* Avatar */}
      <div
        className={
          isUser
            ? "flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/15 text-primary ring-1 ring-primary/20"
            : "flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-card text-foreground/80 ring-1 ring-border/40"
        }
      >
        {isUser ? <User className="h-4 w-4" aria-hidden /> : <Bike className="h-4 w-4" aria-hidden />}
      </div>

      <div
        className={
          isUser
            ? "flex min-w-0 max-w-[640px] flex-col items-end"
            : "min-w-0 flex-1"
        }
      >
        {/* Bubble */}
        <div
          className={
            isUser
              ? "rounded-2xl rounded-tr-sm bg-primary/15 px-4 py-2.5 text-foreground ring-1 ring-primary/20"
              : "min-w-0 rounded-2xl rounded-tl-sm bg-card px-5 py-4 text-foreground ring-1 ring-border/40"
          }
        >
          {isUser ? (
            <>
              {message.imageDataUrl ? (
                <div className="mb-2 overflow-hidden rounded-lg ring-1 ring-border/30">
                  <Image
                    src={message.imageDataUrl}
                    alt="Attached"
                    width={400}
                    height={300}
                    className="h-auto w-full object-cover"
                    unoptimized
                  />
                </div>
              ) : null}
              {message.content ? (
                <p className="whitespace-pre-wrap text-sm leading-relaxed">{message.content}</p>
              ) : null}
            </>
          ) : viewMode === "visual" ? (
            <VisualResponse
              content={message.content}
              corridor={corridor}
              onPickVariant={onPickVariant}
            />
          ) : (
            // Cap markdown text at a comfortable reading measure within
            // the wide bubble. Visual responses ignore this and fill width.
            <div className="max-w-[72ch]">
              <MarkdownRenderer content={message.content} />
            </div>
          )}

          {/* Per-turn meta for assistant messages */}
          {!isUser && message.meta ? (
            <MessageMetaFooter meta={message.meta} />
          ) : null}
        </div>
      </div>
    </div>
  );
}
