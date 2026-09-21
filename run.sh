#!/usr/bin/env bash
set -e

# Setup venvs if missing
[ ! -d ".venv-docling" ] && python3 -m venv .venv-docling && .venv-docling/bin/pip install -r requirements_docling.txt
[ ! -d ".venv-deepseek" ] && python3 -m venv .venv-deepseek && .venv-deepseek/bin/pip install -r requirements_deepseek.txt

# Run full extraction only if --skip-extract is not passed
if [ "$1" != "--skip-extract" ]; then
    echo "==> Running extractions..."
    .venv-docling/bin/python -m app.extract_docling
    .venv-deepseek/bin/python -m app.extract_deepseek
else
    echo "==> Skipping extraction. Using existing artifacts."
fi

# Run downstream pipeline
echo "==> Running downstream pipeline..."
.venv-deepseek/bin/python -m app.pipeline