# Repo-root Dockerfile for hosts that build from the repository root (e.g. Render).
# backend/Dockerfile stays for fly.io/Railway (root dir = backend).
#
# Two stages, because the image now serves BOTH the API and the Mini App:
#   1. node  — compiles webapp/ into a static bundle (webapp/dist)
#   2. python — FastAPI + the bundle copied in
# One git push therefore updates the API and the Mini App together; no separate
# static host (and no second publish step that can silently fail) is involved.

# ---------------------------------------------------------------- stage 1: web
FROM node:20-alpine AS webapp-builder

WORKDIR /build

# Dependencies first for better layer caching.
COPY webapp/package.json webapp/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY webapp/ ./

# The bundle is served by this same host, so it may call same-origin "/api";
# the absolute URL keeps working for any other static host too.
ARG VITE_API_URL=https://eduqurst.onrender.com
ENV VITE_API_URL=$VITE_API_URL

RUN npm run build

# ------------------------------------------------------------- stage 2: runtime
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first (better layer caching).
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy only what the app needs to RUN.
# .env files are NOT in the git repo at all (see .gitignore) — secrets are
# injected as environment variables by the platform (Render Environment tab).
COPY backend/app ./app
COPY backend/alembic.ini ./
COPY backend/alembic ./alembic

# app/webapp.py looks for <workdir>/webapp/dist, so the bundle lands there.
COPY --from=webapp-builder /build/dist ./webapp/dist

# Render routes traffic to the EXPOSEd port; PORT override kept for other hosts.
EXPOSE 8000
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
