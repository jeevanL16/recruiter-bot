.PHONY: help up down run seed test lint format typecheck check

help:
	@echo "Available commands:"
	@echo "  make up         Start Docker Compose services"
	@echo "  make down       Stop Docker Compose services"
	@echo "  make run        Run FastAPI dev server locally"
	@echo "  make seed       Run database seed script"
	@echo "  make test       Run pytest test suite"
	@echo "  make lint       Run ruff linter and formatter check"
	@echo "  make format     Format code with ruff"
	@echo "  make typecheck  Run mypy type checker"
	@echo "  make check      Run lint, typecheck, and tests"

up:
	docker compose up -d --build

down:
	docker compose down

run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

seed:
	python -m app.seed

test:
	pytest -v

lint:
	ruff check .
	ruff format --check .

format:
	ruff format .
	ruff check --fix .

typecheck:
	mypy --strict app

check: lint typecheck test
