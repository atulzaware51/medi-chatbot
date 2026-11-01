"""FastAPI application entry point for Medibot."""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router

app = FastAPI(
    title="Medibot API",
    description=(
        "A document-grounded AI assistant using "
        "retrieval-augmented generation (RAG)."
    ),
    version="0.1.0",
)

app.include_router(chat_router)
app.include_router(auth_router)
app.include_router(admin_router)


@app.middleware("http")
async def normalize_api_prefix(request: Request, call_next):
    """Map frontend /api requests to existing backend API routes."""
    path = request.scope["path"]
    if path == "/api":
        request.scope["path"] = "/"
    elif path.startswith("/api/"):
        request.scope["path"] = path[4:]
    return await call_next(request)


@app.get("/health", tags=["Health"])
def health() -> dict[str, str]:
    """Provide a simple health status."""
    return {"status": "healthy"}


frontend_dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"

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
