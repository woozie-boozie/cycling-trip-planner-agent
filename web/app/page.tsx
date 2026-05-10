"use client";

import { useCallback, useEffect, useMemo, useRef, useState, useTransition } from "react";
import { Header } from "@/components/header";
import { MessageBubble } from "@/components/message-bubble";
import { LoadingIndicator } from "@/components/loading-indicator";
import { ChatInput } from "@/components/chat-input";
import { OnboardingWizard } from "@/components/onboarding/wizard";
import { RouteGallery } from "@/components/route-gallery";
import { ApiError, getProfile, getTrace, postChat, postChatStream } from "@/lib/api";
import { matchCorridor } from "@/lib/corridors";
import type { PreparedImage } from "@/lib/image";
import {
  clearProfileId,
  clearWizardDismissed,
  loadProfileId,
  loadWizardDismissed,
  saveProfileId,
  saveWizardDismissed,
} from "@/lib/profile";
import { clearSessionId, loadSessionId, saveSessionId } from "@/lib/session";
import type { TraceResponse, UiMessage, UserProfile } from "@/lib/types";
import { useViewMode } from "@/lib/view-mode";

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
  const [attachedImage, setAttachedImage] = useState<PreparedImage | null>(null);
  const [profileId, setProfileId] = useState<string | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [wizardOpen, setWizardOpen] = useState(false);

  // Visual ⇄ text view-mode toggle (Phase A · v2 redesign).
  const { mode: viewMode, toggle: toggleViewMode } = useViewMode();

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

  // Hydrate profile_id from localStorage on mount. If absent AND the user
  // hasn't explicitly dismissed the wizard, open it. Same "hydrate from
  // external store" pattern as the session_id restore above.
  useEffect(() => {
    const stored = loadProfileId();
    if (stored) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setProfileId(stored);
    } else if (!loadWizardDismissed()) {
      setWizardOpen(true);
    }
  }, []);

  // When profileId becomes truthy, fetch the canonical profile so we can
  // render the personalised greeting. 404 = stale id (server lost it);
  // clear it and let the wizard re-prompt next time.
  useEffect(() => {
    if (!profileId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setProfile(null);
      return;
    }
    let aborted = false;
    void (async () => {
      try {
        const p = await getProfile(profileId);
        if (!aborted) {
          setProfile(p);
        }
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          clearProfileId();
          if (!aborted) setProfileId(null);
        }
      }
    })();
    return () => {
      aborted = true;
    };
  }, [profileId]);

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
  //
  // A /trace 404 is BENIGN — it can fire when the streaming session-preamble
  // event lands before the backend has persisted state mid-stream. In that
  // case the session is real and in-flight; clearing the id would orphan
  // the next turn into a fresh session and look like amnesia. Only /chat
  // 404 is a real "session lost" signal; that's handled in handleSubmit.
  const refreshTrace = useCallback(async (id: string) => {
    try {
      const data = await getTrace(id);
      setTrace(data);
    } catch (err) {
      // Don't clear sessionId on 404 here — see comment above. Trace will
      // refresh on the next turn's `done` event.
      if (err instanceof ApiError && err.status === 404) {
        // benign — leave sessionId + trace alone
      }
    }
  }, []);

  const handleSubmit = useCallback((textOverride?: string) => {
    // Accept an optional override so callers (e.g. the route gallery) can
    // dispatch a curated prompt without first round-tripping through the
    // textarea state. When no override is passed, use the textarea value.
    const text = (textOverride ?? input).trim();
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

    // Streaming is opt-in via NEXT_PUBLIC_STREAMING; non-streaming path stays
    // intact for environments without a streaming backend (e.g. some preview
    // deploys or older Cloud Run revisions).
    const useStreaming = process.env.NEXT_PUBLIC_STREAMING === "true";

    // useTransition keeps the input UI responsive during the in-flight call.
    startTransition(async () => {
      try {
        const messageText = text || "Plan this trip from the attached image.";

        if (useStreaming) {
          await runStreamingTurn(messageText, imageForRequest);
        } else {
          await runSynchronousTurn(messageText, imageForRequest);
        }
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

    async function runSynchronousTurn(messageText: string, image: PreparedImage | null) {
      let res;
      try {
        res = await postChat({
          message: messageText,
          session_id: sessionId ?? undefined,
          image: image?.payload,
          profile_id: profileId ?? undefined,
        });
      } catch (firstErr) {
        // Session expired on the backend (e.g. process restart wiped the
        // in-memory store). Drop the stale session_id and retry once.
        if (firstErr instanceof ApiError && firstErr.status === 404 && sessionId) {
          clearSessionId();
          setSessionId(null);
          setTrace(null);
          res = await postChat({
            message: messageText,
            image: image?.payload,
            profile_id: profileId ?? undefined,
          });
        } else {
          throw firstErr;
        }
      }

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
          cache_read_tokens: res.cache_read_tokens,
          cache_creation_tokens: res.cache_creation_tokens,
          tool_calls: res.tool_calls,
        },
      };
      setMessages((prev) => [...prev, assistantMessage]);
      void refreshTrace(res.session_id);
    }

    async function runStreamingTurn(
      messageText: string,
      image: PreparedImage | null,
    ) {
      // Optimistic empty assistant bubble — text deltas append into it live.
      const assistantId = makeId();
      const liveTextRef = { current: "" };
      const liveToolCalls: { name: string; args: string[] }[] = [];
      let iterations = 0;
      let inputTokens = 0;
      let outputTokens = 0;
      let cacheReadTokens = 0;
      let cacheCreationTokens = 0;

      setMessages((prev) => [
        ...prev,
        { id: assistantId, role: "assistant", content: "" },
      ]);

      // Stream call factory so we can retry once on a stale-session 404.
      // Mirror of the runSynchronousTurn 404-retry path: the in-memory
      // session store gets wiped on uvicorn restart, leaving the client
      // holding a stale session_id in localStorage. Clear and retry as
      // a fresh session — the user's first turn just becomes the seed
      // turn of the new session.
      const dispatch = (sid: string | null) =>
        postChatStream(
          {
            message: messageText,
            session_id: sid ?? undefined,
            image: image?.payload,
            profile_id: profileId ?? undefined,
          },
          handleEvent,
        );

      function handleEvent(event: Parameters<Parameters<typeof postChatStream>[1]>[0]) {
        switch (event.type) {
            case "session":
              if (event.session_id !== sessionId) {
                saveSessionId(event.session_id);
                setSessionId(event.session_id);
              }
              break;
            case "text_delta":
              liveTextRef.current += event.text;
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId ? { ...m, content: liveTextRef.current } : m,
                ),
              );
              break;
            case "tool_use_complete":
              liveToolCalls.push({
                name: event.name,
                args: Object.keys(event.input ?? {}),
              });
              // Push a "running" pill for the inline trace strip — flips
              // to "done" or "error" when the matching tool_result arrives.
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? {
                        ...m,
                        liveTrace: [
                          ...(m.liveTrace ?? []),
                          {
                            toolUseId: event.id,
                            name: event.name,
                            status: "running",
                            argKeys: Object.keys(event.input ?? {}),
                          },
                        ],
                      }
                    : m,
                ),
              );
              break;
            case "tool_result":
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? {
                        ...m,
                        liveTrace: (m.liveTrace ?? []).map((t) =>
                          t.toolUseId === event.id
                            ? {
                                ...t,
                                status: event.is_error ? "error" : "done",
                                latencyMs: event.latency_ms,
                              }
                            : t,
                        ),
                      }
                    : m,
                ),
              );
              break;
            case "iteration_end":
              iterations = event.iteration;
              break;
            case "done":
              inputTokens = event.input_tokens;
              outputTokens = event.output_tokens;
              cacheReadTokens = event.cache_read_tokens ?? 0;
              cacheCreationTokens = event.cache_creation_tokens ?? 0;
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? {
                        ...m,
                        meta: {
                          iterations: iterations || event.iterations,
                          input_tokens: inputTokens,
                          output_tokens: outputTokens,
                          cache_read_tokens: cacheReadTokens,
                          cache_creation_tokens: cacheCreationTokens,
                          tool_calls: event.tool_calls.length
                            ? event.tool_calls
                            : liveToolCalls,
                        },
                      }
                    : m,
                ),
              );
              void refreshTrace(event.session_id);
              break;
            case "error": {
              // Mid-stream error from backend (rate-limit, timeout, etc.).
              // Surface a user-friendly message with a kind-specific hint
              // and drop the empty assistant bubble so the thread doesn't
              // show a hanging "" reply.
              const hint =
                event.kind === "rate_limit"
                  ? " Tip: click \"+ New trip\" to start fresh and shrink the context."
                  : "";
              setError(`${event.message}${hint}`);
              setMessages((prev) =>
                prev.filter((m) => !(m.id === assistantId && !m.content)),
              );
              break;
            }
        }
      }

      try {
        await dispatch(sessionId);
      } catch (firstErr) {
        if (firstErr instanceof ApiError && firstErr.status === 404 && sessionId) {
          // Stale session_id (uvicorn restart wiped the in-memory store).
          // Clear it and retry as a fresh session — same recovery as the
          // synchronous path, just on the streaming flow.
          clearSessionId();
          setSessionId(null);
          setTrace(null);
          // Reset the optimistic assistant bubble so the retry's text_delta
          // events accumulate from empty rather than appending to a leftover.
          liveTextRef.current = "";
          setMessages((prev) =>
            prev.map((m) => (m.id === assistantId ? { ...m, content: "" } : m)),
          );
          await dispatch(null);
        } else {
          throw firstErr;
        }
      }
    }
  }, [input, isPending, sessionId, attachedImage, refreshTrace, profileId]);

  const handleWizardComplete = useCallback(async (id: string) => {
    saveProfileId(id);
    setProfileId(id);
    setWizardOpen(false);
    // If they explicitly onboarded, clear the dismissed flag — they came back.
    clearWizardDismissed();
    // Refetch — when editing, the id is unchanged so the [profileId] effect
    // won't fire on its own. Pull the canonical updated profile so the
    // header reflects the change immediately.
    try {
      const p = await getProfile(id);
      setProfile(p);
    } catch {
      // benign — the [profileId] effect will retry on next render cycle
    }
  }, []);

  const handleWizardDismiss = useCallback(() => {
    saveWizardDismissed();
    setWizardOpen(false);
  }, []);

  const handleEditProfile = useCallback(() => {
    // Re-open the wizard. Don't clear the existing profile; the wizard will
    // upsert via /profile and the server keeps the same id if we sent it.
    // For simplicity v1 just re-collects fresh — server upsert handles it.
    clearWizardDismissed();
    setWizardOpen(true);
  }, []);

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
      <Header
        sessionId={sessionId}
        onReset={handleReset}
        profile={profile}
        onEditProfile={handleEditProfile}
        viewMode={viewMode}
        onToggleViewMode={toggleViewMode}
      />
      {wizardOpen && (
        <OnboardingWizard
          onComplete={handleWizardComplete}
          onDismiss={handleWizardDismiss}
          existing={profile}
        />
      )}

      <main className="flex-1 overflow-y-auto">
        {isEmpty ? (
          // Empty state — full-width hero + 3-up gallery, no sidebar
          <div className="mx-auto max-w-[1200px] px-4 py-12 sm:py-16 lg:px-10">
            <RouteGallery
              profile={profile}
              onPlan={(prompt) => handleSubmit(prompt)}
            />
          </div>
        ) : (
          // Conversation — same wide container as the landing for visual
          // responses (maps, itineraries) to breathe. Individual bubbles
          // self-cap text width inside; visual content fills the column.
          <div className="mx-auto max-w-[1200px] px-4 py-10 sm:py-14 lg:px-10">
            <div className="space-y-5">
              {messages.map((m) => (
                <MessageBubble
                  key={m.id}
                  message={m}
                  viewMode={viewMode}
                  corridor={corridor}
                />
              ))}
              {isPending ? <LoadingIndicator trace={trace} /> : null}
              {error ? (
                <div className="rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                  {error}
                </div>
              ) : null}
              <div ref={scrollAnchorRef} />
            </div>
          </div>
        )}
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

// EmptyState + PersonalisedEmptyState were replaced by RouteGallery
// (Phase 2E · UI redesign). The gallery's Hero block carries any
// personalisation cue based on the loaded profile.
