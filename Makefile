# Arzi — the single entry point for humans and automation. Run `make help`.
# Requires: uv, Node.js >= 22, npm, bash (Git Bash on Windows), gcloud for cloud targets.

SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

UV ?= uv
NPM ?= npm
API := api
CASE ?= case_a
WEB := web

.PHONY: help setup dev check lint typecheck test test-api test-rules test-web \
        test-e2e eval models demo-cases rules-demo openapi deploy billing-switch

help: ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-16s %s\n", $$1, $$2}'

setup: ## Install Python and Node dependencies and enable the git hooks
	git config core.hooksPath .githooks
	cd $(API) && $(UV) sync --locked
	cd $(WEB) && $(NPM) ci

dev: ## Run API (reload) and web (Vite) locally in replay mode
	trap 'kill 0' EXIT; \
	(cd $(API) && ARZI_LLM_MODE=replay $(UV) run uvicorn arzi.main:create_app --factory --reload --port 8000) & \
	(cd $(WEB) && $(NPM) run dev) & \
	wait

check: lint typecheck test ## Everything CI runs: lint, types, tests with coverage gates

lint: ## ruff (lint + format check), eslint, prettier
	cd $(API) && $(UV) run ruff check . ../scripts && $(UV) run ruff format --check . ../scripts
	cd $(WEB) && $(NPM) run --silent lint && $(NPM) run --silent format:check

typecheck: ## mypy --strict and tsc
	cd $(API) && $(UV) run mypy src tests ../scripts
	cd $(WEB) && $(NPM) run --silent typecheck

test: test-api test-rules test-web ## All unit and integration tests

test-api: ## pytest, overall coverage >= 85%
	cd $(API) && $(UV) run pytest --cov --cov-report=term-missing:skip-covered

test-rules: ## Rules engine coverage gate: 100% line + branch
	cd $(API) && $(UV) run pytest tests/unit/rules -q --cov=arzi.rules --cov-branch \
	  --cov-report=term-missing --cov-fail-under=100

test-web: ## vitest
	cd $(WEB) && $(NPM) run --silent test

test-e2e: ## Playwright against a local production build (installs Chromium on first run)
	cd $(WEB) && npx playwright install chromium && $(NPM) run --silent test:e2e

eval: ## Extraction and flag accuracy report -> evals/report.md
	cd $(API) && $(UV) run python ../evals/run.py

models: ## List Gemini models visible to GOOGLE_CLOUD_PROJECT (read-only)
	cd $(API) && $(UV) run python ../scripts/list_models.py $(MODELS_ARGS)

rules-demo: ## Print flags, totals and trace for a demo case (CASE=case_a|case_b|case_c)
	cd $(API) && $(UV) run python -m arzi.rules.cli ../demo_cases/$(CASE)/facts.json

demo-cases: ## Regenerate synthetic demo PDFs, facts and expected outputs (byte-stable)
	cd $(API) && $(UV) run python ../scripts/gen_demo_cases.py

openapi: ## Regenerate web/src/api/schema.d.ts from the FastAPI schema
	cd $(API) && $(UV) run python -c "import json, pathlib; from arzi.main import create_app; \
	  pathlib.Path('../$(WEB)/src/api/openapi.json').write_text( \
	  json.dumps(create_app(readiness_probes=[]).openapi(), indent=2) + '\n', newline='\n')"
	cd $(WEB) && $(NPM) run --silent openapi

deploy: ## Deploy to Cloud Run (asks for confirmation; spends money)
	bash infra/deploy.sh

billing-switch: ## Re-link the project to the owner's billing account (asks for confirmation)
	bash infra/billing_switch.sh
