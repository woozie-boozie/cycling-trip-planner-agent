.PHONY: install dev test lint format clean docker-build docker-run

PYTHON ?= python3.13
VENV   ?= .venv
PIP    := $(VENV)/bin/pip
PY     := $(VENV)/bin/python

$(VENV)/bin/activate:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip

install: $(VENV)/bin/activate
	$(PIP) install -e ".[dev]"

dev:
	$(VENV)/bin/uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

test:
	$(VENV)/bin/pytest -v

lint:
	$(VENV)/bin/ruff check src tests
	$(VENV)/bin/mypy src

format:
	$(VENV)/bin/ruff format src tests
	$(VENV)/bin/ruff check --fix src tests

clean:
	rm -rf $(VENV) .pytest_cache .ruff_cache .mypy_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

docker-build:
	docker build -t cycling-trip-planner-agent .

docker-run:
	docker run -p 8080:8080 --env-file .env cycling-trip-planner-agent
