"""
Phase 5 OBD Diagnostics Intelligence  –  App Entry Point
=========================================================
Run with:
    python app.py
    
Or with uvicorn directly:
    uvicorn app:app --host 0.0.0.0 --port 8000 --reload

Then visit:
    http://localhost:8000/docs   →  Swagger UI
    http://localhost:8000/redoc  →  ReDoc
"""

import os
import sys

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(__file__))

from api.routes import app   # noqa: F401  (re-exported for uvicorn)

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(
        'app:app',
        host    = '0.0.0.0',
        port    = 8000,
        reload  = False,   # set True during development
        log_level = 'info',
    )
