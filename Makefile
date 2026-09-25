.PHONY: help run sync lint format test tofu-fmt tofu-validate

help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@echo "  run           Run the local RSS feed extractor"
	@echo "  sync          Synchronize and install dependencies using uv"
	@echo "  lint          Run linter and formatting checks"
	@echo "  format        Format code with ruff"
	@echo "  test          Run unit tests with pytest"
	@echo "  tofu-fmt      Format OpenTofu configuration files"
	@echo "  tofu-validate Initialize and validate OpenTofu configuration"

run:
	uv run python src/extractor.py

sync:
	uv sync

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .

test:
	uv run pytest

tofu-fmt:
	tofu fmt -recursive infra/

tofu-validate:
	cd infra && tofu init -backend=false && tofu validate
