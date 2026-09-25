.PHONY: help run sync lint format test md-lint md-format tofu-fmt tofu-validate compose-up compose-down

help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Python:"
	@echo "  run           Run the local RSS feed extractor"
	@echo "  sync          Synchronize and install dependencies using uv"
	@echo "  lint          Run linter and formatting checks"
	@echo "  format        Format Python code with ruff"
	@echo "  test          Run unit tests with pytest"
	@echo ""
	@echo "Markdown:"
	@echo "  md-lint       Lint markdown files using markdownlint-cli"
	@echo "  md-format     Format and fix markdown files using markdownlint-cli"
	@echo ""
	@echo "OpenTofu:"
	@echo "  tofu-fmt      Format OpenTofu configuration files"
	@echo "  tofu-validate Initialize and validate OpenTofu configuration"
	@echo ""
	@echo "Compose:"
	@echo "  compose-up    Run the full pipeline stack locally via podman compose"
	@echo "  compose-down  Tear down the local podman compose stack"

# ==============================================================================
# Python
# ==============================================================================

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

# ==============================================================================
# Markdown
# ==============================================================================

md-lint:
	npx markdownlint-cli "**/*.md" --ignore node_modules --ignore .venv

md-format:
	npx markdownlint-cli --fix "**/*.md" --ignore node_modules --ignore .venv

# ==============================================================================
# OpenTofu
# ==============================================================================

tofu-fmt:
	tofu fmt -recursive infra/

tofu-validate:
	cd infra && tofu init -backend=false && tofu validate

# ==============================================================================
# Compose
# ==============================================================================

compose-up:
	podman compose up --build

compose-down:
	podman compose down
