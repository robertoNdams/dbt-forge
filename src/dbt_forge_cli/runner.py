"""
Runner: invokes `dbt run-operation generate_model` with the validated config
serialized as JSON in `--args`, then parses dbt's stdout for blocks emitted
by the `emit_file` / `emit_dry_run` macros and performs the file writes.

Wire format emitted by dbt-side macros:

    <<<DBT_FORGE_FILE path="models/generated/foo.sql">>>
    ...rendered content...
    <<<DBT_FORGE_END>>>

Or for dry-run:

    <<<DBT_FORGE_DRYRUN path="models/generated/foo.sql">>>
    ...rendered content...
    <<<DBT_FORGE_END>>>

This split (macro renders, Python writes) is intentional:
- dbt's Jinja sandbox does not expose `os` / `io`;
- it preserves the manifest's "no business logic in Python" rule — we only
  match a delimiter and write bytes.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .config import ForgeConfig

# ---------------------------------------------------------------------------
# Wire protocol
# ---------------------------------------------------------------------------

_BLOCK_RE = re.compile(
    r"<<<DBT_FORGE_(?P<kind>FILE|DRYRUN) path=\"(?P<path>[^\"]+)\">>>\n"
    r"(?P<body>.*?)"
    r"<<<DBT_FORGE_END>>>",
    re.DOTALL,
)


@dataclass
class EmittedFile:
    kind: str  # "FILE" | "DRYRUN"
    path: Path
    body: str


@dataclass
class RunnerOptions:
    project_dir: Path
    profiles_dir: Path | None
    output_dir: Path
    overwrite: bool
    dry_run: bool


@dataclass
class RunResult:
    written: list[Path] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)  # already exist, no overwrite
    dry_run_files: list[EmittedFile] = field(default_factory=list)
    raw_stdout: str = ""
    raw_stderr: str = ""


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class DbtNotFoundError(RuntimeError):
    pass


class DbtRunError(RuntimeError):
    def __init__(self, returncode: int, stdout: str, stderr: str) -> None:
        super().__init__(
            f"dbt run-operation failed with exit code {returncode}.\n"
            f"--- stdout ---\n{stdout}\n--- stderr ---\n{stderr}"
        )
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class FileExistsConflict(RuntimeError):
    def __init__(self, path: Path) -> None:
        super().__init__(
            f"Refusing to overwrite '{path}'. Pass --overwrite to replace."
        )
        self.path = path


# ---------------------------------------------------------------------------
# dbt invocation
# ---------------------------------------------------------------------------


def _ensure_dbt() -> str:
    path = shutil.which("dbt")
    if not path:
        raise DbtNotFoundError(
            "`dbt` CLI not found on PATH. Install dbt-core + an adapter "
            "(e.g. `uv pip install dbt-duckdb`)."
        )
    return path


def _run_dbt(cfg: ForgeConfig, opts: RunnerOptions) -> subprocess.CompletedProcess[str]:
    dbt = _ensure_dbt()
    payload = {
        "config": cfg.model_dump(mode="json"),
        "options": {
            "output_dir": str(opts.output_dir),
            "overwrite": opts.overwrite,
            "dry_run": opts.dry_run,
        },
    }
    cmd = [
        dbt,
        "--no-use-colors",  # keep stdout clean for parsing
        "run-operation",
        "generate_model",
        "--args",
        json.dumps(payload),
        "--project-dir",
        str(opts.project_dir),
    ]
    if opts.profiles_dir:
        cmd.extend(["--profiles-dir", str(opts.profiles_dir)])

    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise DbtRunError(proc.returncode, proc.stdout, proc.stderr)
    return proc


# ---------------------------------------------------------------------------
# Stdout parsing + file writes
# ---------------------------------------------------------------------------


def _parse_emitted_blocks(stdout: str) -> list[EmittedFile]:
    out: list[EmittedFile] = []
    for m in _BLOCK_RE.finditer(stdout):
        body = m.group("body")
        # Strip exactly one trailing newline that the macro added before the END marker
        if body.endswith("\n"):
            body = body[:-1]
        out.append(EmittedFile(kind=m.group("kind"), path=Path(m.group("path")), body=body))
    return out


def _write_file(path: Path, body: str, overwrite: bool) -> bool:
    """Returns True if written, False if skipped (existed & no overwrite)."""
    if path.exists() and not overwrite:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def invoke_generate_model(cfg: ForgeConfig, opts: RunnerOptions) -> RunResult:
    proc = _run_dbt(cfg, opts)
    blocks = _parse_emitted_blocks(proc.stdout)

    result = RunResult(raw_stdout=proc.stdout, raw_stderr=proc.stderr)

    if opts.dry_run:
        result.dry_run_files = [b for b in blocks if b.kind == "DRYRUN"]
        return result

    file_blocks = [b for b in blocks if b.kind == "FILE"]
    if not file_blocks:
        # dbt ran clean but emitted no blocks — surface this loudly.
        raise DbtRunError(
            returncode=0,
            stdout=proc.stdout,
            stderr="dbt-forge: no DBT_FORGE_FILE blocks found in dbt stdout. "
            "Is the dbt_forge package installed in your project?",
        )

    for blk in file_blocks:
        # Resolve relative paths against the dbt project_dir
        target = blk.path
        if not target.is_absolute():
            target = (opts.project_dir / target).resolve()
        if _write_file(target, blk.body, opts.overwrite):
            result.written.append(target)
        else:
            result.skipped.append(target)

    if result.skipped and not opts.overwrite:
        # Mirror manifest behavior: refuse silently-incomplete generation.
        first = result.skipped[0]
        raise FileExistsConflict(first)

    return result
