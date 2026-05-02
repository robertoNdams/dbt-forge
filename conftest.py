"""
Pytest configuration.

Adds the `tests/` directory to sys.path so test modules can import the
shared `jinja_harness` helper without packaging it.
"""

from __future__ import annotations

import sys
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent / "tests"
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))
