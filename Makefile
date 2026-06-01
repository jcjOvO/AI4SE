.PHONY: dev test test-unit test-integration e2e lint type docker-build docker-run run clean lock-check

dev:
	uv sync --extra dev

test: test-unit
	uv run pytest -m "not e2e" -v

test-unit:
	uv run pytest tests/unit -v

test-integration:
	uv run pytest tests/integration -v

e2e:
	uv run pytest tests/e2e -v

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests

type:
	uv run mypy src

docker-build:
	docker build -t mini-agent .

docker-run:
	docker run -it --rm -v $(PWD):/workspace -e ANTHROPIC_API_KEY=$${ANTHROPIC_API_KEY} mini-agent

run: docker-build docker-run

lock-check:
	uv lock --check

clean:
	rm -rf .venv .pytest_cache .mypy_cache .ruff_cache
