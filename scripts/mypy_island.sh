#!/usr/bin/env bash
# Blocking mypy gate for the type-checked "island" of modules.
#
# The MassGen codebase is largely untyped (~2300 mypy errors repo-wide), so a
# full mypy gate is not yet feasible. Instead we enforce mypy on a curated set of
# clean modules and expand it over time (the "ratchet"). New type errors in these
# modules fail the gate; the rest of the repo is covered by a non-blocking CI job.
#
# Scoping is by output-filtering (not --follow-imports alone) because mypy can
# leak errors from silently-followed imports depending on package layout.
set -uo pipefail

ISLAND=(
  massgen/backend/_excluded_params.py
  massgen/cli/_constants.py
  massgen/cli/env.py
  massgen/cli/mode_flags.py
  massgen/cli/planning.py
  massgen/agent_config.py
)

out="$(uv run mypy "${ISLAND[@]}" --follow-imports=silent --no-error-summary 2>&1)"
# Keep only error lines located in island files.
errs="$(printf '%s\n' "$out" | grep -E 'error:' | grep -F -f <(printf '%s\n' "${ISLAND[@]}"))"

if [ -n "$errs" ]; then
  echo "mypy island gate FAILED — fix these or shrink the island:"
  printf '%s\n' "$errs"
  exit 1
fi
echo "mypy island gate: clean (${#ISLAND[@]} modules)"
