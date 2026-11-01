"""
app/main.py — FastAPI application entry point.

Run locally (from backend/, venv active):
    uvicorn app.main:app --reload --port 8000
Docs UI: http://localhost:8000/docs
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import webapp
from app.config import get_settings
from app.routers import (
    admin,
    auth,
    bot_internal,
    certificates,
    content,
    exams,
    leaderboard,
    me,
    quiz,
)

settings = get_settings()

app = FastAPI(
    title="EduQuest API",
    version="0.1.0",
    description="EduQuest Mini App backend: auth, lessons, quizzes, stars.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth.router)
app.include_router(content.router)
app.include_router(quiz.router)
app.include_router(me.router)
app.include_router(leaderboard.router)
app.include_router(certificates.router)
app.include_router(exams.router)
app.include_router(bot_internal.router)
app.include_router(admin.router)


@app.get("/api/health", tags=["meta"])
def health() -> dict:
    """Liveness probe + used by deployment checks."""
    return {"ok": True, "service": "eduquest-backend"}


# Registered LAST on purpose: the SPA catch-all must never shadow an API route.
# It only mounts when a compiled Mini App (webapp/dist) is present — in the
# Docker image the build stage always produces one; without it the API is
# unchanged (tests, backend-only deployments).
if webapp.register_webapp(app):
    logging.getLogger("eduquest").info(
        "Mini App servis qilinmoqda: %s", webapp.find_dist()
    )
