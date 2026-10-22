# CLEARWAY: FastAPI serving the API and the built React UI (mirrors FaultForge's image).
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
# uv from PyPI rather than ghcr.io, which some networks cannot reach
RUN pip install --no-cache-dir "uv==0.11.3"
WORKDIR /app/backend
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev
COPY backend/clearway/ clearway/
COPY --from=web /web/dist /app/web/dist
RUN useradd --create-home clearway && chown -R clearway /app
USER clearway
# Offline runs need no keys. Live runs need NEBIUS_API_KEY + TAVILY_API_KEY as secrets and
# CLEARWAY_ALLOW_LIVE=1; they stay rate-limited and capped per day.
ENV PORT=8000 CLEARWAY_LIVE_RUNS_PER_DAY=40
EXPOSE 8000
CMD ["sh", "-c", "uv run --no-sync uvicorn clearway.api:app --host 0.0.0.0 --port ${PORT}"]
