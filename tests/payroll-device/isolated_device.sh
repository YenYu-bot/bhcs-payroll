#!/usr/bin/env bash
set -euo pipefail
P="$1"; M="$2"; O="$M/evidence"
ip -j address > "$O/net-address.json"
ip -j route > "$O/net-route.json"
python3 -I "$P/ci/sandbox_gate.py" > "$O/sandbox-gate.txt" 2>&1
python3 -I "$P/harness/supervise.py" --out "$O/supervisor" --timeout 900 -- python3 -I "$M/device_runner.py" --candidate-root "$M" --harness-dir "$P/harness" --output "$O/results"
