# syntax=docker/dockerfile:1
# One image serves the API and the built single-page app (Cloud Run service `arzi`).

# ---- web: build the SPA -------------------------------------------------------------------
FROM node:24-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# ---- api: resolve the locked Python environment --------------------------------------------
FROM python:3.12-slim AS api
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
RUN pip install --no-cache-dir "uv==0.13.9"
WORKDIR /app
COPY api/pyproject.toml api/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY api/src ./src
RUN uv sync --locked --no-dev --no-editable

# ---- runtime: no build tools, non-root ------------------------------------------------------
FROM python:3.12-slim AS runtime
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin arzi
WORKDIR /app
COPY --from=api /app/.venv /app/.venv
COPY --from=web /web/dist /app/static
# Synthetic demo documents, recorded model responses (replay) and ideal extractions (fake).
COPY demo_cases /app/demo_cases
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ARZI_STATIC_DIR=/app/static \
    PORT=8080
USER arzi
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn arzi.main:create_app --factory --host 0.0.0.0 --port \"$PORT\" --proxy-headers --forwarded-allow-ips='*' --no-server-header"]
