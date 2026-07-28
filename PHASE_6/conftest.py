"""
Ensures the project root is on sys.path so `from app.x import y` works when
pytest is invoked from any working directory (e.g. `pytest tests/`).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
