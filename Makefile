# graderproof make targets (docs/BUILD_BRIEF.md section 10.1 step 7).
# Targets that are not built yet run tools/stub.py and fail, so no gate can pass by accident.

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

UV ?= uv
RUN := $(UV) run --frozen
PY ?= python3

.PHONY: help setup doctor test lint typecheck ci demo prereg-verify claimcheck freshness \
	citecheck secrets-scan budget review report reproduce ship-check

help: ## list targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/:.*## /\t/'

setup: ## create the dev environment from uv.lock
	$(UV) sync --locked

doctor: ## detect Docker, GPU, RAM, disk, claude CLI, local models, sandboxes, free tiers
	$(PY) tools/doctor.py --apply-caps --json runs/doctor/latest.json

test: ## pytest with line coverage (coverage.json, junit.xml)
	$(RUN) pytest -q --cov --cov-report=term --cov-report=json:coverage.json --junitxml=junit.xml

lint: ## ruff check, ruff format --check, no em dashes
	$(RUN) ruff check .
	$(RUN) ruff format --check .
	$(RUN) python tools/style_check.py

typecheck: ## mypy --strict on the package, tools, and tests
	$(RUN) mypy --strict src/graderproof tools tests

ci: lint typecheck test demo ## everything CI runs

demo: ## offline demo from recorded fixtures (output must equal tests/golden/demo_output.txt)
	@GRADERPROOF_NO_MODEL_CALLS=1 $(RUN) graderproof demo --check tests/golden/demo_output.txt

prereg-verify: ## preregistration chain and ordering
	$(PY) tools/prereg.py verify

claimcheck: ## every result number traces to a banked artifact
	@$(PY) tools/stub.py claimcheck G10

freshness: ## re-derive every live number
	@$(PY) tools/stub.py freshness G10

citecheck: ## validate artifacts/citecheck.json offline
	@$(PY) tools/stub.py citecheck G13

secrets-scan: ## scan tracked files and history for secrets
	$(PY) tools/secrets_scan.py

budget: ## cash and cap usage
	$(PY) tools/budget.py

review: ## validate and print the latest independent review
	$(PY) tools/review.py

report: ## figures and docs/REPORT.md from artifacts
	@$(PY) tools/stub.py report G13

reproduce: ## regenerate every figure and table from artifacts
	@$(PY) tools/stub.py reproduce G13

ship-check: ## all 14 gates on a fresh clone
	$(PY) tools/ship_check.py
