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
RESULTS_JSON="$OUT/idb-results.json" node "$ROOT/candidate/tests/indexeddb-integration/application.cjs" | tee "$OUT/idb-results.txt"
bash "$ROOT/harness/run_all.sh" "$ROOT/candidate" "$OUT/run"

# Real DOM review actions against native IndexedDB, synthetic data only.
python3 -I "$ROOT/harness/supervise.py" --out "$OUT/ui-supervisor" --timeout 180 -- python3 -I "$ROOT/harness/native_ui_review.py" --candidate-root "$ROOT/candidate" --output "$OUT/calculation-ui" > "$OUT/calculation-ui.log" 2>&1
