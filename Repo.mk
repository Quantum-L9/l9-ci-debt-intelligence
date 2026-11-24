# Repository-owned implementation of the make-v2 execution phases.
#
# CI parity:
#   setup     -> the install steps of l9-lint-test.yml
#   validate  -> byte-compile and import the package
#   check     -> ruff check and ruff format --check
#   test-fast -> the bounded pull-request selection
#   test      -> the full pytest suite
#
# Core runs each phase as its own make process, so every recipe resolves the
# environment it needs rather than relying on state a previous phase exported.

PYTHON ?= python3
VENV := $(CURDIR)/.venv
BIN := $(VENV)/bin
export PATH := $(BIN):$(PATH)

.PHONY: repo-setup repo-validate repo-check repo-test-fast repo-test

repo-setup: ## Create .venv and install the project with dev extras
	@test -x "$(BIN)/python" || $(PYTHON) -m venv "$(VENV)"
	@"$(BIN)/pip" install --quiet --upgrade pip
	@"$(BIN)/pip" install --quiet -e ".[dev]"

repo-validate: ## Byte-compile and import the package
	@python -m compileall -q src
	@python -c "import l9_debt_intelligence"

repo-check: ## Ruff lint and format check
	@ruff check .
	@ruff format --check .

repo-test-fast: ## Bounded pull-request selection
	pytest tests/contracts tests/ingestion tests/snapshots -q

repo-test: ## Full pytest suite
	pytest -q
