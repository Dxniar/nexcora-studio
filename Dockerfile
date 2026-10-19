# syntax=docker/dockerfile:1
FROM node:24-alpine AS frontend
WORKDIR /build/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run typecheck && npm run build

FROM python:3.14-slim AS python-dependencies
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY requirements.lock ./
RUN python -m venv /opt/venv \
    && /opt/venv/bin/python -m pip install --requirement requirements.lock \
    && /opt/venv/bin/python -m pip check

FROM python:3.14-slim AS runtime
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
RUN groupadd --system --gid 10001 nexcora \
    && useradd --system --uid 10001 --gid nexcora --no-create-home nexcora
COPY --from=python-dependencies /opt/venv /opt/venv
COPY nexcora_studio/ ./nexcora_studio/
# Shared catalogue and the explicit legacy importer still depend on orderbot.
COPY orderbot/ ./orderbot/
COPY migrations/ ./migrations/
COPY alembic.ini ./
COPY --from=frontend /build/web/dist ./web/dist
USER nexcora
EXPOSE 8000
# Railway supplies PORT; __main__ binds 0.0.0.0. Migrations run separately.
CMD ["python", "-m", "nexcora_studio"]
