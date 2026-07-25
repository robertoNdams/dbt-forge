# dbt-forge

**A CI-first quality CLI for dbt.** Inspect lineage, gate PRs on risk, audit technical debt, and generate boilerplate models — all from a single command-line tool. Works on any dbt project. No lock-in.

[![CI](https://img.shields.io/github/actions/workflow/status/robertoNdams/dbt-forge/ci.yml?branch=dev)](https://github.com/robertoNdams/dbt-forge/actions)
[![License](https://img.shields.io/badge/license-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)
[![dbt](https://img.shields.io/badge/dbt-1.7+-orange.svg)](https://getdbt.com)

---

## Why dbt-forge?

dbt gives you SQL, tests, version control. But three problems persist across every project:

- **Boilerplate** — 50-80% of staging models are near-identical `SELECT … WHERE … cast` blocks that get copy-pasted by hand.
- **Silent risk** — a change to a staging model can break a dashboard three hops downstream. Nothing warns you before production.
- **Invisible debt** — untested models, undocumented sources, dead code accumulate over time and no one has a full picture.

dbt-forge is the CLI that fixes all three, without asking you to migrate anything.

---

## Install

1. Install the CLI 

```bash
uv pip install git+https://github.com/your-org/dbt-forge.git 
# Or, locally from the repo root: 
uv pip install -e . 
```

2. Add the dbt package to your project 

`packages.yml`:

```yaml
packages:
  - git: https://github.com/your-org/dbt-forge.git
    subdirectory: dbt
```

```bash
dbt deps
```

Requires Python 3.10+ and dbt-core 1.7+ (works with any adapter: DuckDB, Snowflake, BigQuery, Postgres, Redshift…).

---

## The 5 commands at a glance

| Command | What it does | Full docs |
|---|---|---|
| `dbt-forge lineage <model>` | Show upstream/downstream dependencies as ASCII or Mermaid | [docs/LINEAGE.md](docs/LINEAGE.md) |
| `dbt-forge impact <model>` | Quantify the downstream risk of a change, gate CI with `--fail-on` | [docs/IMPACT.md](docs/IMPACT.md) |
| `dbt-forge audit` | Static linter for tests, documentation, structure (8 rules) | [docs/AUDIT.md](docs/AUDIT.md) |
| `dbt-forge generate` | YAML → SQL + schema.yml, composable templates, override per adapter | [docs/DSL.md](docs/DSL.md) · [docs/TEMPLATES.md](docs/TEMPLATES.md) · [docs/EXTENDING.md](docs/EXTENDING.md) |
| `dbt-forge validate` | Validate a `generate` config without invoking dbt | See DSL.md |

---

## `dbt-forge lineage` — see the DAG in your terminal

**The 30-second first use.** Point it at any dbt project (yours, or a fork you're exploring) and see who depends on what:

```bash
$ dbt-forge lineage fct_revenue_per_customer --show-config

fct_revenue_per_customer  [models/marts/fct_revenue_per_customer.sql]
├── upstream
│   └── stg_orders  [models/staging/stg_orders.sql]
│       └── source: raw.orders  [models/sources.yml]
└── downstream
    ├── rpt_top_customers  [models/marts/rpt_top_customers.sql]
    │   └── exposure: executive_dashboard
    └── fct_high_value_revenue  [models/marts/fct_high_value_revenue.sql]
```

No server, no build, no browser. Runs in ~200ms. Also emits **Mermaid** for pasting in PR descriptions or Notion:

```bash
dbt-forge lineage fct_revenue_per_customer --format mermaid
```

**Options**: `--upstream/--no-upstream`, `--downstream/--no-downstream`, `--depth N`, `--show-config`, `--format ascii|mermaid`. Full reference: [docs/LINEAGE.md](docs/LINEAGE.md).

---

## `dbt-forge impact` — turn CI into a quality gate

You're modifying `stg_orders`. Before you merge, what do you risk breaking?

```bash
$ dbt-forge impact stg_orders

Modifying stg_orders would affect 3 downstream nodes:

  IMMEDIATE (1 hop)
    ✓ fct_revenue_per_customer  [tests: 3]  [exposures: 1: executive_dashboard]
    ⚠ fct_high_value_revenue    [tests: 1]  [exposures: 0]  (no pk test)

  DOWNSTREAM (2+ hops)
    ✗ rpt_top_customers         [tests: 0]  [exposures: 1: executive_dashboard]
                                             (no tests; 1 exposure downstream)

  Risk surface: 1 critical, 1 warning
```

The **`--fail-on critical`** flag turns this into a hard CI gate:

```yaml
# .github/workflows/dbt-impact.yml
- run: |
    for f in $(git diff --name-only origin/main HEAD | grep '\.sql$'); do
      dbt-forge impact "$(basename "$f" .sql)" --fail-on critical || exit 1
    done
```

Blocks any merge that would leave an untested model feeding a dashboard — without running the models. Zero warehouse compute cost, runs in seconds, replaces expensive alternatives that do data-diff on every PR.

**JSON output** for orchestration:

```bash
dbt-forge impact stg_orders --format json | jq '.summary'
# { "without_tests": 1, "exposures_affected": 1, "by_level": {...} }
```

Full reference: [docs/IMPACT.md](docs/IMPACT.md).

---

## `dbt-forge audit` — measure technical debt

Run periodically to see the full health of your project:

```bash
$ dbt-forge audit

Scanned 47 models, ran 8 rules: AUDIT001..AUDIT008

CRITICAL  (3)
  AUDIT002  Model 'fct_revenue' has tests but none on its primary key 'order_id'
           → Add unique + not_null test on 'order_id' in models/marts/schema.yml

WARNING   (12)
  AUDIT001  Model 'stg_events' has no tests defined
  AUDIT005  Source 'raw.archived_orders' is declared but never referenced
  AUDIT006  Model 'stg_users' is a view consumed by 5 downstream models — every query re-executes its SQL
  ...

INFO      (24)
  AUDIT003  Model 'fct_internal_metrics' has no description
  AUDIT007  Model 'legacy_pipeline' is never referenced and feeds no exposure
  ...

Summary: 39 findings across 28 nodes (3 critical, 12 warning, 24 info)
```

**8 rules** across three categories:

| Category | Rules |
|---|---|
| Tests & coverage | AUDIT001 (no tests), AUDIT002 (no PK test) |
| Documentation | AUDIT003 (no model description), AUDIT004 (no column descriptions) |
| Structure | AUDIT005 (orphan source), AUDIT006 (hot view), AUDIT007 (dead model), AUDIT008 (undocumented exposure deps) |

Every finding comes with an actionable suggestion. Also works as a CI gate:

```bash
dbt-forge audit --fail-on critical
```

Full reference: [docs/AUDIT.md](docs/AUDIT.md).

---

## `dbt-forge generate` — write models in YAML, get dbt-native SQL

For teams that want to eliminate staging boilerplate. Write your model as YAML:

```yaml
# config/models.yml
models:
  - name: fct_revenue_per_customer
    source_model: stg_orders
    template: full_select
    select_columns: [customer_id]
    metrics:
      - {name: total_revenue, based_on: amount, operation: sum}
    breakdown_by: [customer_id]
    thresholds:
      - {metric: total_revenue, op: '>', value: 100}
    sort_by:
      - {metric: total_revenue, order: desc}
    columns_meta:
      - {name: customer_id, tests: [not_null, unique]}
      - {name: total_revenue, description: "Sum of paid orders"}
```

Get dbt-native SQL and schema.yml, ready to `dbt run`:

```bash
$ dbt-forge generate --config config/models.yml --output-dir models/generated

  + models/generated/fct_revenue_per_customer.sql
  + models/generated/schema.yml
✓ Wrote 2 files to models/generated
```

**8 composable templates**, override-friendly per project or per adapter (Snowflake / BigQuery / DuckDB / Postgres). Pydantic-validated before invocation, DAG cycles caught before `dbt parse`. Not a scaffolder — a proper composition system.

See:
- [docs/DSL.md](docs/DSL.md) — the YAML DSL reference
- [docs/TEMPLATES.md](docs/TEMPLATES.md) — the 8 templates and how they compose
- [docs/EXTENDING.md](docs/EXTENDING.md) — writing your own templates or overriding defaults

---

## How dbt-forge fits in the 2026 dbt landscape

| Capability | dbt Core v2 | dbt Fusion | dbt Cloud | Recce/Datafold | **dbt-forge** |
|---|:---:|:---:|:---:|:---:|:---:|
| CLI, scriptable, single binary | partial | partial (IDE) | no | partial | **yes** |
| Lineage table-level | via dbt docs | yes | yes | yes | **yes** |
| Lineage column-level | no | yes | yes | yes | roadmap |
| Impact analysis (risk-based) | no | technical only | yes | data-diff only | **yes** |
| CI gate `--fail-on` with JSON | no | no | partial | partial | **yes** |
| YAML-native model generation | no (codegen only) | no | no | no | **yes** |
| Static audit / debt scoring | no | no | no | no | **yes** |
| Licence | Apache 2.0 | ELv2 + proprietary | proprietary | mixed | **Apache 2.0** |

**dbt-forge is complementary to dbt Fusion and dbt Cloud, not competing.** Use them alongside — dbt-forge fills the CI-first, open-source gap they leave.

---

## Quickstart on your existing project

Assumes you already have a dbt project with a working profile.

```bash
# 1. Install
pip install dbt-forge

# 2. Ensure a manifest exists (or let dbt-forge run `dbt parse` for you)
dbt parse

# 3. Explore
dbt-forge lineage stg_orders
dbt-forge impact stg_orders
dbt-forge audit

# 4. When ready, wire the impact gate into CI
# See docs/IMPACT.md for a full GitHub Actions example.
```

No YAML to write, no models to rewrite. Every command works on the manifest dbt already generates.

---

## Try the example

The repo ships a full example project (DuckDB, jaffle-shop-inspired) you can run end-to-end:

```bash
git clone https://github.com/robertoNdams/dbt-forge && cd dbt-forge
uv pip install -e ".[test]"
cd examples/jaffle_shop
dbt deps --profiles-dir=.
dbt seed --profiles-dir=.
dbt-forge generate --config config/models.yml --output-dir models/generated --project-dir . --profiles-dir=.
dbt run --profiles-dir=.
dbt-forge lineage fct_revenue_per_customer --project-dir . --profiles-dir=.
dbt-forge impact stg_orders --project-dir . --profiles-dir=.
dbt-forge audit --project-dir . --profiles-dir=.
```

---

## Documentation

Deep-dive references live in [`docs/`](docs/):

- **[LINEAGE.md](docs/LINEAGE.md)** — full options and Mermaid output reference for `dbt-forge lineage`
- **[IMPACT.md](docs/IMPACT.md)** — risk classification rules, JSON schema, CI integration recipes
- **[AUDIT.md](docs/AUDIT.md)** — 8 audit rules explained, workflows, tool comparison
- **[DSL.md](docs/DSL.md)** — the YAML config language for `dbt-forge generate`
- **[TEMPLATES.md](docs/TEMPLATES.md)** — the 8 built-in SQL templates and how they compose
- **[EXTENDING.md](docs/EXTENDING.md)** — how to write custom templates or override defaults for your adapter

---

## Contributing

PRs welcome. See the [test suite](tests/) for how things are structured — every command has its own sub-package under `src/dbt_forge_cli/` (e.g. `lineage_cli/`, `audit_cli/`) with isolated tests. New rules for `audit` are especially easy to add: subclass `AuditRule`, register it in the engine, done. See [docs/AUDIT.md](docs/AUDIT.md) section "Adding new rules".

For issues or feature requests, open a GitHub issue.

---

## License

Apache 2.0. See [LICENSE](LICENSE).
