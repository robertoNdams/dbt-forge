# Contributing

Thanks for taking the time to contribute. This project follows a fairly standard PR-on-feature-branch workflow.

## Development setup

```bash
git clone https://github.com/robertoNdams/dbt-forge.git
cd dbt-forge

# Install package + all dev tooling
uv pip install -e ".[dev]"

# Wire up pre-commit hooks
pre-commit install
```

## Running checks locally

```bash
pytest tests/unit                     # fast unit suite
pytest -m integration                 # end-to-end against dbt-duckdb
ruff check src tests                  # lint
ruff format --check src tests         # format check
mypy                                  # type check
```

`pre-commit run --all-files` will run the same hooks CI runs.

## Branch workflow

1. Branch from `dev`: `git checkout -b feat/short-description dev`
2. Open the PR against `dev`. CI must be green before merge.
3. `main` is updated from `dev` at release time and tagged with `vX.Y.Z`.

## Commit messages

We don't enforce Conventional Commits, but consistency helps the changelog. Suggested prefixes:

- `feat:` new functionality
- `fix:` bug fix
- `refactor:` code change without behavior change
- `docs:` README / docs / comments
- `test:` test additions/changes
- `ci:` CI workflow / tooling changes
- `chore:` everything else

## Adding a new template

See [`docs/EXTENDING.md`](docs/EXTENDING.md). In short:

1. Add `render_<name>.sql` under `dbt/dbt_forge/macros/templates/`
2. Provide both `render_<name>` (dispatch entry) and `default__render_<name>` (impl)
3. Add render assertions to `tests/unit/test_renders.py`
4. Document the template in `docs/TEMPLATES.md` and `README.md`'s template tree

## Releasing

Maintainer only:

1. Update `pyproject.toml` `project.version`
2. Add a `## X.Y.Z — <title>` section to `CHANGELOG.md`
3. Merge `dev` into `main`
4. Tag and push: `git tag vX.Y.Z && git push origin vX.Y.Z`

The release workflow handles the rest.
