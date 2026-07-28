"""
main.py
=======
FastAPI application entry point for the Vehicle Digital Twin platform.

Run with:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload

The lifespan context manager initialises the Synchronizer (which loads
all 2000 vehicle twins) on startup and performs graceful cleanup on shutdown.
"""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router
from config.settings import (
    API_DESCRIPTION,
    API_HOST,
    API_PORT,
    API_TITLE,
    API_VERSION,
    CORS_ORIGINS,
    LOG_LEVEL,
)
from services.simulation_engine import get_simulation_engine
from services.synchronizer import get_synchronizer
from utils.helpers import setup_logging

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
setup_logging(LOG_LEVEL)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan (replaces deprecated on_event)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """
    Application lifespan handler.
    Startup  : initialise Synchronizer + SimulationEngine.
    Shutdown : log teardown (in-memory state is discarded).
    """
    logger.info("=" * 60)
    logger.info("Vehicle Digital Twin Platform — starting up")
    logger.info("=" * 60)

    # Initialise twin registry (loads and merges CSVs, builds 2000 twins)
    sync = get_synchronizer()
    sync.initialise()

    # Initialise simulation engine (attempts NASA C-MAPSS load)
    sim_engine = get_simulation_engine()
    logger.info("Simulation engine mode: %s", sim_engine.mode)

    logger.info("Startup complete. %d vehicle twins loaded.", sync.total_vehicles)
    logger.info("API docs available at http://%s:%d/docs", API_HOST, API_PORT)

    yield  # Application runs here

    logger.info("Vehicle Digital Twin Platform — shutting down")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title=API_TITLE,
    version=API_VERSION,
    description=API_DESCRIPTION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — allow React dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(router)


# ---------------------------------------------------------------------------
# Root redirect
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
async def root():
    return {
        "service": "Vehicle Digital Twin API",
        "version": API_VERSION,
        "docs":    "/docs",
        "health":  "/digital_twin/health",
    }


# ---------------------------------------------------------------------------
# Direct run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=API_HOST,
        port=API_PORT,
        reload=True,
        log_level=LOG_LEVEL.lower(),
    )
