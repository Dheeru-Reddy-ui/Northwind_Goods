# Multi-stage build for the FastAPI agent backend.
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# --- deps layer (cached) ---
FROM base AS deps
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# --- runtime ---
FROM base AS runtime
WORKDIR /app
COPY --from=deps /install /usr/local
COPY . .
# Seed + ingest into the local SQLite volume on first boot, then serve.
EXPOSE 8000
CMD ["sh", "-c", "python -m app.store.seed && python -m app.knowledge.ingest && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
