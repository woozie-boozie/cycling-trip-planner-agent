/**
 * Markdown → day rows parser for the visual ItineraryCard.
 *
 * The agent's day-by-day plan output is reasonably consistent — `Day N`
 * heading + a `Distance:` line + a `Stay:` line — so we extract those
 * via regex on each detected section.
 *
 * Returns null when fewer than 3 day-headings are found (which is the
 * threshold below which an ItineraryCard is more chrome than the
 * markdown rendering it would replace).
 */

export type AccomType =
  | "camping"
  | "hostel"
  | "hotel"
  | "guesthouse"
  | "ferry"
  | "rest"
  | "unknown";

export interface DayRow {
  /** 1-indexed day number from the heading */
  n: number;
  /** Optional date if the heading carried one (e.g. "Day 1 · Jun 14 — London") */
  date?: string;
  /** Origin city extracted from "from → to" */
  from?: string;
  /** Destination city extracted from "from → to" */
  to?: string;
  /** Cycling km for the day */
  km?: number;
  /** Elevation gain in metres */
  climb?: number;
  /** Accommodation name surfaced in the "Stay:" line */
  accommodation?: string;
  /** Inferred accommodation type — drives the ItineraryCard glyph */
  accom_type?: AccomType;
  /** Whether this day involves a ferry crossing (no cycling km, special row) */
  has_ferry?: boolean;
}

/** Pre-compiled regexes hoisted out of the loop. */
const DAY_HEADING = /(?:^|\n)#{0,3}\s*Day\s+(\d+)\s*[—–\-:·]?\s*([^\n]+)?/gi;
const ROUTE_SPLIT = /\s*(?:[→⇒➔]|->|\bto\b)\s*/i;
const DISTANCE_RE = /Distance:?\s*(\d+(?:\.\d+)?)\s*km/i;
const CLIMB_RE = /(?:gain|climb|elevation)\s*[+]?(\d+)\s*m/i;
const STAY_RE = /Stay:?\s*\*{0,2}([^*\n(]+)\s*\(?\s*(camping|hostel|hotel|guesthouse|guest house|ferry|onboard cabin)/i;
const FERRY_HINT = /\b(ferry day|onboard|ferry crossing)\b/i;

/**
 * Extracts a structured day list from the agent's markdown response.
 * Returns null when the message doesn't look like a multi-day plan.
 */
export function parseItinerary(content: string): DayRow[] | null {
  const days: DayRow[] = [];
  let m: RegExpExecArray | null;
  // Reset before iterating — RegExp.exec is stateful with /g.
  DAY_HEADING.lastIndex = 0;

  // Collect day-heading match positions first so we can slice each
  // day's section between consecutive headings.
  const headings: { n: number; heading: string; start: number }[] = [];
  while ((m = DAY_HEADING.exec(content)) !== null) {
    headings.push({
      n: parseInt(m[1], 10),
      heading: (m[2] ?? "").trim(),
      start: m.index + m[0].length,
    });
  }

  if (headings.length < 3) return null;

  for (let i = 0; i < headings.length; i++) {
    const h = headings[i];
    const sectionEnd = headings[i + 1]?.start ?? Math.min(content.length, h.start + 800);
    const section = content.slice(h.start, sectionEnd);

    // Heading parsing — pulls "Amsterdam → Hoorn" (with optional date prefix).
    let date: string | undefined;
    let from: string | undefined;
    let to: string | undefined;

    let headingText = h.heading.replace(/^[*_]+|[*_]+$/g, "").trim();
    // If the heading contains "·" or "—", a date might be the first segment.
    const dateMaybeRe = /^(\w{3,9}\s+\d{1,2}|\d{1,2}\s+\w{3,9})\s*[·—\-]\s*(.+)$/;
    const dateMatch = headingText.match(dateMaybeRe);
    if (dateMatch) {
      date = dateMatch[1];
      headingText = dateMatch[2];
    }

    // route = "Amsterdam → Hoorn" or "Hamburg to Lübeck"
    const routeParts = headingText.split(ROUTE_SPLIT);
    if (routeParts.length >= 2) {
      from = routeParts[0].trim();
      to = routeParts[routeParts.length - 1].trim();
    } else if (headingText) {
      to = headingText;
    }

    const km = section.match(DISTANCE_RE);
    const climb = section.match(CLIMB_RE);
    // Try the strict regex first (catches `Stay: Foo (camping)`); if no
    // type tag was emitted, fall back to a name-only match so we can at
    // least extract the accommodation string.
    const stay =
      section.match(STAY_RE) ??
      section.match(/Stay:?\s*\*{0,2}([^*\n]+)/i);
    const hasFerry = FERRY_HINT.test(headingText) || FERRY_HINT.test(section);

    const accomName = stay?.[1]?.trim();
    const accomTypeFromMatch = stay?.[2]?.toLowerCase().trim();
    let accom_type: AccomType = "unknown";
    if (hasFerry) accom_type = "ferry";
    else if (accomTypeFromMatch === "camping") accom_type = "camping";
    else if (accomTypeFromMatch === "hostel") accom_type = "hostel";
    else if (accomTypeFromMatch === "hotel") accom_type = "hotel";
    else if (
      accomTypeFromMatch === "guesthouse" ||
      accomTypeFromMatch === "guest house"
    )
      accom_type = "guesthouse";
    else if (accomName) {
      // Heuristic fallback when the agent forgot the `(type)` tag.
      // The strict regex above is the contract; this is just a safety net.
      const lower = accomName.toLowerCase();
      if (/\bcamp(ing|site|sit)?\b|\bcamping\b/.test(lower)) accom_type = "camping";
      else if (/\b(hostel|yha|auberge\s+de\s+jeunesse)\b/.test(lower))
        accom_type = "hostel";
      else if (/\b(hotel|hôtel|inn|lodge|resort)\b/.test(lower)) accom_type = "hotel";
      else if (/\b(b&b|guesthouse|guest house|chambre d'hôtes)\b/.test(lower))
        accom_type = "guesthouse";
    }

    days.push({
      n: h.n,
      date,
      from,
      to,
      km: km ? parseFloat(km[1]) : undefined,
      climb: climb ? parseInt(climb[1], 10) : undefined,
      accommodation: accomName,
      accom_type,
      has_ferry: hasFerry,
    });
  }

  return days;
}

// ---------------------------------------------------------------------------
// Route header parsing — extracts corridor + variant identifiers from the
// agent's prose so the GPX download buttons know what to request.
// ---------------------------------------------------------------------------

export interface ParsedRouteHeader {
  /** Origin city (e.g. "London") */
  start: string;
  /** Destination city (e.g. "Paris") */
  end: string;
  /**
   * Variant identifier the agent picked — matches backend
   * `CorridorVariant.name` (e.g. "v16a_beauvais"). Resolved by matching
   * the prose against `ROUTE_VARIANTS` titles. ``null`` when the title
   * doesn't reference any catalogued variant (corridor with only one
   * variant, or unknown corridor).
   */
  variantName: string | null;
  /** Full matched heading line (for debugging / fallback display). */
  rawHeading: string;
}

const HEADER_LINE_RE =
  /(?:^|\n)#{1,3}\s+([^\n→⇒]+?)\s*(?:→|⇒|->)\s*([^\n]+)/;

/**
 * Pull out the corridor + variant from the agent's response prose.
 *
 * Matches headings like:
 *   ``# London → Paris via Avenue Verte V16a Beauvais``
 *   ``## Amsterdam → Copenhagen · EuroVelo 7 inland``
 *
 * Strategy:
 *   1. Find the first H1/H2/H3 line containing an arrow.
 *   2. Slice ``start`` and ``end`` from either side of the arrow.
 *   3. Search the heading for any variant title (case-insensitive,
 *      against the supplied `variantTitles` map) — pick the longest
 *      title that matches to prefer "V16a Beauvais" over "V16a".
 *
 * Returns ``null`` when no header is found in the content.
 */
export function parseRouteHeader(
  content: string,
  variantTitles: { name: string; title: string }[] = [],
): ParsedRouteHeader | null {
  const m = content.match(HEADER_LINE_RE);
  if (!m) return null;

  const start = cleanCity(m[1]);
  // The "end" capture may include the "via ..." suffix — split it back out
  // so we get the bare destination city and a separate variant string.
  const endRaw = m[2].trim();
  const viaSplit = endRaw.split(/\s+via\s+/i);
  const end = cleanCity(viaSplit[0]);
  const variantHint = viaSplit.slice(1).join(" via ").trim();

  // Look for the longest variant title that appears in either the
  // post-"via" hint or the full heading text. Longest match wins so
  // "V16a Beauvais" beats "V16a" when both could match.
  const haystack = (variantHint || endRaw + " " + start + " " + end).toLowerCase();
  let bestName: string | null = null;
  let bestLen = 0;
  for (const v of variantTitles) {
    // Compare against the title's leading segment (before "—" / "·"), since
    // the agent's prose typically drops the marketing suffix.
    const titleHead = v.title.split(/[—·–\-:]/)[0].trim().toLowerCase();
    if (!titleHead) continue;
    if (haystack.includes(titleHead) && titleHead.length > bestLen) {
      bestName = v.name;
      bestLen = titleHead.length;
    }
  }

  return {
    start,
    end,
    variantName: bestName,
    rawHeading: m[0].trim(),
  };
}

function cleanCity(raw: string): string {
  // Strip leading hashes/markdown chars and trailing punctuation.
  return raw
    .replace(/^[#\s*_]+/, "")
    .replace(/[\s*_,.:]+$/, "")
    .trim();
}
