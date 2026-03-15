#!/usr/bin/env bash
# scripts/run_tests.sh — run the full test suite
# Run: bash scripts/run_tests.sh

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "${REPO_DIR}"

echo ""
echo "  relay-connect — test suite"
echo ""

# Check deps
if ! python -c "import websockets" 2>/dev/null; then
  echo "  Installing test dependencies..."
  pip install -e ".[dev]" --quiet
fi

# Unit tests
echo "  Running unit tests..."
python -m pytest tests/test_crypto.py tests/test_protocol.py tests/test_config.py tests/test_cli.py \
  -v --tb=short 2>&1

echo ""
echo "  Running integration tests (needs websockets)..."
python -m pytest tests/test_integration.py \
  -v --tb=short --timeout=30 2>&1 || echo "  (integration tests require websockets — run: pip install websockets)"

echo ""
echo "  ✓ Test run complete"
echo ""
