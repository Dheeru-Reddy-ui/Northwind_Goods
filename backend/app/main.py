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
from app.routers.actions import router as actions_router
from app.routers.chat import router as chat_router
from app.store.router import router as store_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("northwind")

app = FastAPI(
    title="Northwind Support AI",
    version=__version__,
    description="Autonomous e-commerce customer support agent for Northwind Goods.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    init_db()
    logger.info(
        "Northwind Support AI up. db=%s llm=%s",
        settings.database_url.split("://")[0],
        "anthropic" if settings.llm_available else "deterministic (offline)",
    )


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"error": "internal_error", "detail": str(exc)})


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "llm": "anthropic" if settings.llm_available else "deterministic",
    }


@app.get("/", tags=["meta"])
def root() -> dict:
    return {"service": "Northwind Support AI", "docs": "/docs", "health": "/health"}


app.include_router(store_router)
app.include_router(chat_router)
app.include_router(actions_router)
app.include_router(observability_router)
