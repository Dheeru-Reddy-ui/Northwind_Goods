"""Optional LangSmith integration.

If LANGSMITH_API_KEY (and the langsmith package) are present, conversation
traces are additionally shipped to LangSmith as the primary tracing backend.
If not, this is a no-op and the Postgres/SQLite trace store is authoritative —
the app is fully observable either way. Kept behind this thin hook so the agent
loop never imports langsmith directly.
"""
from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger("northwind.langsmith")
_enabled: bool | None = None


def enabled() -> bool:
    global _enabled
    if _enabled is None:
        _enabled = bool(settings.langsmith_api_key)
        if _enabled:
            logger.info("LangSmith tracing enabled (project=%s).", settings.langsmith_project)
    return _enabled


def log_conversation(conversation_id: str, steps: list[dict]) -> None:
    """Ship a finished conversation trace to LangSmith when configured."""
    if not enabled():
        return
    try:  # pragma: no cover - exercised only when a key is configured
        from langsmith import Client

        client = Client(api_key=settings.langsmith_api_key)
        client.create_run(
            name=f"conversation:{conversation_id}",
            run_type="chain",
            project_name=settings.langsmith_project,
            inputs={"conversation_id": conversation_id},
            outputs={"steps": len(steps)},
        )
    except Exception as e:
        logger.warning("LangSmith logging failed: %s", e)
