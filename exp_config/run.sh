#!/usr/bin/env bash
set -euo pipefail

CONFIG="${1:-exp_config/claude.yaml}"
PROMPT_FILE="${2:-exp_config/prompt.txt}"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  MassGen Starting"
echo "  Config : $CONFIG"
echo "  Prompt : $(head -c 40 "$PROMPT_FILE" | tr '\n' ' ')..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

START_TIME=$(date +%s)

if uv run massgen --automation --config "$CONFIG" "$(cat "$PROMPT_FILE")"; then
    END_TIME=$(date +%s)
    ELAPSED=$((END_TIME - START_TIME))
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  SUCCESS - Run completed in ${ELAPSED}s"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
else
    END_TIME=$(date +%s)
    ELAPSED=$((END_TIME - START_TIME))
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  FAILED  - Exit code $? after ${ELAPSED}s"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    exit 1
fi
