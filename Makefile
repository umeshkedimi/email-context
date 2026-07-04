.PHONY: install migrate revision seed run test lint fmt

install:
	uv sync

migrate:
	uv run alembic upgrade head

revision:
	uv run alembic revision --autogenerate -m "$(m)"

seed:
	uv run python -m app.seed

run:
	uv run uvicorn app.main:app --reload

test:
	uv run pytest -q

lint:
	uv run ruff check app tests

fmt:
	uv run ruff check --fix app tests
