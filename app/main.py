"""
IDS Soft Biometric SDK v2.0 — Subscription-Based Multi-Tenant API

Run: uvicorn app.main:app --reload --port 8000
Swagger: http://localhost:8000/docs
"""

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.rate_limiter import limiter, rate_limit_exceeded_handler
from app.routers import admin, client_panel, face_match, search, subjects

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ── FastAPI App ──────────────────────────────────
app = FastAPI(
    title=settings.APP_TITLE,
    description=settings.APP_DESCRIPTION,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url=None,
    openapi_url="/openapi.json",
    openapi_tags=[
        {"name": "Face Match", "description": "1:1 face comparison — two images → similarity score."},
        {"name": "Subject Management", "description": "Create, list, delete subjects. Add face images."},
        {"name": "Face Search", "description": "1:N face identification — search against all enrolled subjects."},
        {"name": "System", "description": "Health check and system info."},
    ],
)

# ── Rate Limiter ─────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# ── CORS (mobile + web) ─────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Custom ReDoc ─────────────────────────────────
@app.get("/redoc", include_in_schema=False)
async def redoc_html():
    return get_redoc_html(
        openapi_url=app.openapi_url,
        title=app.title + " - ReDoc",
        redoc_js_url="https://unpkg.com/redoc@2.1.5/bundles/redoc.standalone.js",
    )

# ── Routers ──────────────────────────────────────
app.include_router(admin.router, include_in_schema=False)
app.include_router(client_panel.router, include_in_schema=False)
app.include_router(face_match.router)
app.include_router(subjects.router)
app.include_router(search.router)

# ── Static Files ─────────────────────────────────
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs")


@app.get("/admin-panel", include_in_schema=False)
async def admin_panel():
    """Super Admin Dashboard UI."""
    return FileResponse(os.path.join(static_dir, "admin.html"))


@app.get("/client-panel", include_in_schema=False)
async def client_panel_page():
    """Client Dashboard UI."""
    return FileResponse(os.path.join(static_dir, "client.html"))


@app.get("/health", tags=["System"], summary="Health Check")
async def health_check():
    return {
        "status": "healthy",
        "service": settings.APP_TITLE,
        "version": settings.APP_VERSION,
    }


@app.on_event("startup")
async def startup_event():
    logger.info("=" * 60)
    logger.info(f"  {settings.APP_TITLE} v{settings.APP_VERSION}")
    logger.info(f"  Swagger: http://localhost:{settings.PORT}/docs")
    logger.info(f"  ReDoc:   http://localhost:{settings.PORT}/redoc")
    logger.info("=" * 60)
    logger.info("Loading face models...")
    try:
        from app.face_engine import _get_detector, _get_embedder
        _get_detector()
        _get_embedder()
        logger.info("All models loaded!")
    except Exception as e:
        logger.warning(f"Model pre-loading deferred: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)
