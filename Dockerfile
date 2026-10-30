# Repo-root Dockerfile for hosts that build from the repository root (e.g. Render).
# backend/Dockerfile stays for fly.io/Railway (root dir = backend).
# Same image, only the COPY paths are prefixed with backend/.
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

# Render routes traffic to the EXPOSEd port; PORT override kept for other hosts.
EXPOSE 8000
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
