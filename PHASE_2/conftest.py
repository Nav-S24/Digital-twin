"""
Ensures the project root is on sys.path so `from src.x import y` and
`import api` work when pytest is invoked from any working directory.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
