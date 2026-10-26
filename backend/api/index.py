"""Vercel serverless function entry point for FastAPI backend.

Automatically detected by Vercel's Python runtime. Exposes ASGI app instance.
"""

import os
from pathlib import Path
import sys

# Ensure backend root directory is on sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from main import app  # noqa: E402
