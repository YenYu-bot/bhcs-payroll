#!/usr/bin/env bash
# provision.sh path normalization test (uses --check-paths: no network, no install). Usage: test_provision_paths.sh <candidate-root>
set -u; T="$(cd "$(dirname "$0")" && pwd -P)"; ABS="$(cd "$1" && pwd -P)"; ok=1
check(){ out="$(cd "$1" && bash "$T/provision.sh" "$2" --check-paths 2>&1)"; rc=$?
  got="$(printf '%s\n' "$out" | sed -n 's/^CAND=//p')"; echo "cwd=$1 arg=$2 rc=$rc CAND=$got"
  [ $rc -eq 0 ] && [ "$got" = "$ABS" ] || { echo "  FAIL"; ok=0; }; }
check "$ABS/.." "$(basename "$ABS")"        # relative from parent
check "$ABS" "."                              # relative '.'
check "$ABS/tests" ".."                       # relative '..' from a subdirectory
check / "$ABS"                                # absolute
out="$(bash "$T/provision.sh" /nonexistent-cand --check-paths 2>&1)"; rc=$?; echo "missing-dir rc=$rc"; [ $rc -eq 2 ] || { echo "  FAIL"; ok=0; }
[ $ok -eq 1 ] && { echo PROVISION_PATHS_SELFTEST PASS; exit 0; } || { echo PROVISION_PATHS_SELFTEST FAIL; exit 1; }
