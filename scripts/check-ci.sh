#!/usr/bin/env bash
set -euo pipefail

uv sync --all-extras
uv run ruff check src/
uv run pytest tests/ -v

# Template guard: verify the skill's reference template still imports against
# the working-copy framework (catches API drift between framework and skill).
uv run python -m compileall -q skill/template/src
uv run python -c "import sys; sys.path.insert(0, 'skill/template'); import src.main"
