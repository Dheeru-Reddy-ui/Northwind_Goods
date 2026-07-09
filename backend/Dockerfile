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
# The app bootstraps its data (seed + ingest) on first boot and skips when the
# database already has data — safe for both SQLite and a persistent Supabase.
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
