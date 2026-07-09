"""FastAPI application entrypoint.

Routers are added phase by phase. Phase 0 wires the store's internal systems
and a health check; later phases add /chat, /observability, /actions, /simulate.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.config import settings
from app.db.database import init_db
from app.observability.router import router as observability_router
from app.rate_limit import RateLimitMiddleware
from app.routers.actions import router as actions_router
from app.routers.chat import router as chat_router
from app.routers.chat_stream import router as chat_stream_router
from app.routers.simulate import router as simulate_router
from app.routers.voice import router as voice_router
from app.store.router import router as store_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("northwind")

app = FastAPI(
    title="Northwind Support AI",
    version=__version__,
    description="Autonomous e-commerce customer support agent for Northwind Goods.",
)

app.add_middleware(RateLimitMiddleware)
# CORS_ORIGINS="*" opens the API to any origin (credentials must be off per the
# CORS spec) — convenient for a public demo where the frontend URL isn't known
# ahead of time. Otherwise, an explicit allow-list with credentials.
_allow_all_origins = "*" in settings.cors_origin_list
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _allow_all_origins else settings.cors_origin_list,
    allow_credentials=not _allow_all_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    # Create schema + populate a fresh DB (SQLite or Supabase) on first boot;
    # skips when data already exists. Wrapped so a DB connection problem logs
    # clearly instead of crashing startup and silently rolling back the deploy —
    # /health then reports db + db_ok so the issue is diagnosable remotely.
    from app.db.database import SessionLocal
    from app.knowledge.ingest import ingest_if_empty
    from app.store.seed import seed_if_empty

    try:
        init_db()
        db = SessionLocal()
        try:
            seeded = seed_if_empty(db)
            ingested = ingest_if_empty(db)
            if seeded or ingested:
                logger.info("Bootstrapped data: seeded=%s ingested=%s", bool(seeded), bool(ingested))
        finally:
            db.close()
    except Exception as e:
        logger.warning("Startup DB init/bootstrap failed (%s: %s)", type(e).__name__, e)
    logger.info(
        "Northwind Support AI up. db=%s llm=%s",
        settings.database_url.split("://")[0].replace("+psycopg2", ""),
        "anthropic" if settings.llm_available else "deterministic (offline)",
    )


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"error": "internal_error", "detail": str(exc)})


@app.get("/health", tags=["meta"])
def health() -> dict:
    import os

    from sqlalchemy import text

    from app.db.database import engine

    db_ok = True
    try:
        with engine.connect() as conn:
            conn.execute(text("select 1"))
    except Exception:
        db_ok = False
    return {
        "status": "ok",
        "version": __version__,
        "db": engine.url.get_backend_name(),  # "postgresql" (Supabase) or "sqlite"
        "db_ok": db_ok,
        # diagnostic: is DATABASE_URL present in the process env? (boolean, no value)
        "database_url_in_env": bool(os.getenv("DATABASE_URL")),
        "llm": "anthropic" if settings.llm_available else "deterministic",
    }


@app.get("/", tags=["meta"])
def root() -> dict:
    return {"service": "Northwind Support AI", "docs": "/docs", "health": "/health"}


app.include_router(store_router)
app.include_router(chat_router)
app.include_router(chat_stream_router)
app.include_router(actions_router)
app.include_router(observability_router)
app.include_router(simulate_router)
app.include_router(voice_router)
