"""
FastAPI application — changelog tool web UI.

Run (development):
    uvicorn web.app:app --reload --host 0.0.0.0 --port 8000

The existing CLI (python3 changelog.py) is UNCHANGED and remains fully functional.
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from web.db import init_db
from web.routes.jobs import router as jobs_router
from web.routes.config import router as config_router

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    init_db()
    yield


app = FastAPI(
    title="Changelog Tool",
    description="Web UI for generating and distributing changelogs",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(jobs_router)
app.include_router(config_router)


@app.get("/health")
def health_check():
    """Liveness probe — confirms server is running."""
    return {"status": "ok"}


@app.get("/")
def serve_ui():
    """Serve the operator web UI."""
    return FileResponse(STATIC_DIR / "index.html")


# Mount static assets after explicit routes so they don't shadow /health or /config
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
