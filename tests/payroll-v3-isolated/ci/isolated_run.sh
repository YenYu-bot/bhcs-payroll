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
bash "$ROOT/harness/run_all.sh" "$ROOT/candidate" "$OUT/run"
