#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
OUT="$ROOT/evidence"
mkdir -p "$OUT"
# This script is already inside the fresh no-uplink network namespace, non-root, with a clean env.
ip -j address > "$OUT/net-address.json"
ip -j route > "$OUT/net-route.json"
python3 -I "$ROOT/ci/sandbox_gate.py" > "$OUT/sandbox-gate.txt" 2>&1
# Never reach test execution unless the independent sandbox gate succeeds.
node "$ROOT/candidate/tests/calculation-phase1.cjs" | tee "$OUT/calculation-results.txt"
node "$ROOT/candidate/tests/leave-settlement.cjs" | tee "$OUT/leave-results.txt"
node "$ROOT/candidate/tests/deferred-basis.cjs" | tee "$OUT/deferred-basis-results.txt"
RESULTS_JSON="$OUT/independent-leave.json" node "$ROOT/candidate/tests/independent-leave.cjs" | tee "$OUT/independent-leave.txt"
RESULTS_JSON="$OUT/independent-deferred.json" node "$ROOT/candidate/tests/independent-deferred.cjs" | tee "$OUT/independent-deferred.txt"
RESULTS_JSON="$OUT/idb-results.json" node "$ROOT/candidate/tests/indexeddb-integration/application.cjs" | tee "$OUT/idb-results.txt"
bash "$ROOT/harness/run_all.sh" "$ROOT/candidate" "$OUT/run"

node "$ROOT/candidate/tests/leave-types.cjs" | tee "$OUT/leave-types.txt"
RESULTS_JSON="$OUT/independent-types-gate.json" node "$ROOT/candidate/tests/independent-types-gate.cjs" | tee "$OUT/independent-types-gate.txt"

# Real DOM review actions against native IndexedDB, synthetic data only.
python3 -I "$ROOT/harness/supervise.py" --out "$OUT/ui-supervisor" --timeout 180 -- python3 -I "$ROOT/harness/native_ui_review.py" --candidate-root "$ROOT/candidate" --output "$OUT/calculation-ui" > "$OUT/calculation-ui.log" 2>&1

python3 -I "$ROOT/harness/supervise.py" --out "$OUT/leave-ui-supervisor" --timeout 360 -- python3 -I "$ROOT/harness/native_leave_ui.py" --candidate-root "$ROOT/candidate" --output "$OUT/leave-ui" > "$OUT/leave-ui.log" 2>&1

python3 -I "$ROOT/harness/supervise.py" --out "$OUT/leave-types-ui-supervisor" --timeout 420 -- python3 -I "$ROOT/harness/native_leave_types_ui.py" --candidate-root "$ROOT/candidate" --output "$OUT/leave-types-ui" > "$OUT/leave-types-ui.log" 2>&1
