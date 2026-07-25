# l9-ci-debt-intelligence

Fleet learning and prevention-artifact compiler for the L9 CI constellation.

This repository owns **historical corpus learning** and **prevention-artifact
compilation**. It ingests canonical producer events from across the fleet,
builds immutable snapshots, derives deterministic learning metrics, compiles
non-blocking prevention candidates, publishes signed defense packs, and closes
the loop by measuring their real-world effectiveness.

It is an **advisory, append-only** system. It never mutates source repositories,
never activates blocking policy, and never rewrites history — Core retains all
policy authority (see [`AGENTS.md`](AGENTS.md) and the ADRs under
[`docs/architecture/ADRs/`](docs/architecture/ADRs/)).

- Python `>=3.11`, `src/` layout, package `l9_debt_intelligence`.
- Console entry point: `l9-intelligence`.
- Runtime dependencies: `jsonschema`, `PyYAML`, `duckdb`, `pyarrow`,
  `cryptography`. Data models are stdlib frozen `dataclasses`.

## Pipeline phases

The system is organized as seven sequential phases (INTEL-P0 … INTEL-P6). Each
phase consumes only the **verified** output of the previous one and hashes its
own output for tamper detection. Full per-phase invariants live in
[`AGENTS.md`](AGENTS.md); the implementation status is tracked in
[`ROADMAP.md`](ROADMAP.md).

| Phase | Concern | Key output |
| --- | --- | --- |
| **P0** | Schema federation | producer/SDK compatibility, corpus event envelope |
| **P1** | Reproducible ingestion | append-only ledger, content-addressed corpus records |
| **P2** | Immutable snapshots | hashed Parquet partitions, derived DuckDB projection |
| **P3** | Learning metrics | recurrence, co-occurrence, effort, effectiveness reports |
| **P4** | Rule compilation | non-blocking candidates + regression fixtures |
| **P5** | Signed publication | immutable `l9.debt-defense/v1` packs, Ed25519 signatures |
| **P6** | Closed-loop effectiveness | rule/pack effectiveness, advisory recommendations |

DuckDB is a rebuildable projection, not corpus authority. All generated rules
stay in candidate state. Recommendations are advisory only.

## Install

```bash
python -m pip install -e ".[dev]"
```

## CLI

All functionality is exposed through the `l9-intelligence` command (or
`python -m l9_debt_intelligence.cli`). Every subcommand emits a canonical JSON
document to stdout, or to `--output <path>` when given.

**P0–P1 — validation & ingestion**

```bash
l9-intelligence validate-event <event.json>
l9-intelligence ingest-event <event.json> --storage-root <dir>
l9-intelligence verify-store --storage-root <dir>
```

**P2 — snapshots**

```bash
l9-intelligence build-snapshot --storage-root <dir> --snapshots-root <dir>
l9-intelligence verify-snapshot <snapshot>
l9-intelligence create-duckdb-projection <snapshot> --database <db>
```

**P3 — analytics**

```bash
l9-intelligence build-analytics <snapshot> --analytics-root <dir>
l9-intelligence verify-analytics <analysis>
```

**P4 — compilation**

```bash
l9-intelligence compile-candidates <analysis> --compilation-root <dir>
l9-intelligence verify-compilation <compilation>
```

**P5 — publication**

```bash
l9-intelligence generate-publication-key --private-key <k> --public-key <k>
l9-intelligence assemble-defense-pack <compilation> --output-root <dir> \
    --version <v> --taxonomy-version <v>
l9-intelligence sign-defense-pack <build_result> --private-key <k> \
    --channel <experimental|shadow|stable> --publication-manifest <path>
l9-intelligence verify-defense-pack <publication_manifest> <archive>
l9-intelligence update-defense-channel <publication_manifest> \
    --channel <c> --channel-index <path>
l9-intelligence retire-defense-pack <publication_manifest> \
    --reason <r> --issuer <i> --ledger <path>
```

**P6 — effectiveness**

```bash
l9-intelligence ingest-effectiveness-outcome <event.json> --store-root <dir>
l9-intelligence build-effectiveness-report --store-root <dir> \
    --defense-pack <pack> --reports-root <dir>
l9-intelligence verify-effectiveness-report <report_directory>
l9-intelligence compare-effectiveness --baseline <report> --current <report>
```

## Repository layout

```
.l9/                     phase contracts, ownership, and compatibility registries
schemas/intelligence/    versioned JSON Schemas (referenced, never reproduced)
src/l9_debt_intelligence/
  contracts/             P0 schema federation and event validation
  ingestion/             P1 deterministic append-only ingestion
  snapshots/             P2 immutable Parquet snapshots + DuckDB projection
  analytics/             P3 deterministic learning metrics
  compilation/           P4 candidate prevention-rule compilation
  publication/           P5 signed defense-pack publication
  effectiveness/         P6 closed-loop effectiveness measurement
  cli.py                 the l9-intelligence entry point
tests/                   phase test suites + architecture boundary tests
docs/architecture/ADRs/  accepted architecture decision records
```

## Development

Run the local gate before proposing a change is done:

```bash
ruff check .          # lint (config in ruff.toml)
ruff format --check . # formatting
mypy                  # strict static types over src/ (config in pyproject.toml)
pytest -q             # full suite
```

- Ruff settings live in [`ruff.toml`](ruff.toml) (single source of truth).
- The strict `mypy` gate installs its runner and stubs from
  [`requirements-ci.txt`](requirements-ci.txt).
- Keep `from __future__ import annotations` and full type hints on every module.
- Architecture boundary tests (`tests/architecture/`) forbid repository
  mutation, branch pushing, scanner-native parsing, and SDK/producer private
  imports from the authoritative package. Preserve those boundaries.

## Continuous integration

GitHub Actions workflows live in [`.github/workflows/`](.github/workflows/):

- `Lint` — ruff check, ruff format check, and the strict mypy type gate.
- `Intelligence Phase 1` … `Phase 7` — path-filtered per-phase test suites.
- `Publish signed defense pack` — signed publication workflow.

## License

Proprietary. See [`LICENSE`](LICENSE).
