"use client";

import { Bike, User } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { MarkdownRenderer } from "@/components/markdown-renderer";
import type { UiMessage } from "@/lib/types";

interface MessageBubbleProps {
  message: UiMessage;
}

export function MessageBubble({ message }: MessageBubbleProps) {
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

      {/* Bubble */}
      <div
        className={
          isUser
            ? "max-w-[85%] rounded-2xl rounded-tr-sm bg-primary/15 px-4 py-2.5 text-foreground ring-1 ring-primary/20"
            : "min-w-0 max-w-[85%] flex-1 rounded-2xl rounded-tl-sm bg-card px-4 py-3 text-foreground ring-1 ring-border/40"
        }
      >
        {isUser ? (
          <p className="whitespace-pre-wrap text-sm leading-relaxed">{message.content}</p>
        ) : (
          <MarkdownRenderer content={message.content} />
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
  );
}
