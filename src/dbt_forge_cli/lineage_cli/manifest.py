"""
Reads and queries dbt's `manifest.json` artifact.

The manifest is produced by `dbt parse` (and any command that parses, like
`dbt compile`, `dbt run`, etc.). We treat it as the source of truth for the
project's DAG — including hand-written models, not just dbt-forge generated
ones.

Schema notes (manifest v12, dbt 1.7+):
  - nodes:        models, seeds, snapshots, tests, analyses, exposures-attached
  - sources:      external tables declared via sources.yml
  - exposures:    downstream consumers (dashboards, ML models, etc.)
  - parent_map:   unique_id -> list of upstream unique_ids
  - child_map:    unique_id -> list of downstream unique_ids

Unique IDs follow the convention:
  - model.<project>.<name>
  - source.<project>.<schema>.<table>
  - test.<project>.<name>
  - seed.<project>.<name>
  - snapshot.<project>.<name>
  - exposure.<project>.<name>
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ManifestError(RuntimeError):
    """Raised when the manifest cannot be loaded or parsed."""


class NodeNotFoundError(LookupError):
    """A name could not be resolved to a single manifest node."""


class AmbiguousNodeError(LookupError):
    """A short name matched more than one node."""

    def __init__(self, name: str, candidates: list[str]) -> None:
        super().__init__(
            f"Ambiguous name '{name}' matches {len(candidates)} nodes:\n"
            + "\n".join(f"  - {c}" for c in candidates)
            + "\n\nPass the full unique_id (e.g. 'model.<project>.<name>')."
        )
        self.candidates = candidates


@dataclass(frozen=True)
class ManifestNode:
    """A normalized view over a manifest entry.

    We collapse the differences between models, sources, seeds, etc. into a
    single shape so the graph layer doesn't care what kind of node it walks.
    """

    unique_id: str
    name: str
    resource_type: str  # model | source | seed | snapshot | test | exposure
    file_path: str      # original_file_path — relative to the dbt project root
    schema: str | None  # database schema; None for tests and exposures
    package_name: str

    @property
    def is_model(self) -> bool:
        return self.resource_type in {"model", "seed", "snapshot"}

    @property
    def display_name(self) -> str:
        """Human-friendly label, e.g. 'stg_orders' or 'source: raw.orders'."""
        if self.resource_type == "source":
            return f"source: {self.schema}.{self.name}" if self.schema else f"source: {self.name}"
        return self.name


class ManifestLoader:
    """
    Loads a manifest from disk and answers structural questions about it.

    Usage:
        loader = ManifestLoader.from_project(Path("."))
        node = loader.resolve("stg_orders")
        parents = loader.parents_of(node.unique_id)
    """

    def __init__(self, raw: dict[str, Any]) -> None:
        self._raw = raw
        self._nodes: dict[str, ManifestNode] = {}
        self._parent_map: dict[str, list[str]] = raw.get("parent_map", {})
        self._child_map: dict[str, list[str]] = raw.get("child_map", {})
        self._index_by_name: dict[str, list[str]] = {}

        self._ingest()

    @classmethod
    def from_path(cls, manifest_path: Path) -> ManifestLoader:
        if not manifest_path.exists():
            raise ManifestError(
                f"Manifest not found at {manifest_path}. "
                "Run `dbt parse` first, or pass --no-parse if you've already parsed."
            )
        try:
            raw = json.loads(manifest_path.read_text())
        except json.JSONDecodeError as e:
            raise ManifestError(f"Could not parse {manifest_path}: {e}") from e
        return cls(raw)

    @classmethod
    def from_project(
        cls,
        project_dir: Path,
        target_dir: Path | None = None,
        *,
        auto_parse: bool = True,
        profiles_dir: Path | None = None,
    ) -> ManifestLoader:
        """Load from `<project_dir>/<target_dir>/manifest.json`.

        If the manifest doesn't exist and `auto_parse` is True, run `dbt parse`
        to generate it. This is the default for the `lineage` / `impact`
        commands so first-time users don't need to know about dbt's artifacts.
        """
        target = target_dir or (project_dir / "target")
        manifest_path = target / "manifest.json"

        if not manifest_path.exists():
            if not auto_parse:
                raise ManifestError(
                    f"Manifest not found at {manifest_path} and --no-parse was set."
                )
            _run_dbt_parse(project_dir, profiles_dir)
            if not manifest_path.exists():
                raise ManifestError(
                    f"`dbt parse` ran but did not produce {manifest_path}. "
                    "Check the dbt logs."
                )

        return cls.from_path(manifest_path)

    def _ingest(self) -> None:
        for uid, node in self._raw.get("nodes", {}).items():
            self._register(_node_from_manifest_entry(uid, node))
        for uid, src in self._raw.get("sources", {}).items():
            self._register(_node_from_source_entry(uid, src))
        for uid, exp in self._raw.get("exposures", {}).items():
            self._register(_node_from_exposure_entry(uid, exp))

    def _register(self, node: ManifestNode) -> None:
        self._nodes[node.unique_id] = node
        self._index_by_name.setdefault(node.name, []).append(node.unique_id)

    # --- public read API ---------------------------------------------------

    def all_nodes(self) -> dict[str, ManifestNode]:
        return dict(self._nodes)

    def get(self, unique_id: str) -> ManifestNode | None:
        return self._nodes.get(unique_id)

    def resolve(self, name: str, *, prefer_resource: str = "model") -> ManifestNode:
        """Resolve a user-supplied name to a node.

        Accepts either a full unique_id (`model.foo.bar`) or a short name
        (`bar`). When a short name matches multiple candidates, we prefer
        nodes of `prefer_resource` type (default: model); if still ambiguous,
        we raise `AmbiguousNodeError`.
        """
        if name in self._nodes:
            return self._nodes[name]
        if "." in name:
            raise NodeNotFoundError(f"No node with unique_id '{name}'.")

        candidates = self._index_by_name.get(name, [])
        if not candidates:
            raise NodeNotFoundError(
                f"No node named '{name}'. Did you run `dbt parse` after your latest changes?"
            )
        if len(candidates) == 1:
            return self._nodes[candidates[0]]

        preferred = [c for c in candidates if self._nodes[c].resource_type == prefer_resource]
        if len(preferred) == 1:
            return self._nodes[preferred[0]]

        raise AmbiguousNodeError(name, candidates)

    def parents_of(self, unique_id: str) -> list[str]:
        return list(self._parent_map.get(unique_id, []))

    def children_of(self, unique_id: str) -> list[str]:
        return list(self._child_map.get(unique_id, []))

    # --- test & exposure lookups, used by `impact` ------------------------

    def tests_attached_to(self, unique_id: str) -> list[ManifestNode]:
        """Return test nodes whose parent_map includes the given unique_id."""
        result: list[ManifestNode] = []
        for test_uid, parents in self._parent_map.items():
            node = self._nodes.get(test_uid)
            if node is None or node.resource_type != "test":
                continue
            if unique_id in parents:
                result.append(node)
        return result

    def exposures_downstream_of(self, unique_ids: set[str]) -> list[ManifestNode]:
        """Return exposures reachable downstream from any of the given unique_ids.

        Walks `child_map` transitively, collecting any exposure encountered.
        """
        seen: set[str] = set()
        exposures: list[ManifestNode] = []
        stack: list[str] = list(unique_ids)
        while stack:
            uid = stack.pop()
            if uid in seen:
                continue
            seen.add(uid)
            for child in self._child_map.get(uid, []):
                child_node = self._nodes.get(child)
                if child_node is None:
                    continue
                if child_node.resource_type == "exposure":
                    exposures.append(child_node)
                else:
                    stack.append(child)
        return exposures


def _node_from_manifest_entry(uid: str, entry: dict[str, Any]) -> ManifestNode:
    return ManifestNode(
        unique_id=uid,
        name=entry.get("name", ""),
        resource_type=entry.get("resource_type", "model"),
        file_path=entry.get("original_file_path", entry.get("path", "")),
        schema=entry.get("schema"),
        package_name=entry.get("package_name", ""),
    )


def _node_from_source_entry(uid: str, entry: dict[str, Any]) -> ManifestNode:
    return ManifestNode(
        unique_id=uid,
        name=entry.get("name", ""),
        resource_type="source",
        file_path=entry.get("original_file_path", entry.get("path", "")),
        schema=entry.get("source_name") or entry.get("schema"),
        package_name=entry.get("package_name", ""),
    )


def _node_from_exposure_entry(uid: str, entry: dict[str, Any]) -> ManifestNode:
    return ManifestNode(
        unique_id=uid,
        name=entry.get("name", ""),
        resource_type="exposure",
        file_path=entry.get("original_file_path", entry.get("path", "")),
        schema=None,
        package_name=entry.get("package_name", ""),
    )


def _run_dbt_parse(project_dir: Path, profiles_dir: Path | None) -> None:
    dbt = shutil.which("dbt")
    if not dbt:
        raise ManifestError(
            "`dbt` CLI not found on PATH. Either install dbt-core + an adapter, "
            "or run with --no-parse and ensure target/manifest.json already exists."
        )
    cmd = [dbt, "parse", "--project-dir", str(project_dir)]
    if profiles_dir:
        cmd.extend(["--profiles-dir", str(profiles_dir)])
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise ManifestError(
            f"`dbt parse` failed (exit {proc.returncode}):\n"
            f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
        )
