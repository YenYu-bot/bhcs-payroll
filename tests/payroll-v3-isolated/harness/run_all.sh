#!/usr/bin/env bash
# Full rerunnable validation sequence (non-root). Usage: run_all.sh <candidate-root> <new-output-dir>
# Final exit (from aggregate.py): 0 all PASS | 1 any FAIL (incl. hash mismatch, self-test failure, wrong empty-selection
# exit, supervisor failure) | 3 nothing failed but the full suite was BLOCKED. BSDK_RUNNER may point to an alternative
# runner (used only by test_run_all.py to inject controlled outcomes).
set -u
T="$(cd "$(dirname "$0")" && pwd -P)"
[ $# -eq 2 ] || { echo "usage: run_all.sh <candidate-root> <new-output-dir>"; exit 2; }
C="$(cd "$1" && pwd -P)" || exit 2; mkdir "$2" || exit 2; O="$(cd "$2" && pwd -P)"
RUNNER="${BSDK_RUNNER:-$T/bsdk_runner.py}"
EXP=ff5399e07c7e023de6db13c3983acec5d991d82de54e25782109851a7ea64782
sha256sum "$C/index.html" | cut -d' ' -f1 > "$O/index-sha-before.txt"
python3 -I "$T/netpolicy.py" > "$O/netpolicy-selftest.txt" 2>&1; echo $? > "$O/netpolicy-selftest.exit"
python3 -I "$T/test_supervisor.py" > "$O/supervisor-selftest.txt" 2>&1; echo $? > "$O/supervisor-selftest.exit"
bash "$T/test_provision_paths.sh" "$C" > "$O/provision-paths.txt" 2>&1; echo $? > "$O/provision-paths.exit"
python3 -I "$T/sandbox_check.py" > "$O/sandbox-check.txt" 2>&1; echo $? > "$O/sandbox-check.exit"
python3 -I "$T/supervise.py" --out "$O/sup-empty" --timeout 120 -- python3 -I "$RUNNER" --candidate-root "$C" --output "$O/out-empty" --case NO_SUCH_CASE > /dev/null; echo $? > "$O/sup-empty.exit"
python3 -I "$T/supervise.py" --out "$O/sup-full" --timeout "${BSDK_FULL_TIMEOUT:-2700}" -- python3 -I "$RUNNER" --candidate-root "$C" --output "$O/out-full" > /dev/null; echo $? > "$O/sup-full.exit"
sha256sum "$C/index.html" | cut -d' ' -f1 > "$O/index-sha-after.txt"
python3 -I "$T/aggregate.py" "$O" "$EXP"; rc=$?
echo "run_all exit=$rc"; exit $rc
