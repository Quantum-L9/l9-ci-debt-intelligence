# CLAUDE.md — l9-ci-debt-intelligence

Operating contract for Claude Code and other coding agents in this repo. This
is the quick contract; authoritative governance and per-phase invariants live
in the files under **References**. On conflict, `AGENTS.md` and the accepted
ADRs win over this file.

## What this is

Fleet learning and prevention-artifact compiler for the L9 CI constellation.
It ingests canonical producer events, builds immutable snapshots, derives
deterministic learning metrics, compiles non-blocking prevention candidates,
publishes signed defense packs, and measures their effectiveness — as seven
sequential phases, INTEL-P0 … INTEL-P6.

Python `>=3.11`, `src/` layout, package `l9_debt_intelligence`, console entry
point `l9-intelligence`. Runtime deps: `jsonschema`, `PyYAML`, `duckdb`,
`pyarrow`, `cryptography`. Data models are stdlib frozen `dataclasses` — not
pydantic.

## Always

- Run the full local gate before proposing a change is done:
  `ruff check . && ruff format --check . && mypy && pytest -q`.
- Keep `from __future__ import annotations` and full type hints on every
  module — the `mypy` gate runs in `--strict` mode over `src/`.
- Each phase consumes only the **verified** output of the previous phase and
  hashes its own output; represent missing data explicitly as `unknown`.
- Reference SDK/intelligence schemas under `schemas/intelligence/`; never
  reproduce or redefine them inline.
- Record change through correction, retraction, or retirement events — never
  silently rewrite history (append-only).
- Keep ruff configuration in `ruff.toml` (single source of truth) and the
  `mypy` toolchain pins in `requirements-ci.txt`. A `[tool.ruff]` table in
  `pyproject.toml` would be silently ignored while `ruff.toml` exists.

## Never

- Mutate a source repository, push branches, or open/merge pull requests from
  inside the authoritative package (`tests/architecture/` enforces this).
- Import producer implementations, SDK private modules, or a scanner/parser
  natively; do not `import semgrep`.
- Activate blocking policy, edit Core governance, or promote a candidate — all
  generated rules stay in candidate state and recommendations stay advisory.
- Distribute corpus records, raw logs, source content, secrets, absolute
  paths, or developer identities in any snapshot, pack, or event.
- Add a runtime dependency, change a cache/identity/hashing scheme, or add a
  CLI subcommand without first checking `AGENTS.md` and the ADRs.

## Boundaries are tested

`tests/architecture/` asserts the authoritative package contains no mutation
behavior, no prohibited module names (`repair`, `mutation`, `branch`,
scanner/repository parsers), and no legacy-tool imports. Keep those green;
they are not advisory.

## CI reality

Workflows live in `.github/workflows/`:

- `Lint` — ruff check, ruff format check, and the strict `mypy` type gate
  (installs the project plus `requirements-ci.txt`).
- `Intelligence Phase 1` … `Phase 7` — path-filtered per-phase test suites.
- `Publish signed defense pack` — signed publication.

GitGuardian / Semgrep run as platform checks. Run the local gate yourself; a
green PR does not prove the code was type-checked unless the `mypy` job ran.

## References

- `AGENTS.md` — full agent governance and the per-phase INTEL-P0..P6 invariants.
- `ROADMAP.md` — implemented capability per phase.
- `README.md` — project overview, CLI reference, and repository layout.
- `docs/architecture/ADRs/` — accepted architecture decision records.
- `.l9/` — phase contracts, ownership, and compatibility registries.
- `pyproject.toml` — dependencies, `[tool.mypy]` config, and packaging.
