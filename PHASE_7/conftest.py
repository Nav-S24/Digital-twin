"""
Ensures the project root is on sys.path so `from services.x import y`,
`from data.loaders import ...`, `from routes.chat import ...` etc. work
when pytest is invoked from any working directory (mirrors the pattern
used in Phase 6's conftest.py for consistency across phases).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
