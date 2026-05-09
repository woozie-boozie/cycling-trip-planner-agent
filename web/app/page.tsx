"use client";

import { useCallback, useEffect, useMemo, useRef, useState, useTransition } from "react";
import { Header } from "@/components/header";
import { MessageBubble } from "@/components/message-bubble";
import { LoadingIndicator } from "@/components/loading-indicator";
import { ChatInput } from "@/components/chat-input";
import { TracePanel } from "@/components/trace-panel";
import { OnboardingWizard } from "@/components/onboarding/wizard";
import { ApiError, getProfile, getTrace, postChat } from "@/lib/api";
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
  const [profileId, setProfileId] = useState<string | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [wizardOpen, setWizardOpen] = useState(false);

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
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setWizardOpen(true);
    }
  }, []);

  // When profileId becomes truthy, fetch the canonical profile so we can
  // render the personalised greeting. 404 = stale id (server lost it);
  // clear it and let the wizard re-prompt next time.
  useEffect(() => {
    if (!profileId) {
      setProfile(null);
      return;
    }
    let aborted = false;
    void (async () => {
      try {
        const p = await getProfile(profileId);
        if (!aborted) {
          // eslint-disable-next-line react-hooks/set-state-in-effect
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
  const refreshTrace = useCallback(async (id: string) => {
    setIsTraceLoading(true);
    try {
      const data = await getTrace(id);
      setTrace(data);
    } catch (err) {
      // 404 means the backend doesn't know this session anymore (e.g. server
      // restarted). Clear the stale id so the next /chat starts fresh.
      // Other errors are non-fatal — leave the existing panel as-is.
      if (err instanceof ApiError && err.status === 404) {
        clearSessionId();
        setSessionId(null);
        setTrace(null);
      }
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
        const messageText = text || "Plan this trip from the attached image.";
        let res;
        try {
          res = await postChat({
            message: messageText,
            session_id: sessionId ?? undefined,
            image: imageForRequest?.payload,
            profile_id: profileId ?? undefined,
          });
        } catch (firstErr) {
          // Session expired on the backend (e.g. process restart wiped the
          // in-memory store). Drop the stale session_id and retry once as
          // a fresh conversation. Same pattern as silent token refresh.
          if (firstErr instanceof ApiError && firstErr.status === 404 && sessionId) {
            clearSessionId();
            setSessionId(null);
            setTrace(null);
            res = await postChat({
              message: messageText,
              image: imageForRequest?.payload,
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
  }, [input, isPending, sessionId, attachedImage, refreshTrace, profileId]);

  const handleWizardComplete = useCallback((id: string) => {
    saveProfileId(id);
    setProfileId(id);
    setWizardOpen(false);
    // If they explicitly onboarded, clear the dismissed flag — they came back.
    clearWizardDismissed();
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
        hasProfile={Boolean(profile)}
        onEditProfile={handleEditProfile}
      />
      {wizardOpen && (
        <OnboardingWizard
          onComplete={handleWizardComplete}
          onDismiss={handleWizardDismiss}
        />
      )}

      <main className="flex-1 overflow-hidden">
        <div className="mx-auto flex h-full max-w-7xl">
          {/* Chat column — full width on mobile, ~7/10ths on desktop */}
          <div className="flex flex-1 flex-col overflow-hidden">
            <div className="flex-1 overflow-y-auto px-4 py-6">
              {isEmpty ? (
                <EmptyState profile={profile} />
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
function EmptyState({ profile }: { profile: UserProfile | null }) {
  if (profile) {
    return <PersonalisedEmptyState profile={profile} />;
  }
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

const EXPERIENCE_LABEL: Record<UserProfile["experience"], string> = {
  beginner: "beginner",
  casual: "casual rider",
  intermediate: "intermediate cyclist",
  experienced: "experienced rider",
  racer: "endurance / racer",
};
const TRIP_STYLE_LABEL: Record<UserProfile["trip_styles"][number], string> = {
  weekend: "weekend tours",
  touring: "multi-day touring",
  commute: "commuting",
  charity: "charity rides",
  special: "special-occasion trips",
  solo: "solo trips",
};
const PRIORITY_LABEL: Record<UserProfile["priorities"][number], string> = {
  scenery: "scenery",
  distance: "distance",
  food_drink: "food & drink",
  wild_camping: "wild camping",
  quiet_roads: "quiet roads",
  pubs_culture: "pubs & culture",
  cheap: "low-budget rides",
  iconic: "iconic routes",
  photography: "photography stops",
};

function joinHuman(items: string[]): string {
  if (items.length === 0) return "";
  if (items.length === 1) return items[0];
  if (items.length === 2) return `${items[0]} and ${items[1]}`;
  return `${items.slice(0, -1).join(", ")}, and ${items[items.length - 1]}`;
}

function PersonalisedEmptyState({ profile }: { profile: UserProfile }) {
  const experience = EXPERIENCE_LABEL[profile.experience];
  const styles = profile.trip_styles.map((s) => TRIP_STYLE_LABEL[s]);
  const priorities = profile.priorities.map((p) => PRIORITY_LABEL[p]);

  const stylePhrase = styles.length > 0 ? ` who likes ${joinHuman(styles)}` : "";
  const priorityPhrase =
    priorities.length > 0 ? ` Bias toward ${joinHuman(priorities)}.` : "";

  return (
    <div className="mx-auto flex h-full max-w-2xl flex-col items-center justify-center text-center">
      <div className="mb-5 rounded-full bg-primary/15 p-4 ring-1 ring-primary/20">
        <span className="text-3xl" aria-hidden>
          🚴
        </span>
      </div>
      <h2 className="mb-2 text-xl font-semibold tracking-tight text-foreground">
        Welcome back, {experience}
        {stylePhrase}.
      </h2>
      <p className="max-w-md text-sm leading-relaxed text-muted-foreground">
        I&apos;ll plan within your{" "}
        <span className="font-medium text-foreground">{profile.max_daily_km_comfort} km/day</span>{" "}
        comfort zone.
        {priorityPhrase} Where to next?
      </p>
      <p className="mt-4 text-xs text-muted-foreground/70">
        Try a suggestion below — or describe your own trip in your own words.
      </p>
    </div>
  );
}
