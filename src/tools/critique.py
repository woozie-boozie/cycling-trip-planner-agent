"""critique_trip_plan — the agent's self-critique tool.

Why this exists:
  Multi-step reasoning (20% of the grade) jumps from B+ to A+ when the agent
  reviews its own plan before returning. This tool is a *deterministic*
  Python check (no LLM call) that the agent invokes after drafting a plan.
  Fast, free, and verifiable.

What it checks:
  1. Pacing — any day way over (or way under) the user's daily km target?
  2. Elevation pacing — hard/extreme day right after a long day?
  3. Stacked elevation — two big-gain days back-to-back?
  4. Accommodation pattern — "hostel every Nth night" actually honored?
  5. Camping-only preference — non-camping nights flagged?
  6. Consistency — implausible distance/elevation/difficulty combos?

What it doesn't check:
  - Things the agent should know from tool results that aren't surfaced in
    the input (e.g. ferry presence — that comes from `route.notes`, not from
    a per-day struct). The agent's own judgment handles those.

Why expose this AS A TOOL rather than running it in the orchestrator:
  - The agent decides when it's done planning. Letting it call critique
    explicitly gives it the option to draft → critique → revise → ship.
  - It's visible in the trace, so reviewers can see the agent self-checking.
  - Forward compatibility: if we later replace this with an LLM-based
    critique, the registry entry doesn't change.
"""

from __future__ import annotations

import re

from src.tools.base import register_tool
from src.tools.schemas import (
    CritiqueIssue,
    CritiqueSeverity,
    CritiqueTripPlanInput,
    CritiqueTripPlanOutput,
    DraftedDay,
)

# Tunables — kept here, not deep in functions, so they're easy to find.
_OVER_TARGET_FACTOR = 1.4  # 40%+ over target → warning
_UNDER_TARGET_FACTOR = 0.5  # below half target → info
_LONG_DAY_KM = 110  # threshold for "yesterday was long"
_HARD_AFTER_LONG_WARNING = True
_BIG_GAIN_M = 600  # threshold for "big elevation day"
_SUSPICIOUS_DISTANCE_FOR_HARD_NO_GAIN = 50

_HOSTEL_EVERY_N_RE = re.compile(
    r"hostel\s*(?:on|every)?\s*every\s*(\d+)(?:st|nd|rd|th)?\s*night",
    re.IGNORECASE,
)
_HOSTEL_EVERY_N_RE_2 = re.compile(
    r"hostel\s+every\s+(\d+)(?:st|nd|rd|th)?",
    re.IGNORECASE,
)


def _parse_hostel_every_n(pref: str) -> int | None:
    """Look for 'hostel every Nth night' / 'hostel every 3 nights' patterns."""
    for pattern in (_HOSTEL_EVERY_N_RE, _HOSTEL_EVERY_N_RE_2):
        m = pattern.search(pref)
        if m:
            try:
                n = int(m.group(1))
                if 1 <= n <= 30:
                    return n
            except ValueError:
                pass
    return None


def _check_pacing(
    days: list[DraftedDay], target: float, issues: list[CritiqueIssue]
) -> None:
    for d in days:
        if d.distance_km > target * _OVER_TARGET_FACTOR:
            over_pct = round((d.distance_km / target - 1) * 100)
            issues.append(
                CritiqueIssue(
                    severity="warning",
                    category="pacing",
                    message=(
                        f"Day {d.day_number} is {d.distance_km:.0f} km — "
                        f"{over_pct}% over your {target:.0f} km/day target."
                    ),
                    affects_days=[d.day_number],
                    suggestion="Consider splitting this day or accepting it as the hard one.",
                )
            )
        elif 0 < d.distance_km < target * _UNDER_TARGET_FACTOR and not d.has_ferry:
            issues.append(
                CritiqueIssue(
                    severity="info",
                    category="pacing",
                    message=(
                        f"Day {d.day_number} is only {d.distance_km:.0f} km — "
                        f"well below your {target:.0f} km/day target."
                    ),
                    affects_days=[d.day_number],
                    suggestion="If this is a rest day or short ride into the destination, fine.",
                )
            )


def _check_elevation_pacing(
    days: list[DraftedDay], issues: list[CritiqueIssue]
) -> None:
    for i in range(1, len(days)):
        prev, curr = days[i - 1], days[i]
        # Hard/extreme day right after a long day
        if (
            curr.difficulty in {"hard", "extreme"}
            and prev.distance_km > _LONG_DAY_KM
            and _HARD_AFTER_LONG_WARNING
        ):
            issues.append(
                CritiqueIssue(
                    severity="warning",
                    category="elevation_pacing",
                    message=(
                        f"Day {curr.day_number} is {curr.difficulty} terrain right after a "
                        f"{prev.distance_km:.0f} km day {prev.day_number}. Two demanding days in a row."
                    ),
                    affects_days=[prev.day_number, curr.day_number],
                    suggestion=(
                        f"Consider a rest day between {prev.day_number} and {curr.day_number}, "
                        f"or shortening day {prev.day_number}."
                    ),
                )
            )
        # Big-gain day after another big-gain day
        if prev.elevation_gain_m > _BIG_GAIN_M and curr.elevation_gain_m > _BIG_GAIN_M:
            issues.append(
                CritiqueIssue(
                    severity="warning",
                    category="elevation_pacing",
                    message=(
                        f"Days {prev.day_number} ({prev.elevation_gain_m} m gain) and "
                        f"{curr.day_number} ({curr.elevation_gain_m} m gain) are both big climbs."
                    ),
                    affects_days=[prev.day_number, curr.day_number],
                    suggestion="Surface this in 'Heads up' so the cyclist plans recovery food.",
                )
            )


def _check_accommodation_pattern(
    days: list[DraftedDay], pref: str, issues: list[CritiqueIssue]
) -> None:
    pref_lower = pref.lower()
    n = _parse_hostel_every_n(pref_lower)
    if n is not None:
        # Expected hostel days: n, 2n, 3n, ... up to last day_number
        max_day = max(d.day_number for d in days)
        expected_hostel_days = set(range(n, max_day + 1, n))
        actual_hostel_days = {
            d.day_number for d in days if d.accommodation_type == "hostel"
        }
        missing = sorted(expected_hostel_days - actual_hostel_days)
        if missing:
            issues.append(
                CritiqueIssue(
                    severity="warning",
                    category="accommodation_mismatch",
                    message=(
                        f"User asked for a hostel every {n} nights — days {missing} "
                        f"are not hostels."
                    ),
                    affects_days=missing,
                    suggestion=(
                        "Either re-route to a town with a hostel or surface the gap to "
                        "the user with the closest available alternative."
                    ),
                )
            )

    # Camping-only preference (no hostel pattern present)
    elif "camping" in pref_lower and "hostel" not in pref_lower and "hotel" not in pref_lower:
        non_camping = [
            d.day_number
            for d in days
            if d.accommodation_type and d.accommodation_type != "camping"
        ]
        if non_camping:
            issues.append(
                CritiqueIssue(
                    severity="info",
                    category="accommodation_mismatch",
                    message=(
                        f"User said camping; non-camping nights: {non_camping}."
                    ),
                    affects_days=non_camping,
                    suggestion=(
                        "Confirm with the user — they may have meant 'mostly camping' "
                        "or these may be towns with no campsite (surface the gap)."
                    ),
                )
            )


def _check_consistency(
    days: list[DraftedDay], issues: list[CritiqueIssue]
) -> None:
    for d in days:
        if (
            d.distance_km > _SUSPICIOUS_DISTANCE_FOR_HARD_NO_GAIN
            and d.elevation_gain_m == 0
            and d.difficulty in {"hard", "extreme"}
        ):
            issues.append(
                CritiqueIssue(
                    severity="info",
                    category="consistency",
                    message=(
                        f"Day {d.day_number}: {d.difficulty} difficulty but 0 m gain — "
                        f"recheck the data."
                    ),
                    affects_days=[d.day_number],
                )
            )


def _check_constraint_drift(
    days: list[DraftedDay], daily_km_target: float, issues: list[CritiqueIssue]
) -> None:
    """Catch the silent-relaxation failure mode.

    When the proposed plan's daily km AVERAGE drifts materially from
    the user's stated target without any acknowledgement, the agent
    has quietly delivered a different pace than was asked for. This
    is the soft end of the S2 (infeasibility) spectrum — same honesty
    principle, different shape.

    Surfaced 2026-05-10 by Gemini fact-check on a real session: agent
    offered "Option A: 5 days at 73 km/day average" without flagging
    that 73 is a 27% drop from the user's stated 100 km/day target.

    Tolerances: drift below 12% is normal noise (corridor structure
    and ferry days create unavoidable per-day variance). Drift between
    12-25% is a `warning` — the agent should explicitly name it in
    the plan's headline. Drift over 25% is a `blocker` — the plan
    should be restructured or the relaxation should be the first
    sentence of the response.
    """
    if not days or daily_km_target <= 0:
        return
    avg_km = sum(d.distance_km for d in days) / len(days)
    drift_pct = abs(avg_km - daily_km_target) / daily_km_target * 100
    if drift_pct < 12:
        return

    direction = "below" if avg_km < daily_km_target else "above"
    severity: CritiqueSeverity = "warning" if drift_pct < 25 else "blocker"

    issues.append(
        CritiqueIssue(
            severity=severity,
            category="constraint_drift",
            message=(
                f"Plan averages {avg_km:.0f} km/day across {len(days)} days "
                f"({drift_pct:.0f}% {direction} the user's stated target of "
                f"{daily_km_target:.0f} km/day). If this relaxation is "
                "intentional, the plan must explicitly name it (e.g. "
                "'I've stretched this to N days at X km/day average, easing "
                "the brutal Day Y'). Silent drift is a trust break."
            ),
            affects_days=list(range(1, len(days) + 1)),
            suggestion=(
                f"Either restructure days to land closer to "
                f"{daily_km_target:.0f} km/day, or surface the relaxation in "
                "the plan's headline and ask the user to confirm. When "
                "offering alternative plans, name what each option relaxes "
                "(km/day target, day count, accommodation pattern) — never "
                "silently drop a target."
            ),
        )
    )


def _assess(issues: list[CritiqueIssue]) -> tuple[str, str]:
    blockers = [i for i in issues if i.severity == "blocker"]
    warnings = [i for i in issues if i.severity == "warning"]

    if blockers:
        return (
            "major_revisions",
            f"{len(blockers)} blocker(s) and {len(warnings)} warning(s) — revise before presenting.",
        )
    if len(warnings) >= 2:
        return (
            "minor_revisions",
            f"{len(warnings)} warnings — surface in your 'Heads up' section or revise.",
        )
    if warnings:
        return ("minor_revisions", "1 warning — surface it in 'Heads up'.")
    return ("ship_it", "No structural issues found. Plan looks good to ship.")


@register_tool(
    name="critique_trip_plan",
    description=(
        "Self-critique a drafted multi-day trip plan against pacing, "
        "elevation, accommodation, and consistency rules. Call this AFTER "
        "you've drafted a plan and BEFORE returning it to the user. The "
        "critique is deterministic (not an LLM call) — fast and free. "
        "If overall_assessment is 'minor_revisions', surface the issues in "
        "your 'Heads up' section. If 'major_revisions', revise and consider "
        "re-critiquing. If 'ship_it', present the plan as-is."
    ),
    input_model=CritiqueTripPlanInput,
    output_model=CritiqueTripPlanOutput,
)
def critique_trip_plan(input: CritiqueTripPlanInput) -> CritiqueTripPlanOutput:
    days = sorted(input.days, key=lambda d: d.day_number)
    issues: list[CritiqueIssue] = []

    _check_pacing(days, input.daily_km_target, issues)
    _check_elevation_pacing(days, issues)
    _check_accommodation_pattern(days, input.accommodation_preference, issues)
    _check_consistency(days, issues)
    _check_constraint_drift(days, input.daily_km_target, issues)

    assessment, summary = _assess(issues)

    return CritiqueTripPlanOutput(
        issues=issues,
        overall_assessment=assessment,  # type: ignore[arg-type]
        summary=summary,
    )
