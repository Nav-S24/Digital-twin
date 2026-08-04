"""
Phase 7 - Standalone app entrypoint.

If you already have an existing FastAPI app, skip this file and instead
add to your existing main.py:

    from phase7.routes.chat import router as phase7_chat_router
    app.include_router(phase7_chat_router)

This file is provided so Phase 7 can be run and tested on its own.
"""
from dotenv import load_dotenv

load_dotenv()
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes.chat import router as chat_router

app = FastAPI(title="Vehicle Digital Twin - Phase 7 Assistant")

# Allow the Vite dev server (default port 5173) to call this API during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)


@app.get("/health")
def health():
    return {"status": "ok"}
