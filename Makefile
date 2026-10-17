SHELL := /bin/bash
export UV_NO_ENV_FILE := 1
# Compose must never implicitly load a developer's .env file.
COMPOSE := docker compose --env-file /dev/null -f docker-compose.yml
export DATABASE_URL ?= postgresql+psycopg://afterward@127.0.0.1:5432/afterward
export DATABASE_URL_TEST ?= postgresql+psycopg://afterward@127.0.0.1:5432/afterward

.PHONY: setup db-up db-down run test test-fast lint fmt proof ci worktree merge requirements
setup:
	uv sync --frozen
	uv run --frozen pre-commit install
	uv export --frozen --no-dev --no-emit-project --no-hashes -o requirements.txt > /dev/null

db-up:
	$(COMPOSE) up -d --wait postgres

db-down:
	$(COMPOSE) down

run:
	uv run --frozen uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --proxy-headers

test:
	uv run --frozen pytest -m 'not network'

test-fast:
	uv run --offline --frozen pytest -m 'not db and not network and not slow'

lint:
	uv run --offline --frozen ruff check .
	uv run --offline --frozen ruff format --check .

fmt:
	uv run --offline --frozen ruff check --fix .
	uv run --offline --frozen ruff format .

proof:
	uv run --frozen python -m app.engine.proofs

ci: lint test

requirements:
	uv export --frozen --no-dev --no-emit-project --no-hashes -o requirements.txt > /dev/null

worktree:
	@bash scripts/agent_worktree.sh "$(SLICE)"

merge:
	@bash scripts/merge_slice.sh "$(SLICE)"
