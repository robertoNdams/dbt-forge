# `dbt-forge lineage`

Inspect upstream and downstream dependencies of any node in your dbt project — without spinning up `dbt docs` or running a query.

```bash
dbt-forge lineage <model_name> [options]
```

Works on any dbt project, not just ones using dbt-forge YAML. It reads `target/manifest.json` (and runs `dbt parse` for you if it doesn't exist).

---

## Quickstart

```bash
$ dbt-forge lineage fct_revenue_per_customer

fct_revenue_per_customer
├── upstream
│   └── stg_orders
│       └── source: raw.orders
└── downstream
    └── rpt_top_customers
        └── executive_dashboard
```

With file paths:

```bash
$ dbt-forge lineage fct_revenue_per_customer --show-config

fct_revenue_per_customer  [models/generated/fct_revenue_per_customer.sql]
├── upstream
│   └── stg_orders  [models/generated/stg_orders.sql]
│       └── source: raw.orders  [models/sources.yml]
└── downstream
    └── rpt_top_customers  [models/marts/rpt_top_customers.sql]
```

---

## Options

| Option | Default | Description |
| --- | --- | --- |
| `--upstream / --no-upstream` | upstream | Show ancestors |
| `--downstream / --no-downstream` | downstream | Show descendants |
| `--depth N` | unlimited | Limit hops from the root |
| `--show-config` | off | Show the file path of each node |
| `--format ascii\|mermaid` | ascii | Output format |
| `--project-dir PATH` | `.` | dbt project root |
| `--target-dir PATH` | `<project>/target` | Where `manifest.json` lives |
| `--profiles-dir PATH` | dbt default | Forwarded to `dbt parse` |
| `--no-parse` | off | Don't auto-run `dbt parse` |

---

## Mermaid output

Paste the output into any Markdown file (PR description, Notion, README):

```bash
$ dbt-forge lineage fct_revenue_per_customer --format mermaid

graph LR
    model_jaffle_shop_fct_revenue_per_customer["fct_revenue_per_customer"]
    source_jaffle_shop_raw_orders[("source: raw.orders")]
    model_jaffle_shop_stg_orders["stg_orders"]
    model_jaffle_shop_rpt_top_customers["rpt_top_customers"]
    exposure_jaffle_shop_executive_dashboard{{"executive_dashboard"}}

    source_jaffle_shop_raw_orders --> model_jaffle_shop_stg_orders
    model_jaffle_shop_stg_orders --> model_jaffle_shop_fct_revenue_per_customer
    model_jaffle_shop_fct_revenue_per_customer --> model_jaffle_shop_rpt_top_customers
    model_jaffle_shop_rpt_top_customers --> exposure_jaffle_shop_executive_dashboard

    classDef focus fill:#fef3c7,stroke:#f59e0b,stroke-width:2px;
    class model_jaffle_shop_fct_revenue_per_customer focus
```

Sources render as cylinders, exposures as hexagons, the focused model is highlighted.

---

## Notes

- **Tests and analyses are hidden by default.** They create lots of edges without adding lineage information; we skip `test` and `analysis` nodes during traversal.
- **Ambiguous short names**: if two nodes share the same short name (e.g. one model and one seed both called `customers`), `dbt-forge lineage` will print both unique IDs and exit. Pass the full unique ID (`model.<project>.<name>`) to disambiguate.
- **External packages**: the manifest includes upstream packages, so lineage that crosses package boundaries (e.g. into `dbt_utils`) is fully visible.
