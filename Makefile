.PHONY: install migrate seed run test lint fmt dev-db

install:
	python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"

migrate:
	alembic upgrade head

revision:
	alembic revision --autogenerate -m "$(m)"

seed:
	python -m app.seed

run:
	uvicorn app.main:app --reload

test:
	pytest -q

lint:
	ruff check app tests

fmt:
	ruff check --fix app tests
