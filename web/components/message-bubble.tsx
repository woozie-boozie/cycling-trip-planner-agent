"use client";

import Image from "next/image";
import { Bike, User } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { MarkdownRenderer } from "@/components/markdown-renderer";
import { VisualResponse } from "@/components/visual-response";
import type { Corridor } from "@/lib/corridors";
import type { UiMessage } from "@/lib/types";
import type { ViewMode } from "@/lib/view-mode";

interface MessageBubbleProps {
  message: UiMessage;
  /** When "visual", assistant messages route through `VisualResponse` */
  viewMode?: ViewMode;
  /** Conversation-scoped corridor used by visual mode for card rendering */
  corridor?: Corridor | null;
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
export function MessageBubble({ message, viewMode = "text", corridor = null }: MessageBubbleProps) {
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
            <VisualResponse content={message.content} corridor={corridor} />
          ) : (
            // Cap markdown text at a comfortable reading measure within
            // the wide bubble. Visual responses ignore this and fill width.
            <div className="max-w-[72ch]">
              <MarkdownRenderer content={message.content} />
            </div>
          )}

          {/* Per-turn meta for assistant messages */}
          {!isUser && message.meta ? (
            <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-border/30 pt-2.5">
              <Badge variant="secondary" className="font-mono text-[10px]">
                {message.meta.iterations} iter
              </Badge>
              <Badge variant="secondary" className="font-mono text-[10px]">
                {message.meta.tool_calls.length} tools
              </Badge>
              <Badge variant="secondary" className="font-mono text-[10px]">
                {message.meta.input_tokens.toLocaleString()} in
              </Badge>
              <Badge variant="secondary" className="font-mono text-[10px]">
                {message.meta.output_tokens.toLocaleString()} out
              </Badge>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
