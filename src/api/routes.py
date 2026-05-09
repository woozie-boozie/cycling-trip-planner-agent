"""HTTP routes for the cycling trip planner agent.

Endpoints:
  GET  /healthz                  — liveness probe
  GET  /                         — root, same shape as healthz
  POST /chat                     — single conversational turn (the brief's required endpoint)
  POST /profile                  — upsert a cyclist profile (Phase 2D)
  GET  /profile/{profile_id}     — fetch a cyclist profile (Phase 2D)
  DELETE /profile/{profile_id}   — drop a profile (Phase 2D)
  GET  /sessions                 — list active session ids
  GET  /sessions/{session_id}    — full conversation state for a session
  DELETE /sessions/{session_id}  — drop a session
  GET  /trace/{session_id}       — observability — full ordered trace
"""

from __future__ import annotations

from typing import Any, Literal

import structlog
from anthropic import AsyncAnthropic
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.agent import (
    AgentLoopExceeded,
    AgentResponse,
    ConversationState,
    TraceEvent,
    run_turn,
)
from src.api.dependencies import (
    get_anthropic_client,
    get_profile_store,
    get_session_store,
)
from src.sessions import ProfileStore, SessionStore, UserProfile, UserProfileCreate

log = structlog.get_logger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


@router.get("/healthz", response_model=HealthResponse, tags=["meta"])
async def healthz() -> HealthResponse:
    """Liveness probe for Cloud Run + local dev."""
    return HealthResponse(status="ok", service="cycling-trip-planner-agent", version="0.1.0")


@router.get("/", response_model=HealthResponse, tags=["meta"])
async def root() -> HealthResponse:
    return HealthResponse(status="ok", service="cycling-trip-planner-agent", version="0.1.0")


# ---------------------------------------------------------------------------
# Chat — the brief's required endpoint
# ---------------------------------------------------------------------------


class ChatImage(BaseModel):
    """Optional image attachment for multimodal /chat requests.

    Mirrors Anthropic's content-block image format. The agent receives the
    image as the first content block of the user message and reasons about
    it directly — no separate "extract intent" pass.
    """

    media_type: Literal["image/jpeg", "image/png", "image/webp", "image/gif"] = Field(
        description="MIME type. Anthropic vision supports JPEG, PNG, WebP, and GIF."
    )
    base64_data: str = Field(
        min_length=1,
        max_length=10_000_000,
        description="Base64-encoded image data. Cap at ~7MB encoded (~5MB decoded).",
    )


class ChatRequest(BaseModel):
    """Body for POST /chat.

    Pass `session_id` to continue an existing conversation. Omit it to start a
    fresh one — the response will include a generated id you can re-send.

    Optionally attach an `image` (base64) to send a multimodal turn — the
    agent will reason over the image (e.g. a Strava/Komoot screenshot) AND
    the text in one loop.
    """

    message: str = Field(
        min_length=1,
        max_length=4000,
        description="The user's message for this turn.",
    )
    session_id: str | None = Field(
        default=None,
        description="Optional. If provided and the session exists, the conversation resumes. "
        "If omitted, a fresh session is created.",
    )
    image: ChatImage | None = Field(
        default=None,
        description=(
            "Optional. Base64-encoded image to attach to the user's message. "
            "When provided, the agent receives both the image and the text as content blocks."
        ),
    )
    profile_id: str | None = Field(
        default=None,
        description=(
            "Optional cyclist profile id (Phase 2D). When supplied and known, "
            "the agent personalises its planning to this rider's experience, "
            "priorities, and dietary needs. Created via POST /profile."
        ),
    )


class ChatResponse(BaseModel):
    """Reply for POST /chat.

    Always includes the `session_id` so a client without prior context can use
    the response directly to continue the conversation.
    """

    session_id: str
    message: str = Field(description="The agent's final assistant text for this turn.")
    stop_reason: str
    iterations: int = Field(description="LLM round-trips required to resolve this turn.")
    input_tokens: int
    output_tokens: int
    tool_calls: list[dict[str, Any]] = Field(
        description="Summary of tools invoked this turn — names and argument keys."
    )


@router.post("/chat", response_model=ChatResponse, tags=["chat"])
async def chat(
    request: ChatRequest,
    store: SessionStore = Depends(get_session_store),
    profile_store: ProfileStore = Depends(get_profile_store),
    client: AsyncAnthropic = Depends(get_anthropic_client),
) -> ChatResponse:
    """Run one conversational turn against the cycling trip planner agent.

    Behavior:
      - With no session_id: creates a fresh ConversationState.
      - With a known session_id: resumes the existing conversation.
      - With an unknown session_id: 404. (We don't silently create — that
        would mask client bugs.)

    The agent's tool-use loop runs to completion before the response returns.
    Multi-turn flows are coordinated by the client re-sending the session_id.
    """
    if request.session_id is None:
        state = ConversationState()
        is_new = True
    else:
        existing = await store.get(request.session_id)
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"session {request.session_id!r} not found",
            )
        state = existing
        is_new = False

    # Load the profile (if requested + known). Treat missing profile as a soft
    # miss — log it but proceed without personalisation; mirrors the same
    # contract as session expiry on /chat (frontend handles re-onboarding).
    profile: UserProfile | None = None
    if request.profile_id is not None:
        profile = await profile_store.get(request.profile_id)
        if profile is None:
            log.info(
                "chat.profile.unknown",
                session_id=state.session_id,
                profile_id=request.profile_id,
            )

    log.info(
        "chat.turn.start",
        session_id=state.session_id,
        is_new=is_new,
        message_len=len(request.message),
        has_image=request.image is not None,
        has_profile=profile is not None,
    )

    # Multimodal: build a content list with the image as the first block,
    # text as the second. Anthropic accepts a string OR a list of content
    # blocks for the user message — see docs/agent-loop.md.
    user_message: str | list[dict[str, Any]]
    if request.image is not None:
        user_message = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": request.image.media_type,
                    "data": request.image.base64_data,
                },
            },
            {"type": "text", "text": request.message},
        ]
    else:
        user_message = request.message

    try:
        response: AgentResponse = await run_turn(
            state, user_message, client=client, profile=profile
        )
    except AgentLoopExceeded as e:
        log.warning("chat.loop_exceeded", session_id=state.session_id, error=str(e))
        # Persist the partial state so /trace can still show what happened.
        await store.put(state)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="agent did not converge — see /trace for what it tried",
        ) from e

    await store.put(state)

    log.info(
        "chat.turn.done",
        session_id=state.session_id,
        iterations=response.iterations,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        tool_calls=len(response.tool_calls),
    )

    return ChatResponse(
        session_id=response.session_id,
        message=response.message,
        stop_reason=response.stop_reason,
        iterations=response.iterations,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        tool_calls=response.tool_calls,
    )


# ---------------------------------------------------------------------------
# Profile — Phase 2D · onboarding wizard backend
# ---------------------------------------------------------------------------


@router.post("/profile", response_model=UserProfile, tags=["profile"])
async def upsert_profile(
    create: UserProfileCreate,
    profile_store: ProfileStore = Depends(get_profile_store),
) -> UserProfile:
    """Create or update a cyclist profile.

    Idempotent: send the same `profile_id` to update the existing profile,
    omit it for a fresh one (server generates a UUID4). The returned object
    includes the canonical `profile_id` the client should persist locally.

    `max_daily_km_comfort` is derived from `experience` server-side — clients
    don't need to know the mapping.
    """
    profile = create.to_profile()
    return await profile_store.upsert(profile)


@router.get("/profile/{profile_id}", response_model=UserProfile, tags=["profile"])
async def get_profile(
    profile_id: str,
    profile_store: ProfileStore = Depends(get_profile_store),
) -> UserProfile:
    profile = await profile_store.get(profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="profile not found")
    return profile


@router.delete("/profile/{profile_id}", tags=["profile"])
async def delete_profile(
    profile_id: str,
    profile_store: ProfileStore = Depends(get_profile_store),
) -> dict[str, bool]:
    deleted = await profile_store.delete(profile_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="profile not found")
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Sessions — read/list/delete
# ---------------------------------------------------------------------------


class SessionDetail(BaseModel):
    session_id: str
    created_at: str
    updated_at: str
    total_turns: int
    total_input_tokens: int
    total_output_tokens: int
    messages: list[dict[str, Any]]


class SessionList(BaseModel):
    session_ids: list[str]
    count: int


@router.get("/sessions", response_model=SessionList, tags=["sessions"])
async def list_sessions(store: SessionStore = Depends(get_session_store)) -> SessionList:
    ids = await store.list_ids()
    return SessionList(session_ids=ids, count=len(ids))


@router.get(
    "/sessions/{session_id}",
    response_model=SessionDetail,
    tags=["sessions"],
)
async def get_session(
    session_id: str, store: SessionStore = Depends(get_session_store)
) -> SessionDetail:
    state = await store.get(session_id)
    if state is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
    return SessionDetail(
        session_id=state.session_id,
        created_at=state.created_at.isoformat(),
        updated_at=state.updated_at.isoformat(),
        total_turns=state.total_turns,
        total_input_tokens=state.total_input_tokens,
        total_output_tokens=state.total_output_tokens,
        messages=state.messages,
    )


@router.delete("/sessions/{session_id}", tags=["sessions"])
async def delete_session(
    session_id: str, store: SessionStore = Depends(get_session_store)
) -> dict[str, bool]:
    deleted = await store.delete(session_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Trace — observability for the agent loop
# ---------------------------------------------------------------------------


class TraceResponse(BaseModel):
    session_id: str
    events: list[TraceEvent]
    event_count: int
    total_input_tokens: int
    total_output_tokens: int
    estimated_cost_usd: float = Field(
        description=(
            "Rough cost estimate using Sonnet-tier pricing — accurate to ~10%, "
            "intended for at-a-glance debugging not billing."
        )
    )


# Sonnet 4.5 / 4.6 input ≈ $3 / 1M tokens, output ≈ $15 / 1M tokens.
_INPUT_COST_PER_1M = 3.0
_OUTPUT_COST_PER_1M = 15.0


def _estimate_cost(input_tokens: int, output_tokens: int) -> float:
    return round(
        (input_tokens / 1_000_000) * _INPUT_COST_PER_1M
        + (output_tokens / 1_000_000) * _OUTPUT_COST_PER_1M,
        4,
    )


@router.get("/trace/{session_id}", response_model=TraceResponse, tags=["trace"])
async def get_trace(
    session_id: str, store: SessionStore = Depends(get_session_store)
) -> TraceResponse:
    """Return the full ordered trace of a session — every user message,
    assistant text, tool call, and tool result, in order, with token usage
    and estimated cost.

    This is what makes the agent inspectable. Useful in the demo for showing
    Edo and Sunny exactly how the agent reasoned over multiple turns.
    """
    state = await store.get(session_id)
    if state is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")

    return TraceResponse(
        session_id=state.session_id,
        events=state.trace,
        event_count=len(state.trace),
        total_input_tokens=state.total_input_tokens,
        total_output_tokens=state.total_output_tokens,
        estimated_cost_usd=_estimate_cost(state.total_input_tokens, state.total_output_tokens),
    )
