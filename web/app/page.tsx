"use client";

import { useCallback, useEffect, useMemo, useRef, useState, useTransition } from "react";
import { Header } from "@/components/header";
import { MessageBubble } from "@/components/message-bubble";
import { LoadingIndicator } from "@/components/loading-indicator";
import { ChatInput } from "@/components/chat-input";
import { TracePanel } from "@/components/trace-panel";
import { ApiError, getTrace, postChat } from "@/lib/api";
import { matchCorridor } from "@/lib/corridors";
import type { PreparedImage } from "@/lib/image";
import { clearSessionId, loadSessionId, saveSessionId } from "@/lib/session";
import type { TraceResponse, UiMessage } from "@/lib/types";

function makeId(): string {
  // Quick-and-light unique id for React keys; not the backend session_id.
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

export default function Home() {
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [trace, setTrace] = useState<TraceResponse | null>(null);
  const [isTraceLoading, setIsTraceLoading] = useState(false);
  const [attachedImage, setAttachedImage] = useState<PreparedImage | null>(null);

  const scrollAnchorRef = useRef<HTMLDivElement>(null);

  // Restore session_id from localStorage on mount so a refresh continues the
  // conversation. We don't re-fetch the message thread — backend has it,
  // and a fresh page legitimately starts with an empty UI.
  //
  // ESLint's `react-hooks/set-state-in-effect` warns on setState-from-effect
  // even for legitimate "hydrate from external store" cases like localStorage.
  // The alternative (useSyncExternalStore) is heavier than warranted here,
  // and the brief flicker (badge shows "new" then the real id) is acceptable.
  useEffect(() => {
    const stored = loadSessionId();
    if (stored) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSessionId(stored);
    }
  }, []);

  // Auto-scroll to the latest message when the thread or pending state changes.
  useEffect(() => {
    scrollAnchorRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, isPending]);

  const handleReset = useCallback(() => {
    clearSessionId();
    setSessionId(null);
    setMessages([]);
    setError(null);
    setTrace(null);
  }, []);

  // Fetch the trace for the current session whenever a turn settles. Kept as
  // a separate function (not a hook) so we can call it imperatively from
  // handleSubmit's transition without re-creating dependencies.
  const refreshTrace = useCallback(async (id: string) => {
    setIsTraceLoading(true);
    try {
      const data = await getTrace(id);
      setTrace(data);
    } catch {
      // Trace fetch failures are non-fatal — leave the existing panel as-is.
    } finally {
      setIsTraceLoading(false);
    }
  }, []);

  const handleSubmit = useCallback(() => {
    const text = input.trim();
    // Allow send when there's text OR an image (both are valid turns).
    if ((!text && !attachedImage) || isPending) return;

    const userMessage: UiMessage = {
      id: makeId(),
      role: "user",
      content: text,
      imageDataUrl: attachedImage?.dataUrl,
    };

    // Snapshot the attached image so we can clear UI state immediately and
    // still send it inside the transition.
    const imageForRequest = attachedImage;

    // Optimistic append + clear input. Functional setState keeps callbacks stable.
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setAttachedImage(null);
    setError(null);

    // useTransition keeps the input UI responsive during the in-flight call.
    startTransition(async () => {
      try {
        const res = await postChat({
          message: text || "Plan this trip from the attached image.",
          session_id: sessionId ?? undefined,
          image: imageForRequest?.payload,
        });

        if (res.session_id !== sessionId) {
          saveSessionId(res.session_id);
          setSessionId(res.session_id);
        }

        const assistantMessage: UiMessage = {
          id: makeId(),
          role: "assistant",
          content: res.message,
          meta: {
            iterations: res.iterations,
            input_tokens: res.input_tokens,
            output_tokens: res.output_tokens,
            tool_calls: res.tool_calls,
          },
        };
        setMessages((prev) => [...prev, assistantMessage]);

        // Fire-and-forget — don't block the UI on the trace fetch.
        void refreshTrace(res.session_id);
      } catch (err) {
        const fallback = "Something went wrong talking to the agent.";
        if (err instanceof ApiError) {
          setError(`${fallback} (${err.status} ${err.message})`);
        } else if (err instanceof Error) {
          setError(`${fallback} ${err.message}`);
        } else {
          setError(fallback);
        }
      }
    });
  }, [input, isPending, sessionId, attachedImage, refreshTrace]);

  // If a session was restored from localStorage on mount, fetch its trace
  // so the panel reflects state from before the page reload. refreshTrace
  // calls setState internally — that's the legitimate "hydrate from external"
  // pattern, same justification as the localStorage restore above.
  useEffect(() => {
    if (sessionId && !trace) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      void refreshTrace(sessionId);
    }
    // We intentionally only run this when sessionId becomes truthy after mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  const isEmpty = messages.length === 0 && !isPending;
  const canSend = input.trim().length > 0 || attachedImage !== null;

  // Detect which corridor the conversation is about by scanning messages
  // (most recent first) for any of the known route aliases. Cheap pure
  // function, derived state — no effect needed.
  const corridor = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      const m = matchCorridor(messages[i].content);
      if (m) return m;
    }
    return null;
  }, [messages]);

  return (
    <div className="flex h-dvh flex-col bg-background">
      <Header sessionId={sessionId} onReset={handleReset} />

      <main className="flex-1 overflow-hidden">
        <div className="mx-auto flex h-full max-w-7xl">
          {/* Chat column — full width on mobile, ~7/10ths on desktop */}
          <div className="flex flex-1 flex-col overflow-hidden">
            <div className="flex-1 overflow-y-auto px-4 py-6">
              {isEmpty ? (
                <EmptyState />
              ) : (
                <div className="space-y-5">
                  {messages.map((m) => (
                    <MessageBubble key={m.id} message={m} />
                  ))}
                  {isPending ? <LoadingIndicator /> : null}
                  {error ? (
                    <div className="rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                      {error}
                    </div>
                  ) : null}
                  <div ref={scrollAnchorRef} />
                </div>
              )}
            </div>
          </div>

          {/* Trace panel — hidden on mobile, ~3/10ths on lg+ */}
          <aside className="hidden w-[360px] shrink-0 overflow-y-auto border-l border-border/40 bg-card/30 p-4 lg:block">
            <TracePanel
              trace={trace}
              isLoading={isTraceLoading || isPending}
              hasSession={Boolean(sessionId)}
              corridor={corridor}
            />
          </aside>
        </div>
      </main>

      <ChatInput
        value={input}
        onChange={setInput}
        onSubmit={handleSubmit}
        disabled={!canSend}
        isPending={isPending}
        attachedImage={attachedImage}
        onAttachImage={setAttachedImage}
      />
    </div>
  );
}

/* Defined at module level (not inside Home) to keep a stable function
   reference across renders — see `rerender-no-inline-components`. */
function EmptyState() {
  return (
    <div className="mx-auto flex h-full max-w-2xl flex-col items-center justify-center text-center">
      <div className="mb-5 rounded-full bg-primary/15 p-4 ring-1 ring-primary/20">
        <span className="text-3xl" aria-hidden>
          🚲
        </span>
      </div>
      <h2 className="mb-2 text-xl font-semibold tracking-tight text-foreground">
        Plan a multi-day cycling trip
      </h2>
      <p className="max-w-md text-sm leading-relaxed text-muted-foreground">
        Tell me where you&apos;re riding, how far per day, what time of year, and your accommodation
        preferences. I&apos;ll build you a day-by-day plan with route, terrain, weather, and
        accommodation.
      </p>
      <p className="mt-4 text-xs text-muted-foreground/70">
        Try one of the suggestions below to get started.
      </p>
    </div>
  );
}
