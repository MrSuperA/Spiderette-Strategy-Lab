.PHONY: help install dev lint format test test-cov type-check build clean run cli

help:  ## Show this help
	@grep -E "^[a-zA-Z_-]+:.*?## .*\$\$" $(MAKEFILE_LIST) | sort | awk "BEGIN {FS = ":.*?## "}; {printf "[36m%-15s[0m %s
", $$1, $$2}"

install:  ## Install production dependencies
	pip install -e .

dev:  ## Install with dev dependencies
	pip install -e ".[dev]"

lint:  ## Run linter (ruff)
	ruff check src/ tests/
	ruff format --check src/ tests/

format:  ## Auto-format code
	ruff check --fix src/ tests/
	ruff format src/ tests/

test:  ## Run tests
	pytest tests/ -v --tb=short

test-cov:  ## Run tests with coverage report
	pytest tests/ -v --tb=short --cov=src --cov-report=term-missing --cov-report=html

type-check:  ## Run type checker (mypy)
	mypy src/ --ignore-missing-imports

build:  ## Build distribution packages
	python -m build

clean:  ## Remove build artifacts
	rm -rf dist/ build/ *.egg-info src/*.egg-info

run:  ## Start the application
	python main.py

pre-commit:  ## Install pre-commit hooks
	pre-commit install
