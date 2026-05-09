"use client";

import { useEffect, useRef } from "react";
import { Send, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  disabled: boolean;
  isPending: boolean;
}

const SUGGESTIONS = [
  "Plan a 4-day cycle from London to Paris on the Avenue Verte, 100km/day, prefer camping but a hostel every 3rd night, traveling in June.",
  "Plan a London to Brighton ride for Saturday June 14, 100km/day, hostel both nights.",
  "I want to cycle from Amsterdam to Copenhagen, ~100km a day, prefer camping but a hostel every 4th night, June.",
];

export function ChatInput({ value, onChange, onSubmit, disabled, isPending }: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-focus on mount and when not pending so the user can keep typing.
  useEffect(() => {
    if (!isPending) {
      textareaRef.current?.focus();
    }
  }, [isPending]);

  // Auto-grow the textarea up to a sensible cap.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [value]);

  const showSuggestions = value.length === 0 && !isPending;

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    // Enter sends, Shift+Enter inserts newline.
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (!disabled) onSubmit();
    }
  }

  return (
    <div className="border-t border-border/40 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
      <div className="mx-auto max-w-5xl px-4 py-4">
        {showSuggestions ? (
          <div className="mb-3 flex flex-wrap gap-2">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => onChange(s)}
                className="rounded-full border border-border/40 bg-card/50 px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:bg-card hover:text-foreground"
              >
                {s.slice(0, 60)}…
              </button>
            ))}
          </div>
        ) : null}

        <div className="flex items-end gap-2 rounded-2xl border border-border/50 bg-card/40 p-2 focus-within:border-primary/40 focus-within:ring-1 focus-within:ring-primary/30">
          <Textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask me to plan a multi-day cycling trip…"
            disabled={isPending}
            rows={1}
            className="min-h-0 resize-none border-0 bg-transparent px-2 py-1.5 text-sm shadow-none focus-visible:ring-0"
          />
          <Button
            type="button"
            size="icon"
            onClick={onSubmit}
            disabled={disabled || isPending}
            className="h-9 w-9 shrink-0"
          >
            {isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
            ) : (
              <Send className="h-4 w-4" aria-hidden />
            )}
            <span className="sr-only">Send</span>
          </Button>
        </div>

        <p className="mt-2 text-center text-[11px] text-muted-foreground/70">
          Enter sends · Shift+Enter for a new line
        </p>
      </div>
    </div>
  );
}
