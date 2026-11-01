# EduQuest FastAPI backend — production image (fly.io / Railway / any Docker host)
# Build happens in the CLOUD (fly.io / Railway), so you do NOT need Docker locally.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first (better layer caching).
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy only what the app needs to RUN.
# NOTE: .env is intentionally NOT copied — secrets are injected as environment
# variables by the platform (fly secrets / Railway variables). See .dockerignore.
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic

# fly.io / Railway inject PORT; default to 8000 for local runs.
# NOTE: this image is API-only. The Telegram bot lives in the repo-root
# Dockerfile (Render), which runs API + bot in one process via serve.py.
EXPOSE 8000
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
