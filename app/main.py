"""FastAPI application entry point for Medibot."""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.auth import router as auth_router
from app.api.admin import router as admin_router
from app.api.chat import router as chat_router
from app.db import SessionLocal, get_db
from app.auth import purge_expired_data

logger = logging.getLogger(__name__)


async def _retention_worker() -> None:
    """Run retention cleanup at startup and every six hours."""
    while True:
        try:
            await asyncio.to_thread(_purge_expired_data)
        except Exception as exc:
            logger.error("Scheduled retention cleanup failed (%s).", type(exc).__name__)
        await asyncio.sleep(6 * 60 * 60)


def _purge_expired_data() -> None:
    with SessionLocal() as db:
        purge_expired_data(db)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    cleanup_task = asyncio.create_task(_retention_worker())
    try:
        yield
    finally:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass

app = FastAPI(
    title="Medibot API",
    description=(
        "A document-grounded AI assistant using "
        "retrieval-augmented generation (RAG)."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(chat_router)
app.include_router(auth_router)
app.include_router(admin_router)


@app.middleware("http")
async def normalize_api_prefix(request: Request, call_next):
    """Strip the Vite proxy prefix so frontend and backend routes align."""
    path = request.scope["path"]
    if path == "/api":
        request.scope["path"] = "/"
    elif path.startswith("/api/"):
        request.scope["path"] = path[4:]
    return await call_next(request)


@app.get("/health", tags=["Health"])
def health() -> dict[str, str]:
    """Provide a process liveness status."""
    return {"status": "healthy"}


@app.get("/ready", tags=["Health"])
def readiness(db: Session = Depends(get_db)) -> dict[str, str]:
    """Verify that the application database is reachable."""
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Application database is unavailable.",
        ) from exc
    return {"status": "ready"}


frontend_dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"

# Serve the production React build when present; during development Vite serves it separately.
if frontend_dist.is_dir():
    app.mount(
        "/",
        StaticFiles(directory=str(frontend_dist), html=True),
        name="frontend",
    )
else:
    @app.get("/", tags=["Health"])
    def health_check() -> dict[str, str]:
        """Development fallback when the React build is unavailable."""
        return {"status": "ok", "service": "Medibot API"}
