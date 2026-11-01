"""
app/webapp.py — serve the compiled Mini App from the API itself.

WHY THIS EXISTS
---------------
The Mini App used to live on a separate static host, so every UI change needed a
second deployment step. When that host's publish API became unavailable the
Telegram "Mini App" button kept serving a stale bundle while the code in git was
already newer. The API, in contrast, redeploys on every git push — so shipping
the compiled SPA inside the same image means one push updates API and Mini App
together, and same-origin calls need no CORS allowance at all.

SAFETY
------
`webapp/dist` only exists in the production image (the Dockerfile builds it in a
node stage). Locally it exists only after `npm run build`, and in tests it may be
absent entirely. When the folder is missing nothing is mounted and the API
behaves exactly as before — no routes, no side effects.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Non-GET requests must keep answering 404 (not 405) on unknown paths, exactly
# like before the catch-all existed.
_METHODS = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"]


def dist_candidates() -> list[Path]:
    """Where a built Mini App may live, most explicit first."""
    env = os.getenv("WEBAPP_DIST", "").strip()
    if env:
        return [Path(env)]
    here = Path(__file__).resolve()
    # repo checkout: <root>/backend/app/webapp.py  -> <root>/webapp/dist
    # docker image: /app/app/webapp.py            -> /app/webapp/dist
    return [here.parents[2] / "webapp" / "dist", here.parents[1] / "webapp" / "dist"]


def find_dist() -> Path | None:
    """Return the dist folder holding an index.html, or None."""
    for candidate in dist_candidates():
        index = candidate / "index.html"
        if index.is_file():
            return candidate.resolve()
    return None


def register_webapp(app: FastAPI, dist: Path | None = None) -> bool:
    """Mount hashed assets + SPA fallback. Returns True when a build was found."""
    root = dist or find_dist()
    if root is None:
        return False
    index = root / "index.html"
    if not index.is_file():
        return False

    assets = root / "assets"
    if assets.is_dir():
        # File names are content-hashed (index-CVf1lVih.js), so a stale copy can
        # never be picked up; index.html is the only thing revalidated (below).
        app.mount("/assets", StaticFiles(directory=assets), name="mini-app-assets")

    @app.api_route("/{full_path:path}", methods=_METHODS, include_in_schema=False)
    def spa(full_path: str, request: Request):
        """Unknown non-API path -> the SPA shell; API paths stay JSON 404."""
        if request.method not in ("GET", "HEAD") or full_path.startswith("api/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        if full_path:
            candidate = (root / full_path).resolve()
            # is_relative_to guards against ../ traversal escaping dist.
            if candidate.is_file() and candidate.is_relative_to(root):
                return FileResponse(candidate)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return True
