/**
 * TypeScript mirrors of the backend's Pydantic schemas.
 *
 * Source of truth lives in:
 *   - src/api/routes.py — ChatRequest, ChatResponse, TraceResponse
 *   - src/agent/state.py — TraceEvent
 *
 * If the backend schemas change, update these by hand. A future improvement
 * is generating types from the backend's OpenAPI doc via `openapi-typescript`.
 */

export type Role = "user" | "assistant";

export type ImageMediaType =
  | "image/jpeg"
  | "image/png"
  | "image/webp"
  | "image/gif";

export interface ChatImage {
  media_type: ImageMediaType;
  /** Base64-encoded image data (no data URL prefix). */
  base64_data: string;
}

export interface ChatRequest {
  message: string;
  session_id?: string;
  image?: ChatImage;
  /** Optional cyclist profile id (Phase 2D) — backend personalises the plan. */
  profile_id?: string;
}

// ---------------------------------------------------------------------------
// User profile (Phase 2D)
// ---------------------------------------------------------------------------

export type ExperienceLevel =
  | "beginner"
  | "casual"
  | "intermediate"
  | "experienced"
  | "racer";

export type TripStyle =
  | "weekend"
  | "touring"
  | "commute"
  | "charity"
  | "special"
  | "solo";

export type Priority =
  | "scenery"
  | "distance"
  | "food_drink"
  | "wild_camping"
  | "quiet_roads"
  | "pubs_culture"
  | "cheap"
  | "iconic"
  | "photography";

export type DietaryRestriction =
  | "vegetarian"
  | "vegan"
  | "gluten_free"
  | "halal"
  | "kosher"
  | "lactose_free"
  | "none";

/** Body for POST /profile — server fills in derived fields + timestamps. */
export interface UserProfileCreate {
  profile_id?: string;
  experience: ExperienceLevel;
  trip_styles: TripStyle[];
  priorities: Priority[];
  dietary: DietaryRestriction[];
  additional_notes?: string | null;
}

/** Canonical profile returned by GET / POST /profile. */
export interface UserProfile {
  profile_id: string;
  experience: ExperienceLevel;
  max_daily_km_comfort: number;
  trip_styles: TripStyle[];
  priorities: Priority[];
  dietary: DietaryRestriction[];
  additional_notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface ToolCallSummary {
  name: string;
  args: string[];
}

export interface ChatResponse {
  session_id: string;
  message: string;
  stop_reason: string;
  iterations: number;
  input_tokens: number;
  output_tokens: number;
  tool_calls: ToolCallSummary[];
}

export type TraceEventType =
  | "user_message"
  | "assistant_text"
  | "tool_use"
  | "tool_result"
  | "stop"
  | "error";

export interface TraceEvent {
  timestamp: string;
  type: TraceEventType;
  payload: Record<string, unknown>;
  iteration: number;
}

export interface TraceResponse {
  session_id: string;
  events: TraceEvent[];
  event_count: number;
  total_input_tokens: number;
  total_output_tokens: number;
  estimated_cost_usd: number;
}

/**
 * One tool invocation surfaced inline next to the agent's message while
 * the stream is in flight. Status flips from "running" to "done" or "error"
 * as the matching `tool_result` event arrives.
 */
export interface InlineTraceItem {
  toolUseId: string;
  name: string;
  status: "running" | "done" | "error";
  latencyMs?: number;
  /** Argument keys (not values) — keeps the pill compact + leaks no PII. */
  argKeys?: string[];
}

/** Local UI-only message representation for the chat thread. */
export interface UiMessage {
  id: string;
  role: Role;
  content: string;
  /**
   * For user messages with an attached image — the data URL we display in
   * the bubble. Stored separately from `content` (which is the text).
   */
  imageDataUrl?: string;
  /**
   * In-flight + completed tool calls for this assistant message,
   * surfaced as inline pills next to the bubble. Visible in both
   * text and visual modes.
   */
  liveTrace?: InlineTraceItem[];
  /** Per-turn snapshot for assistant messages. Undefined while in flight. */
  meta?: {
    iterations: number;
    input_tokens: number;
    output_tokens: number;
    tool_calls: ToolCallSummary[];
  };
}
