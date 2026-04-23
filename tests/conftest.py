"""Shared pytest fixtures and path setup."""

import sys
from pathlib import Path

# Ensure the repo root is importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
