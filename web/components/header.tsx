"use client";

import { Bike, Map, Plus, Type, UserRound } from "lucide-react";
import type { UserProfile } from "@/lib/types";
import type { ViewMode } from "@/lib/view-mode";

interface HeaderProps {
  sessionId: string | null;
  onReset: () => void;
  profile?: UserProfile | null;
  onEditProfile?: () => void;
  viewMode?: ViewMode;
  onToggleViewMode?: () => void;
}

/**
 * Header — minimal, user-facing only. No session hash, no model id, no
 * cryptic "personalised" pill. Three actions, each clearly labelled:
 *
 *   - Visual / Text — segmented view toggle
 *   - Profile — opens the wizard to edit your saved answers
 *   - New trip — starts a fresh conversation (keeps your profile)
 */
export function Header({
  sessionId,
  onReset,
  profile,
  onEditProfile,
  viewMode,
  onToggleViewMode,
}: HeaderProps) {
  return (
    <header className="surface-glass sticky top-0 z-30 border-b border-border/50">
      <div className="mx-auto flex h-14 max-w-[1480px] items-center gap-4 px-4 lg:px-10 xl:px-14">
        {/* Brand */}
        <div className="flex shrink-0 items-center gap-2.5">
          <div className="relative flex h-7 w-7 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-[0_2px_8px_-2px_rgba(255,61,20,0.5)]">
            <Bike className="h-3.5 w-3.5" aria-hidden />
          </div>
          <span className="text-[15px] font-semibold tracking-[-0.01em] text-foreground">
            Cyclepath
          </span>
        </div>

        <div className="flex-1" />

        {/* Right cluster — clear, labelled actions */}
        <div className="flex shrink-0 items-center gap-2">
          {onToggleViewMode && viewMode && (
            <ViewToggle mode={viewMode} onToggle={onToggleViewMode} />
          )}

          {onEditProfile && (
            <ProfileButton profile={profile ?? null} onClick={onEditProfile} />
          )}

          <button
            type="button"
            onClick={onReset}
            disabled={!sessionId}
            className="inline-flex h-8 items-center gap-1.5 rounded-full bg-foreground px-3 text-[12px] font-semibold text-background transition-colors hover:bg-foreground/90 disabled:cursor-not-allowed disabled:bg-foreground/40"
            title="Start a fresh conversation (your profile stays the same)"
          >
            <Plus className="h-3.5 w-3.5" aria-hidden />
            New trip
          </button>
        </div>
      </div>
    </header>
  );
}

function ViewToggle({
  mode,
  onToggle,
}: {
  mode: ViewMode;
  onToggle: () => void;
}) {
  return (
    <div className="relative inline-flex h-8 items-center rounded-full border border-border/80 bg-card p-0.5">
      {/* Animated thumb */}
      <span
        className={[
          "absolute top-0.5 bottom-0.5 w-[68px] rounded-full bg-foreground transition-all duration-200 ease-out",
          mode === "visual" ? "left-0.5" : "left-[70px]",
        ].join(" ")}
        aria-hidden
      />
      <button
        type="button"
        onClick={mode === "visual" ? undefined : onToggle}
        className={[
          "relative z-10 inline-flex h-7 w-[68px] items-center justify-center gap-1 rounded-full text-[11.5px] font-semibold transition-colors",
          mode === "visual" ? "text-background" : "text-muted-foreground hover:text-foreground",
        ].join(" ")}
      >
        <Map className="h-3 w-3" aria-hidden />
        Visual
      </button>
      <button
        type="button"
        onClick={mode === "text" ? undefined : onToggle}
        className={[
          "relative z-10 inline-flex h-7 w-[68px] items-center justify-center gap-1 rounded-full text-[11.5px] font-semibold transition-colors",
          mode === "text" ? "text-background" : "text-muted-foreground hover:text-foreground",
        ].join(" ")}
      >
        <Type className="h-3 w-3" aria-hidden />
        Text
      </button>
    </div>
  );
}

function ProfileButton({
  profile,
  onClick,
}: {
  profile: UserProfile | null;
  onClick: () => void;
}) {
  const hasProfile = Boolean(profile);

  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        "inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-[12px] font-medium transition-colors",
        hasProfile
          ? "border border-border/80 bg-card text-foreground hover:border-foreground/30"
          : "border border-primary/40 bg-primary/[0.08] text-primary hover:bg-primary/[0.12]",
      ].join(" ")}
      title={hasProfile ? "Edit your saved profile" : "Set up your profile"}
    >
      <UserRound className="h-3.5 w-3.5" aria-hidden />
      {hasProfile ? (
        <>
          <span className="capitalize">{profile?.experience}</span>
          <span className="text-muted-foreground/80">·</span>
          <span className="font-mono tabular-nums text-muted-foreground">
            {profile?.max_daily_km_comfort}
            <span className="ml-0.5 text-[10px]">km</span>
          </span>
        </>
      ) : (
        "Set up profile"
      )}
    </button>
  );
}
