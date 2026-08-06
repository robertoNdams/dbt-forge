# `dbt-forge audit`

Static linter for dbt projects. Scans your `manifest.json` and surfaces technical debt: missing tests, undocumented models, dead code, materialization mistakes. Designed to run in CI and as a recurring quarterly health check.

```bash
dbt-forge audit [options]
```

---

## Quickstart

```bash
$ dbt-forge audit

Scanned 47 models, ran 8 rules: AUDIT001, AUDIT002, ..., AUDIT008

CRITICAL  (3)
  AUDIT002  Model 'fct_revenue' has tests, but none on its primary key column 'order_id'
           → Add a 'unique' and 'not_null' test on column 'order_id' in models/marts/schema.yml
  ...

WARNING   (12)
  AUDIT001  Model 'stg_legacy_users' has no tests defined
           → Add at least a not_null + unique test on its primary key column in models/staging/stg_legacy_users.sql
  AUDIT005  Source 'raw.archived_orders' is declared but no model references it
           → Either reference it via {{ source('raw', 'archived_orders') }}, or remove it from models/sources.yml
  ...

INFO      (24)
  AUDIT003  Model 'fct_internal_metrics' has no description
           → Add a 'description:' field for 'fct_internal_metrics' in models/marts/schema.yml
  ...

Summary: 39 findings across 28 nodes (3 critical, 12 warning, 24 info)
```

---

## Rules

| Code | Severity | Description |
|---|---|---|
| AUDIT001 | warning | Model has no attached tests |
| AUDIT002 | **critical** | Model has tests but none on its primary key |
| AUDIT003 | info | Model has no description |
| AUDIT004 | info | Model has columns declared but they lack descriptions |
| AUDIT005 | warning | Source is declared but never referenced |
| AUDIT006 | warning | Model materialized as 'view' but consumed by 5+ downstream models |
| AUDIT007 | info | Model is never referenced and feeds no exposure |
| AUDIT008 | warning | Exposure depends on undocumented models |

### Rationale by category

**Tests & coverage** (AUDIT001, AUDIT002) — Untested models are silent risk. AUDIT002 is critical because PK violations cause downstream data corruption that's hard to diagnose after the fact.

**Documentation** (AUDIT003, AUDIT004) — Info severity. Important for collaboration and LLM-based tooling, but not blocking. AUDIT004 only fires when columns are *declared*, not when they're absent entirely (we don't punish "no columns declared yet").

**Structure & configuration** (AUDIT005–AUDIT008) — Project-level hygiene. AUDIT006 (hot view) and AUDIT008 (undocumented exposure deps) are warnings because they affect downstream consumers; AUDIT005 (orphan source) is a warning because it misleads new team members; AUDIT007 (dead models) is info because false positives are common (e.g., models accessed by ad-hoc queries outside the DAG).

---

## Options

| Option | Default | Description |
|---|---|---|
| `--select RULE,...` | all rules | Run only listed rule codes |
| `--exclude RULE,...` | nothing | Skip listed rule codes |
| `--severity-threshold critical\|warning\|info` | info | Hide findings below this level |
| `--format ascii\|json` | ascii | Output format |
| `--fail-on critical\|warning\|info` | never | Exit non-zero if max severity ≥ this |
| `--project-dir`, `--target-dir`, `--profiles-dir`, `--no-parse` | — | Same as `lineage` / `impact` |

---

## Common workflows

### Quarterly audit

Run with all rules at default threshold:

```bash
$ dbt-forge audit > audit-report.txt
```

Share with the team, plan a remediation sprint for `CRITICAL` and high-impact `WARNING` items.

### CI gate: never let critical findings into main

```yaml
# .github/workflows/dbt-audit.yml
- run: dbt-forge audit --fail-on critical
```

Blocks merge if any AUDIT002 (missing PK test) finding exists. Light enough to run on every PR.

### Focus on tests only

```bash
$ dbt-forge audit --select AUDIT001,AUDIT002
```

Skips documentation and structure rules — useful when running on a project with known documentation debt that you're not addressing this quarter.

### Strict mode (PR comment)

```bash
$ dbt-forge audit --severity-threshold warning --format json | jq '.findings | length'
```

Get a count of warning+critical findings for PR comments or Slack notifications.

---

## JSON output schema

```json
{
  "rules_run": ["AUDIT001", "AUDIT002", "..."],
  "models_scanned": 47,
  "findings_count": 39,
  "findings": [
    {
      "rule": "AUDIT002",
      "severity": "critical",
      "node": {
        "name": "fct_revenue",
        "unique_id": "model.jaffle_shop.fct_revenue",
        "resource_type": "model",
        "file_path": "models/marts/fct_revenue.sql"
      },
      "message": "Model 'fct_revenue' has tests, but none on its primary key column 'order_id'",
      "suggestion": "Add a 'unique' and 'not_null' test on column 'order_id' in models/marts/schema.yml"
    }
  ],
  "summary": {
    "by_severity": {"critical": 3, "warning": 12, "info": 24},
    "models_affected": 28,
    "max_severity": "critical"
  }
}
```

Pipe through `jq` for ad-hoc analysis:

```bash
# Count critical findings per rule
$ dbt-forge audit --format json | jq '[.findings[] | select(.severity == "critical")] | group_by(.rule) | map({rule: .[0].rule, count: length})'

# List all models without descriptions
$ dbt-forge audit --select AUDIT003 --format json | jq '.findings[].node.name'
```

---

## Comparison with other tools

| Tool | Audit-like capability | Limit |
|---|---|---|
| `dbt-checkpoint` | Linter as pre-commit hooks | Each rule = a separate hook to install/configure |
| `dbt-project-evaluator` | Audit package within dbt itself | Lives inside `dbt run-operation`, not a standalone CLI |
| Elementary | Runtime test failures, freshness | Observability *after* prod, not static *before* prod |
| dbt Cloud Catalog | Lineage, documentation surface | Subscription required, no CI gate |

`dbt-forge audit` is a unified CLI with one binary, one install, one report — and a `--fail-on` for CI integration that the alternatives don't provide.

---

## Known limitations & future work

- **PK detection is heuristic** (first column declared in schema.yml). Models that declare PK via `meta` or with custom test names are missed. Configurable in V2.
- **AUDIT006 threshold (5)** is hard-coded. Configurable via `.dbt-forge.yml` in V2.
- **No auto-fix** in V1. `--fix-suggestions` flag (apply YAML edits) planned for V2.
- **No project-wide config exclusions** — use `--exclude` per-invocation for now.
