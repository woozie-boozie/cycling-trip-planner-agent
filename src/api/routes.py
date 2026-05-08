"""HTTP routes for the cycling trip planner agent."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


@router.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    """Liveness probe for Cloud Run + local dev."""
    return HealthResponse(status="ok", service="cycling-trip-planner-agent", version="0.1.0")


@router.get("/", response_model=HealthResponse)
async def root() -> HealthResponse:
    """Root endpoint — same shape as /healthz for convenience."""
    return HealthResponse(status="ok", service="cycling-trip-planner-agent", version="0.1.0")
