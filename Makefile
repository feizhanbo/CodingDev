.PHONY: lint test lint-devpilot lint-shopflow test-devpilot test-shopflow

lint: lint-devpilot lint-shopflow

lint-devpilot:
	cd devpilot && uv run ruff check .

lint-shopflow:
	cd shopflow-order-service && uv run ruff check .

test: test-devpilot test-shopflow

test-devpilot:
	cd devpilot && uv run pytest

test-shopflow:
	cd shopflow-order-service && uv run pytest
