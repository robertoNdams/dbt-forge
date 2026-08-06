"""
Audit CLI sub-package.

Provides `dbt-forge audit`: a static linter for dbt projects.

Each rule is a class that inherits from AuditRule and produces Finding objects
when scanning the manifest. The engine collects all findings and the renderers
present them as either an ASCII report or a JSON payload for CI consumption.

Adding a new rule:
  1. Create a new class inheriting AuditRule in the appropriate rules/ module
  2. Register it in AuditEngine.DEFAULT_RULES
  3. Add tests in tests/unit/test_audit_rules.py

Reuses the lineage_cli's ManifestLoader — no duplication of manifest parsing.
"""

from .engine import AuditEngine, AuditReport
from .rules.base import AuditRule, Finding, Severity

__all__ = [
    "AuditEngine",
    "AuditReport",
    "AuditRule",
    "Finding",
    "Severity",
]
