.PHONY: install migrate revision seed run test lint fmt

install:
	uv sync

migrate:
	uv run alembic upgrade head

revision:
	uv run alembic revision --autogenerate -m "$(m)"

seed:
	uv run python scripts/seed.py

run:
	uv run uvicorn app.main:app --reload

test:
	uv run pytest -q

lint:
	uv run ruff check .
	uv run ruff format --check .

fmt:
	uv run ruff check --fix .
	uv run ruff format .
