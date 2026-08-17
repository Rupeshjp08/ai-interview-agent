"""
AI Interview Agent — Backend Entry Point
=========================================
Initialises the FastAPI application, registers routers, and configures CORS.

Exposed endpoints:
  GET  /                          → health check
  GET  /api/candidates            → list candidate profiles
  GET  /api/candidates/{id}       → get a single candidate profile
  POST /api/interview             → drive an interview turn (AI-powered)
  GET  /api/sessions/{id}         → get session status
  DELETE /api/sessions/{id}       → delete / reset a session
"""

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import interview

# ---------------------------------------------------------------------------
# Environment & Logging
# ---------------------------------------------------------------------------
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown hooks)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run startup tasks, then yield, then run shutdown tasks."""
    api_key = os.getenv("GOOGLE_API_KEY")
    if api_key:
        logger.info("GOOGLE_API_KEY loaded (length=%d).", len(api_key))
    else:
        logger.warning(
            "GOOGLE_API_KEY is NOT set. "
            "The /api/interview endpoint will fail until the key is provided."
        )
    yield  # Application runs
    logger.info("AI Interview Agent is shutting down.")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="AI Interview Agent",
    description=(
        "An AI agent that conducts personalised, realistic, multi-turn "
        "technical interviews based on a candidate's learning journey through "
        "a 31-day AI Engineering Cohort."
    ),
    version="0.2.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",  # CRA / other dev servers
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(interview.router, prefix="/api")


# ---------------------------------------------------------------------------
# Root health check
# ---------------------------------------------------------------------------
@app.get("/", tags=["Health"])
async def root() -> dict:
    """Simple health-check endpoint."""
    api_key_set = bool(os.getenv("GOOGLE_API_KEY"))
    return {
        "status": "ok",
        "message": "AI Interview Agent API is running.",
        "version": "0.2.0",
        "google_api_key_configured": api_key_set,
    }


@app.get("/health", tags=["Health"])
async def health() -> dict:
    """Detailed health check."""
    api_key = os.getenv("GOOGLE_API_KEY")
    return {
        "status": "healthy",
        "version": "0.2.0",
        "google_api_configured": bool(api_key),
        "google_api_key_length": len(api_key) if api_key else 0,
    }
