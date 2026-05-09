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
  /** Per-turn snapshot for assistant messages. Undefined while in flight. */
  meta?: {
    iterations: number;
    input_tokens: number;
    output_tokens: number;
    tool_calls: ToolCallSummary[];
  };
}
