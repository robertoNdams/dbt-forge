"""
Minimal harness to render dbt-forge macros under plain Jinja2.

Strategy
--------
1. Concatenate every macro file into one big template module.
2. Compile it once via `env.from_string(...).module` — that gives us a
   ModuleType whose attributes are the top-level macros.
3. Stub `adapter.dispatch(name, ns)` so it resolves to the same module's
   `default__<name>` if present, else `<name>`. This mimics dbt's behavior
   closely enough for our purposes — overrides aren't tested here.
4. Stub `exceptions.raise_compiler_error`, `log`, and `print`.

Limitations
-----------
- We don't model `modules.os`, `modules.io` (we don't use them anyway).
- The `dbt_forge` namespace is simulated by a proxy that looks up names on
  the same module — i.e. we resolve `dbt_forge.foo` like dbt would resolve
  `dbt_forge.foo` from another `dbt_forge` macro: as a sibling.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, StrictUndefined


class CompilerError(Exception):
    pass


def _collect_macros(macros_root: Path) -> str:
    parts: list[str] = []
    for p in sorted(macros_root.rglob("*.sql")):
        parts.append(f"{{# === {p.relative_to(macros_root)} === #}}\n")
        parts.append(p.read_text())
        parts.append("\n")
    return "".join(parts)


def build():
    """Return an object with .render_macro(name, model_cfg) and .prints."""
    macros_root = Path(__file__).resolve().parents[1] / "dbt" / "dbt_forge" / "macros"
    source = _collect_macros(macros_root)

    env = Environment(
        undefined=StrictUndefined,
        keep_trailing_newline=False,
        extensions=["jinja2.ext.do"],
    )

    state = {"prints": [], "logs": []}

    def _print(msg, *_, **__):
        state["prints"].append(str(msg))
        return ""

    def _log(msg, info=False):
        state["logs"].append(str(msg))
        return ""

    def _raise(msg):
        raise CompilerError(msg)

    # Pass 1: compile with placeholders; we need `module` first to wire up
    # adapter.dispatch and dbt_forge proxy that reference `module` itself.
    env.globals.update(
        {
            "exceptions": type("E", (), {"raise_compiler_error": staticmethod(_raise)})(),
            "log": _log,
            "print": _print,
        }
    )

    holder: dict[str, Any] = {}

    class DispatchProxy:
        def __getattr__(self, name: str):
            module = holder.get("module")
            if module is None:
                raise CompilerError("module not yet built")
            for cand in (f"default__{name}", name):
                if hasattr(module, cand):
                    return getattr(module, cand)
            raise CompilerError(f"dbt_forge.{name} not found")

    class AdapterStub:
        @staticmethod
        def dispatch(name: str, ns: str = "dbt_forge"):
            module = holder.get("module")
            for cand in (f"default__{name}", name):
                if hasattr(module, cand):
                    return getattr(module, cand)
            raise CompilerError(f"adapter.dispatch could not resolve '{name}'")

    env.globals["adapter"] = AdapterStub()
    env.globals["dbt_forge"] = DispatchProxy()

    tmpl = env.from_string(source)
    holder["module"] = tmpl.module

    class Harness:
        prints = state["prints"]
        logs = state["logs"]

        def reset(self):
            state["prints"].clear()
            state["logs"].clear()

        def call(self, macro_name: str, *args, **kwargs):
            mod = holder["module"]
            fn = getattr(mod, macro_name, None) or getattr(mod, f"default__{macro_name}", None)
            if fn is None:
                raise AttributeError(f"No macro {macro_name}")
            return str(fn(*args, **kwargs))

    return Harness()


if __name__ == "__main__":
    h = build()
    cfg = {
        "name": "stg_orders",
        "source": "raw.orders",
        "select_columns": ["*"],
        "filters": [],
        "metrics": [],
        "breakdown_by": [],
        "thresholds": [],
        "sort_by": [],
        "include_sources": [],
    }
    print(h.call("render_base_select", cfg))
