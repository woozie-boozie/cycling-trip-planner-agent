"""FastAPI application entry point."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, LOG_LEVEL, logging.INFO)),
)

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run schema migrations on startup so Cloud Run cold starts produce a
    DB that matches the SQLModel definitions.

    `SQLModel.metadata.create_all` (called by `init_db()`) is idempotent —
    it skips tables that already exist (most of them on Neon, since
    `make seed` was run locally). The only table this realistically
    creates fresh on prod is `sessions` (Phase 1.12b) the first time
    after a deploy that introduces a new SQLModel table. Cheap to run
    every cold start.

    Skipped when no `DATABASE_URL` is set (local dev without .env, or
    the test process before a fixture provisions an engine).
    """
    if os.getenv("DATABASE_URL"):
        from src.db import init_db

        try:
            await init_db()
            log.info("db.init.success")
        except Exception as e:
            # Don't crash the boot — log and let a bad schema fail loudly
            # on the first real request. Cold-starting fast matters more
            # on Cloud Run than blocking /health on the migration.
            log.warning("db.init.failed", error=str(e))
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Cycling Trip Planner Agent",
        description="AI agent that helps a cyclist plan a multi-day bike trip through conversation.",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)

    log.info("app.started", log_level=LOG_LEVEL)
    return app


app = create_app()
