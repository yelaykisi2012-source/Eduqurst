# Repo-root Dockerfile for hosts that build from the repository root (e.g. Render).
# backend/Dockerfile stays for fly.io/Railway (root dir = backend).
#
# Two stages, because the image now serves the API, the Mini App AND runs the
# Telegram bot:
#   1. node   — compiles webapp/ into a static bundle (webapp/dist)
#   2. python — FastAPI + the bundle + bot/, started together by serve.py
# One git push therefore updates the API, the Mini App and the bot at once; no
# separate static host (and no second publish step that can silently fail) is
# involved, and the bot costs nothing extra to keep online.

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

# Install dependencies first (better layer caching). Both requirement sets land
# in ONE image because the container now runs the API and the Telegram bot
# together — see serve.py. (Render has no free Background Worker instance type,
# so a separate bot service would cost $7/month.)
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY bot/requirements.txt ./bot-requirements.txt
RUN pip install --no-cache-dir -r bot-requirements.txt

# Copy only what the app needs to RUN.
# .env files are NOT in the git repo at all (see .gitignore) — secrets are
# injected as environment variables by the platform (Render Environment tab).
COPY backend/app ./app
COPY backend/alembic.ini ./
COPY backend/alembic ./alembic

# The bot imports its own folder flat (import config, import handlers...),
# which serve.py arranges by putting /app/bot on sys.path.
COPY bot ./bot
COPY serve.py ./

# app/webapp.py looks for <workdir>/webapp/dist, so the bundle lands there.
COPY --from=webapp-builder /build/dist ./webapp/dist

# Render routes traffic to the EXPOSEd port; PORT override kept for other hosts.
EXPOSE 8000
# One process, two jobs: uvicorn in the main thread, aiogram polling in its own
# thread with a supervisor that restarts it (and never takes the API down).
CMD python serve.py
