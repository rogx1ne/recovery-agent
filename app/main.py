"""
main.py — FastAPI application entrypoint.

Wires together:
  - Database initialisation (create_all on startup)
  - All routers under /api/v1/
  - Root health-check endpoint
  - Swagger UI auto-generated at /docs
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import init_db
from app.routers import audit, demo, metrics, recovery, transactions, webhooks

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)
settings = get_settings()


# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Replaces deprecated @app.on_event('startup'/'shutdown')."""
    logger.info("Initialising database tables...")
    init_db()
    logger.info("Database ready. App environment: %s", settings.app_env)
    yield
    # shutdown logic can go here if needed


# ─── App instance ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="Recovery Agent",
    description=(
        "An autonomous agent that detects failed Razorpay payments, classifies the "
        "root cause, applies a bounded recovery action, and logs every decision with "
        "reasoning to an immutable audit trail.\n\n"
        "All Razorpay calls use **test-mode** credentials — no real money moves."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# ─── Middleware ───────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Lock down in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ──────────────────────────────────────────────────────────────────

API_PREFIX = "/api/v1"

app.include_router(transactions.router, prefix=API_PREFIX)
app.include_router(recovery.router, prefix=API_PREFIX)
app.include_router(audit.router, prefix=API_PREFIX)
# NOTE: mounted as /stats (not /metrics) — ad blockers block URLs containing "metrics"
app.include_router(metrics.router, prefix=API_PREFIX)
app.include_router(webhooks.router, prefix=API_PREFIX)
app.include_router(demo.router, prefix=API_PREFIX)


# ─── Root ─────────────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"], summary="Health check")
def root():
    return {
        "service": "recovery-agent",
        "status": "ok",
        "environment": settings.app_env,
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"], summary="Liveness probe")
def health():
    return {"status": "ok"}
